import os
import logging
import hashlib
import asyncio
import time
from collections import deque
from typing import Dict, Any, Optional
from io import BytesIO
from dotenv import load_dotenv
from aiolimiter import AsyncLimiter
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler

# Load environment variables
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
DEEPAI_API_KEY = os.getenv('DEEPAI_API_KEY')

# Logging setup (enhanced for heavy monitoring)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - User:%(user_id)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# DeepAI API Base URL
DEEPAI_URL = "https://api.deepai.org/api"

# Global structures
user_limits: Dict[int, AsyncLimiter] = {}
caches: Dict[int, Dict[str, tuple]] = {}
queues: Dict[int, asyncio.Queue] = {}
history: Dict[int, deque] = {}

# States
WAITING_FOR_IMAGE = 0

def get_user_limiter(user_id: int) -> AsyncLimiter:
    if user_id not in user_limits:
        user_limits[user_id] = AsyncLimiter(5, 1)  # 5 calls per minute
    return user_limits[user_id]

def get_user_queue(user_id: int) -> asyncio.Queue:
    if user_id not in queues:
        queues[user_id] = asyncio.Queue()
    return queues[user_id]

def get_user_cache(user_id: int) -> Dict[str, tuple]:
    if user_id not in caches:
        caches[user_id] = {}
    return caches[user_id]

def get_user_history(user_id: int) -> deque:
    if user_id not in history:
        history[user_id] = deque(maxlen=3)
    return history[user_id]

def is_cached(user_id: int, input_hash: str, max_age: int = 3600) -> tuple[bool, Optional[Any]]:
    cache = get_user_cache(user_id)
    if input_hash in cache:
        result, ts = cache[input_hash]
        if time.time() - ts < max_age:
            return True, result
    return False, None

def cache_result(user_id: int, input_hash: str, result: Any):
    cache = get_user_cache(user_id)
    cache[input_hash] = (result, time.time())

# Background worker for queues (runs per user)
async def background_worker(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    user_id = job.data['user_id']
    queue = get_user_queue(user_id)
    while not queue.empty():
        feature_data = await queue.get()
        feature, input_data, chat_id, message_id = feature_data
        try:
            if feature == 'text2image':
                result = await process_text2image(input_data['prompt'], user_id)
            elif feature == 'summarize':
                result = await process_summarize(input_data['text'], user_id)
            elif feature == 'generate':
                result = await process_generate(input_data['prompt'], user_id)
            elif feature in ['nsfw', 'toonify', 'removebg', 'tag']:
                result = await process_image_feature(feature, input_data['image_bytes'], user_id)
            else:
                result = {'error': 'Unknown feature'}

            # Send result via bot
            if isinstance(result, dict) and 'image_url' in result:
                await context.bot.send_photo(chat_id, result['image_url'], caption=result.get('caption', ''))
            elif isinstance(result, str):
                await context.bot.send_message(chat_id, result)
            else:
                await context.bot.send_message(chat_id, str(result))
        except Exception as e:
            logger.error(f"Queue processing error for {user_id}: {e}", extra={'user_id': user_id})
            await context.bot.send_message(chat_id, f"Processing error: {e}")

# API Processing Functions (with rate limit, cache, queue)
async def process_text2image(prompt: str, user_id: int) -> Dict[str, Any]:
    input_hash = hashlib.md5(prompt.encode()).hexdigest()
    cached, result = is_cached(user_id, input_hash)
    if cached:
        logger.info(f"Cache hit for text2image, user {user_id}", extra={'user_id': user_id})
        return result

    async with get_user_limiter(user_id):
        queue = get_user_queue(user_id)
        if not queue.empty():
            await queue.put(('text2image', {'prompt': prompt}, user_id, None))
            return {'status': 'queued', 'message': f"Queued (position: {queue.qsize()}). I'll send the image soon!"}

        try:
            response = requests.post(
                f"{DEEPAI_URL}/text2img",
                data={'text': prompt[:1000]},  # Truncate
                headers={'api-key': DEEPAI_API_KEY},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            if 'output_url' in data:
                result = {'image_url': data['output_url'], 'caption': f"Generated from: '{prompt}' 🚀"}
                cache_result(user_id, input_hash, result)
                get_user_history(user_id).append('text2image')
                logger.info(f"Text2Image success for {user_id}", extra={'user_id': user_id})
                return result
            else:
                raise ValueError(data.get('err', 'No output'))
        except requests.exceptions.HTTPError as e:
            if response.status_code == 429:
                raise ValueError("Rate limit reached! Free tier is limited (~5/day). Upgrade at deepai.org for more ($5/mo).")
            raise e
        except Exception as e:
            logger.error(f"Text2Image error for {user_id}: {e}", extra={'user_id': user_id})
            raise ValueError(f"API error: {e}")

async def process_summarize(text: str, user_id: int) -> str:
    input_hash = hashlib.md5(text.encode()).hexdigest()
    cached, result = is_cached(user_id, input_hash)
    if cached:
        return result

    async with get_user_limiter(user_id):
        queue = get_user_queue(user_id)
        if not queue.empty():
            await queue.put(('summarize', {'text': text}, user_id, None))
            return "Queued—summary coming soon!"

        try:
            response = requests.post(
                f"{DEEPAI_URL}/summarization",
                data={'text': text[:5000]},
                headers={'api-key': DEEPAI_API_KEY},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            output = data.get('output', 'No summary generated.')
            cache_result(user_id, input_hash, output)
            get_user_history(user_id).append('summarize')
            return f"📝 Summary:\n{output}\n\n(Original: ~{len(text)} chars)"
        except Exception as e:
            logger.error(f"Summarize error for {user_id}: {e}", extra={'user_id': user_id})
            return f"Error: {e}"

async def process_generate(prompt: str, user_id: int) -> str:
    input_hash = hashlib.md5(prompt.encode()).hexdigest()
    cached, result = is_cached(user_id, input_hash)
    if cached:
        return result

    async with get_user_limiter(user_id):
        queue = get_user_queue(user_id)
        if not queue.empty():
            await queue.put(('generate', {'prompt': prompt}, user_id, None))
            return "Queued—generated text coming soon!"

        try:
            response = requests.post(
                f"{DEEPAI_URL}/text-generator",
                data={'text': prompt[:1000]},
                headers={'api-key': DEEPAI_API_KEY},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            output = data.get('output', 'No text generated.')[:1000]  # Truncate response
            cache_result(user_id, input_hash, output)
            get_user_history(user_id).append('generate')
            return f"✍️ Generated Text:\n{output}\n\n(Prompt: '{prompt}')"
        except Exception as e:
            logger.error(f"Generate error for {user_id}: {e}", extra={'user_id': user_id})
            return f"Error: {e}"

async def process_image_feature(feature: str, image_bytes: BytesIO, user_id: int) -> Any:
    image_bytes.seek(0)
    image_hash = hashlib.md5(image_bytes.read()).hexdigest()
    input_hash = f"{feature}_{image_hash}"
    cached, result = is_cached(user_id, input_hash)
    if cached:
        logger.info(f"Cache hit for {feature}, user {user_id}", extra={'user_id': user_id})
        return result

    async with get_user_limiter(user_id):
        queue = get_user_queue(user_id)
        if not queue.empty():
            image_bytes_copy = BytesIO(image_bytes.read())
            await queue.put((feature, {'image_bytes': image_bytes_copy}, user_id, None))
            return f"Queued for {feature}—result coming soon!"

        try:
            endpoint = {
                'nsfw': 'nsfw-detector',
                'toonify': 'toonify',
                'removebg': 'remove-background',
                'tag': 'image-tag'  # Note: DeepAI's tagging is via /image-tag or similar; adjust if needed
            }.get(feature, feature)
            files = {'image': ('image.jpg', image_bytes, 'image/jpeg')}
            response = requests.post(
                f"{DEEPAI_URL}/{endpoint}",
                files=files,
                headers={'api-key': DEEPAI_API_KEY},
                timeout=60  # Longer for images
            )
            response.raise_for_status()
            data = response.json()

            if feature == 'nsfw' and 'output' in data:
                score = data['output']
                status = "🚫 NSFW detected!" if score > 0.5 else "✅ Safe content!"
                output = f"{status}\nConfidence: {score:.2f}"
                get_user_history(user_id).append('nsfw')
            elif feature in ['toonify', 'removebg'] and 'output_url' in data:
                output = {'image_url': data['output_url'], 'caption': f"{feature.title()}ed image! 🎨"}
                get_user_history(user_id).append(feature)
            elif feature == 'tag' and 'output' in data:
                tags = data['output'][:10]  # Top tags
                output = f"🏷️ Tags: {', '.join(tags)}"
                get_user_history(user_id).append('tag')
            else:
                raise ValueError(data.get('err', 'No output'))

            cache_result(user_id, input_hash, output)
            logger.info(f"{feature} success for {user_id}", extra={'user_id': user_id})
            return output
        except Exception as e:
            logger.error(f"{feature} error for {user_id}: {e}", extra={'user_id': user_id})
            return f"Error processing {feature}: {e}"

# NLP Intent Parser
def parse_intent(text: str, has_photo: bool = False) -> tuple[Optional[str], Optional[str]]:
    text_lower = text.lower().strip()
    if has_photo:
        if any(word in text_lower for word in ['nsfw', 'safe', 'check', 'inappropriate']):
            return 'nsfw', text
        elif any(word in text_lower for word in ['tag', 'describe', 'labels', 'what is']):
            return 'tag', text
        elif any(word in text_lower for word in ['toon', 'cartoon', 'animate']):
            return 'toonify', text
        elif any(word in text_lower for word in ['background', 'remove bg', 'transparent']):
            return 'removebg', text
        return None, None
    if any(word in text_lower for word in ['image', 'generate', 'draw', 'picture', 'art']):
        return 'text2image', text
    elif any(word in text_lower for word in ['summarize', 'summary', 'shorten', 'tl;dr']):
        return 'summarize', text
    elif any(word in text_lower for word in ['generate text', 'write', 'story', 'continue']):
        return 'generate', text
    return None, None

# Menu Keyboards (personalized)
def main_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    hist = list(get_user_history(user_id))
    keyboard = []
    if 'text2image' in hist:
        keyboard.append([InlineKeyboardButton("🎨 Recent: Text-to-Image", callback_data='start_text2image')])
    if 'summarize' in hist:
        keyboard.append([InlineKeyboardButton("📝 Recent: Summarize", callback_data='start_summarize')])
    keyboard.extend([
        [InlineKeyboardButton("🖼️ Image Generation", callback_data='menu_image')],
        [InlineKeyboardButton("📝 Text Processing", callback_data='menu_text')],
        [InlineKeyboardButton("🔍 Content Analysis", callback_data='menu_analysis')],
        [InlineKeyboardButton("ℹ️ Help", callback_data='menu_help')],
        [InlineKeyboardButton("📊 Stats", callback_data='show_stats')],
    ])
    return InlineKeyboardMarkup(keyboard)

def image_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Text-to-Image", callback_data='start_text2image')],
        [InlineKeyboardButton("Toonify", callback_data='start_toonify')],
        [InlineKeyboardButton("Remove Background", callback_data='start_removebg')],
        [InlineKeyboardButton("← Back", callback_data='main_menu')],
    ])

def text_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Summarize Text", callback_data='start_summarize')],
        [InlineKeyboardButton("Generate Text", callback_data='start_generate')],
        [InlineKeyboardButton("← Back", callback_data='main_menu')],
    ])

def analysis_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("NSFW Detection", callback_data='start_nsfw')],
        [InlineKeyboardButton("Image Tagging", callback_data='start_tag')],
        [InlineKeyboardButton("← Back", callback_data='main_menu')],
    ])

def help_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Tips & Examples", callback_data='show_tips')],
        [InlineKeyboardButton("Limits & Upgrade", callback_data='show_limits')],
        [InlineKeyboardButton("← Back", callback_data='main_menu')],
    ])

# Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    logger.info(f"Start command from {user_id}", extra={'user_id': user_id})
    await update.message.reply_text(
        "🚀 Welcome to Smart DeepAI Bot!\n\n"
        "I'm powered by DeepAI—generate images, summarize text, analyze photos, and more.\n"
        "Just chat naturally (e.g., 'draw a cat' or upload photo + 'check NSFW') or use buttons.\n\n"
        "For heavy use, check /stats or upgrade DeepAI plan.",
        reply_markup=main_menu_keyboard(user_id)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    data = query.data
    logger.info(f"Button '{data}' from {user_id}", extra={'user_id': user_id})

    if data == 'main_menu':
        await query.edit_message_text("Main Menu:", reply_markup=main_menu_keyboard(user_id))
        return

    # Category menus
    if data == 'menu_image':
        await query.edit_message_text("Image Features:", reply_markup=image_menu_keyboard())
    elif data == 'menu_text':
        await query.edit_message_text("Text Features:", reply_markup=text_menu_keyboard())
    elif data == 'menu_analysis':
        await query.edit_message_text("Analysis Features:", reply_markup=analysis_menu_keyboard())
    elif data == 'menu_help':
        await query.edit_message_text("Help:", reply_markup=help_menu_keyboard())

    # Feature starters
