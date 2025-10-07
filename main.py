import os
import logging
import hashlib
import time
from collections import deque
from typing import Dict, Any, Optional
from io import BytesIO
from dotenv import load_dotenv
from aiolimiter import AsyncLimiter
import requests
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# Load environment variables
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
DEEPAI_API_KEY = os.getenv('DEEPAI_API_KEY')

if not TELEGRAM_BOT_TOKEN or not DEEPAI_API_KEY:
    raise ValueError("Missing TELEGRAM_BOT_TOKEN or DEEPAI_API_KEY in .env")

# Logging setup
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
history: Dict[int, deque] = {}

def get_user_limiter(user_id: int) -> AsyncLimiter:
    if user_id not in user_limits:
        user_limits[user_id] = AsyncLimiter(5, 1)
    return user_limits[user_id]

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

# API Processing Functions (run in thread for async)
async def _api_call(endpoint: str, data: Dict, files: Optional[Dict] = None, user_id: int = 0) -> Dict:
    try:
        response = requests.post(
            f"{DEEPAI_URL}/{endpoint}",
            data=data,
            files=files,
            headers={'api-key': DEEPAI_API_KEY},
            timeout=60
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        if response.status_code == 429:
            raise ValueError("DeepAI rate limit hit! Free tier ~5 calls/day. Upgrade at deepai.org ($5/mo for more).")
        raise ValueError(f"API error {response.status_code}: {e}")
    except Exception as e:
        logger.error(f"API call error for {user_id}: {e}", extra={'user_id': user_id})
        raise ValueError(f"API failed: {e}")

async def process_text2image(prompt: str, user_id: int) -> Dict[str, Any]:
    input_hash = hashlib.md5(prompt.encode()).hexdigest()
    cached, result = is_cached(user_id, input_hash)
    if cached:
        logger.info(f"Cache hit text2image {user_id}", extra={'user_id': user_id})
        return result

    async with get_user_limiter(user_id):
        try:
            data = await _api_call('text2img', {'text': prompt[:1000]}, user_id=user_id)
            if 'output_url' in data:
                result = {'image_url': data['output_url'], 'caption': f"Generated: '{prompt}' 🚀"}
                cache_result(user_id, input_hash, result)
                get_user_history(user_id).append('text2image')
                return result
            else:
                raise ValueError(data.get('err', 'No output'))
        except ValueError as e:
            logger.error(f"Text2Image error {user_id}: {e}", extra={'user_id': user_id})
            return {'error': str(e)}

async def process_summarize(text: str, user_id: int) -> str:
    input_hash = hashlib.md5(text.encode()).hexdigest()
    cached, result = is_cached(user_id, input_hash)
    if cached:
        return result

    async with get_user_limiter(user_id):
        try:
            data = await _api_call('summarization', {'text': text[:5000]}, user_id=user_id)
            output = data.get('output', 'No summary.')
            cache_result(user_id, input_hash, output)
            get_user_history(user_id).append('summarize')
            return f"📝 Summary:\n{output}"
        except ValueError as e:
            return f"Error: {e}"

async def process_generate(prompt: str, user_id: int) -> str:
    input_hash = hashlib.md5(prompt.encode()).hexdigest()
    cached, result = is_cached(user_id, input_hash)
    if cached:
        return result

    async with get_user_limiter(user_id):
        try:
            data = await _api_call('text-generator', {'text': prompt[:1000]}, user_id=user_id)
            output = data.get('output', 'No text.')[ :1000]
            cache_result(user_id, input_hash, output)
            get_user_history(user_id).append('generate')
            return f"✍️ Generated:\n{output}"
        except ValueError as e:
            return f"Error: {e}"

async def process_image_feature(feature: str, image_bytes: BytesIO, user_id: int) -> Any:
    image_bytes.seek(0)
    image_hash = hashlib.md5(image_bytes.read()).hexdigest()
    input_hash = f"{feature}_{image_hash}"
    cached, result = is_cached(user_id, input_hash)
    if cached:
        logger.info(f"Cache hit {feature} {user_id}", extra={'user_id': user_id})
        return result

    async with get_user_limiter(user_id):
        image_bytes.seek(0)  # Reset for upload
        files = {'image': ('image.jpg', image_bytes, 'image/jpeg')}
        endpoint_map = {
            'nsfw': 'nsfw-detector',
            'toonify': 'toonify',
            'removebg': 'remove-background',
            'tag': 'image-tag'
        }
        endpoint = endpoint_map.get(feature, feature)
        try:
            data = await _api_call(endpoint, {}, files, user_id)
            if feature == 'nsfw':
                score = data.get('output', 0)
                status = "🚫 NSFW!" if score > 0.5 else "✅ Safe!"
                output = f"{status}\nConfidence: {score:.2f}"
                get_user_history(user_id).append('nsfw')
            elif feature in ['toonify', 'removebg']:
                if 'output_url' in data:
                    output = {'image_url': data['output_url'], 'caption': f"{feature.title()}ed! 🎨"}
                    get_user_history(user_id).append(feature)
                else:
                    raise ValueError(data.get('err', 'No image'))
            elif feature == 'tag':
                tags = data.get('output', [])[:10]
                output = f"🏷️ Tags: {', '.join(tags)}"
                get_user_history(user_id).append('tag')
            else:
                raise ValueError(data.get('err', 'No output'))
            cache_result(user_id, input_hash, output)
            return output
        except ValueError as e:
            return f"Error in {feature}: {e}"

# NLP Parser
def parse_intent(text: str, has_photo: bool = False) -> tuple[Optional[str], str]:
    text_lower = text.lower().strip()
    if has_photo:
        if any(word in text_lower for word in ['nsfw', 'safe', 'check', 'inappropriate']):
            return 'nsfw', text
        if any(word in text_lower for word in ['tag', 'describe', 'labels']):
            return 'tag', text
        if any(word in text_lower for word in ['toon', 'cartoon']):
            return 'toonify', text
        if any(word in text_lower for word in ['background', 'remove bg']):
            return 'removebg', text
        return None, text
    if any(word in text_lower for word in ['image', 'generate', 'draw', 'picture']):
        return 'text2image', text
    if any(word in text_lower for word in ['summarize', 'summary', 'shorten']):
        return 'summarize', text
    if any(word in text_lower for word in ['generate text', 'write', 'story']):
        return 'generate', text
    return None, text

# Menus
def main_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    hist = list(get_user_history(user_id))
    keyboard = []
    if 'text2image' in hist:
        keyboard.append([InlineKeyboardButton("🎨 Recent: Image Gen", callback_data='start_text2image')])
    keyboard += [
        [InlineKeyboardButton("🖼️ Images", callback_data='menu_image')],
        [InlineKeyboardButton("📝 Text", callback_data='menu_text')],
        [InlineKeyboardButton("🔍 Analysis", callback_data='menu_analysis')],
        [InlineKeyboardButton("ℹ️ Help", callback_data='menu_help')],
        [InlineKeyboardButton("📊 Stats", callback_data='show_stats')],
    ]
    return InlineKeyboardMarkup(keyboard)

def image_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Text-to-Image", callback_data='start_text2image')],
        [InlineKeyboardButton("Toonify", callback_data='start_toonify')],
        [InlineKeyboardButton("Remove BG", callback_data='start_removebg')],
        [InlineKeyboardButton("← Back", callback_data='main_menu')],
    ])

def text_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Summarize", callback_data='start_summarize')],
        [InlineKeyboardButton("Generate Text", callback_data='start_generate')],
        [InlineKeyboardButton("← Back", callback_data='main_menu')],
    ])

def analysis_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("NSFW Check", callback_data='start_nsfw')],
        [InlineKeyboardButton("Tag Image", callback_data='start_tag')],
        [InlineKeyboardButton("← Back", callback_data='main_menu')],
    ])

def help_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Tips", callback_data='show_tips')],
        [InlineKeyboardButton("Limits", callback_data='show_limits')],
        [InlineKeyboardButton("← Back", callback_data='main_menu')],
    ])

# Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    logger.info(f"Start from {user_id}", extra={'user_id': user_id})
    context.user_data.clear()  # Reset state
    await update.message.reply_text(
        "🚀 DeepAI Bot ready! Say 'generate image of cat' or use buttons.",
        reply_markup=main_menu_keyboard(user_id)
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    await update.message.reply_text("Help:", reply_markup=help_menu_keyboard())

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    hist = list(get_user_history(user_id))
    calls = len(get_user_cache(user_id))
    text = f"Stats:\nHistory: {', '.join(hist) or 'None'}\nCalls (cached): {calls}"
    await update.message.reply_text(text, reply_markup=main_menu_keyboard(user_id))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    data = query.data
    logger.info(f"Button {data} from {user_id}", extra={'user_id': user_id})

    if data == 'main_menu':
        await query.edit_message_text("Menu:", reply_markup=main_menu_keyboard(user_id))
        return

    # Categories
    if data == 'menu_image':
        await query.edit_message_text("Images:", reply_markup=image_menu_keyboard())
    elif data == 'menu_text':
        await query.edit_message_text("Text:", reply_markup=text_menu_keyboard())
    elif data == 'menu_analysis':
        await query.edit_message_text("Analysis:", reply_markup=analysis_menu_keyboard())
    elif data == 'menu_help':
        await query.edit_message_text("Help:", reply_markup=help_menu_keyboard())

    # Feature starters (set state)
    elif data == 'start_text2image':
        context.user_data['waiting_for'] = 'text2image'
        await query.edit_message_text("Send image prompt (e.g., 'cat in space'):")
    elif data == 'start_summarize':
        context.user_data['waiting_for'] = 'summarize'
        await query.edit_message_text("Send text to summarize:")
    elif data == 'start_generate':
        context.user_data['waiting_for'] = 'generate'
        await query.edit_message_text("Send text prompt (e.g., 'write a story'):")
    elif data in ['start_nsfw', 'start_toonify', 'start_removebg', 'start_tag']:
        feature = data.split('_')[1]
        context.user_data['waiting_for_image'] = feature
        cancel_btn = InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data='cancel_wait')]])
        await query.edit_message_text(f"Upload photo for {feature}:", reply_markup=cancel_btn)
    elif data == 'cancel_wait':
        context.user_data.pop('waiting_for_image', None)
        await query.edit_message_text("Cancelled.", reply_markup=main_menu_keyboard(user_id))

    # Help subs
    elif data == 'show_tips':
        tips = "Tips:\n- Use detailed prompts.\n- Photos <10MB.\n- NLP: 'draw dragon' works!"
        await query.edit_message_text(tips, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data='menu_help')]]))
    elif data == 'show_limits':
        limits = "Limits:\n- Bot: 5/min per user.\n- DeepAI Free: ~5/day. Upgrade for heavy use."
        await query.edit_message_text(limits, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data='menu_help')]]))

    elif data == 'show_stats':
        hist = list(get_user_history(user_id))
        calls = len(get_user_cache(user_id))
        text = f"Stats:\nRecent: {', '.join(hist) or 'None'}\nCalls: {calls}"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data='main_menu')]]))

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    text = update.message.text
    waiting = context.user_data.get('waiting_for')
    logger.info(f"Text '{text[:30]}' from {user_id}",
