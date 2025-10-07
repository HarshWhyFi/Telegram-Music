import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, InlineQueryHandler, ContextTypes
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import yt_dlp
import asyncio
from typing import Dict, List, Optional
from cachetools import TTLCache
import re

# Replace with your NEW Telegram token (URGENT: Revoke the old one!)
TELEGRAM_TOKEN = 'YOUR_NEW_TELEGRAM_BOT_TOKEN'  # Get from @BotFather NOW!
YOUTUBE_API_KEY = 'AIzaSyCZBf20AuQ2KS7M77YBrpCeEW6TZtwDg9A'  # Your key

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# YouTube API setup
youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)

# Caches: TTL 5 min for searches
search_cache = TTLCache(maxsize=100, ttl=300)

# In-memory storage
queues: Dict[int, List[Dict]] = {}
current_playing: Dict[int, Dict] = {}
history: Dict[int, List[Dict]] = {}

# Smart query enhancements
MOOD_KEYWORDS = {
    'happy': 'upbeat pop music',
    'sad': 'ballads emotional songs',
    'workout': 'energetic gym music',
    'relax': 'chill lo-fi beats',
    'party': 'dance edm hits'
}
ARTIST_ALIASES = {
    'beatles': 'The Beatles',
    'mj': 'Michael Jackson',
    'taylor': 'Taylor Swift'
}

def enhance_query(query: str) -> str:
    query_lower = query.lower()
    enhanced = query
    for alias, full in ARTIST_ALIASES.items():
        if alias in query_lower:
            enhanced = re.sub(r'\b' + re.escape(alias) + r'\b', full, enhanced, count=1)
    for mood, append in MOOD_KEYWORDS.items():
        if mood in query_lower:
            enhanced += f' {append}'
            break
    if not any(word in query_lower for word in ['music', 'song', 'official', 'video']):
        enhanced += ' official music video'
    return enhanced

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text('🏓 Pong! Bot is responding.')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    try:
        trending_response = youtube.videos().list(
            part='id,snippet',
            chart='mostPopular',
            videoCategoryId='10',
            maxResults=3,
            regionCode='US'
        ).execute()
        recs = []
        for item in trending_response['items']:
            title = item['snippet']['title'][:50]
            video_id = item['id']
            recs.append(f"• {title}\nhttps://youtube.com/watch?v={video_id}")
        rec_text = "\n".join(recs) if recs else "No trends available."
        keyboard = [
            [InlineKeyboardButton("🔥 Refresh Trending", callback_data="trending")],
            [InlineKeyboardButton("📜 My History", callback_data="history")],
            [InlineKeyboardButton("🔍 Smart Search", callback_data="search_menu")],
            [InlineKeyboardButton("❓ Help", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f'🧠 Welcome to Smart Music Bot!\n\nAudio-only streaming. Let\'s play!\n\n🔥 Top Trending:\n{rec_text}\n\nCommands: /search, /play, /history, /ping',
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except HttpError as e:
        if e.resp.status in [403, 429]:
            await update.message.reply_text(f'API Error ({e.resp.status}): Check quota/key.')
        else:
            logger.error(f"Trending error: {e}")
            await update.message.reply_text('Welcome! Use /search to start.')
    except Exception as e:
        logger.error(f"Start error: {e}")
        await update.message.reply_text('Welcome! Bot ready. Use /search <query> for audio.')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "🧠 **Smart Music Bot (Audio Only):** \n\n"
        "**Features:**\n"
        "- 🔍 Search: Top 5 audio results.\n"
        "- 🎯 Recs: Similar audio.\n"
        "- 📋 Queue: Add/skip audio.\n"
        "- 📜 History: Past plays.\n\n"
        "**Commands:**\n"
        "/start - Menu\n"
        "/search <query> - Top 5 audio\n"
        "/play <query/url> - Queue audio\n"
        "/queue - View controls\n"
        "/next - Skip audio\n"
        "/history - Past\n"
        "/clear_queue - Reset\n"
        "/ping - Test\n"
        "/help - Guide\n\n"
        "Inline: @bot <song>"
    )
    keyboard = [[InlineKeyboardButton("Test API", callback_data="test_api")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(help_text, reply_markup=reply_markup, parse_mode='Markdown')

async def test_api(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        response = youtube.search().list(q='test', part='id', maxResults=1).execute()
        await update.message.reply_text('✅ YouTube API OK!')
    except HttpError as e:
        await update.message.reply_text(f'❌ API Error: {e.resp.status} - {e.resp.reason}')

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE, is_inline: bool = False) -> None:
    if is_inline:
        query_input = update.inline_query.query.strip()
        chat_id = None
    else:
        query_input = ' '.join(context.args)
        chat_id = update.effective_chat.id
        if not query_input:
            await update.message.reply_text('Usage: /search <query>')
            return
        await update.message.reply_text(f"🧠 Top 5 audio for '{query_input}'...")

    if not query_input:
        return

    query = enhance_query(query_input)
    cache_key = f"search:{query}"
    enhanced_note = ""

    if cache_key in search_cache:
        results = search_cache[cache_key]
    else:
        try:
            search_response = youtube.search().list(
                q=query,
                part='id,snippet',
                maxResults=5,
                type='video'
            ).execute()
            results = search_response['items'][:5]
            if not results:
                fuzzy_query = re.sub(r' official music video$', '', query) + ' audio'
                fuzzy_response = youtube.search().list(q=fuzzy_query, part='id,snippet', maxResults=5, type='video').execute()
                results = fuzzy_response['items'][:5]
                enhanced_note = " (fuzzy)"
            if results:
                search_cache[cache_key] = results
        except HttpError as e:
            if e.resp.status in [403, 429]:
                if not is_inline:
                    await update.message.reply_text('API quota hit.')
                return
            raise
        except Exception as e:
            logger.error(f"Search error: {e}")
            if not is_inline:
                await update.message.reply_text('Search failed.')
            return

    if not results:
        if not is_inline:
            await update.message.reply_text(f'No audio results for "{query_input}".')
        return

    if not is_inline:
        keyboard = []
        for item in results:
            title = item['snippet']['title'][:40] + '...' if len(item['snippet']['title']) > 40 else item['snippet']['title']
            video_id = item['id']['videoId']
            callback_data = f"smart_play:{video_id}:{title}"
            keyboard.append([InlineKeyboardButton(title, callback_data=callback_data)])
        if results:
            keyboard.append([InlineKeyboardButton("🎯 Recs", callback_data=f"recommend:{results[0]['id']['videoId']}:{query_input}")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"🧠 Top 5 audio{enhanced_note}:", reply_markup=reply_markup)
    else:
        inline_results = []
        for item in results:
            title = item['snippet']['title']
            video_id = item['id']['videoId']
            link = f"https://www.youtube.com/watch?v={video_id}"
            description = item['snippet']['description'][:80] + '...'
            thumb_url = item['snippet'].get('thumbnails', {}).get('medium', {}).get('url', '')
            inline_results.append(
                InlineQueryResultArticle(
                    id=video_id,
                    title=title,
                    description=description,
                    thumb_url=thumb_url,
                    input_message_content=InputTextMessageContent(f"🎵 Audio: {title}\n{link}"),
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Play Audio", callback_data=f"smart_play:{video_id}:{title}")]])
                )
            )
        await update.inline_query.answer(inline_results, cache_time=60)

async def inline_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await search(update, context, is_inline=True)

def get_audio_url(video_url: str) -> tuple[str, str]:
    try:
        ydl_opts = {
            'format': 'bestaudio/best[filesize<50M]/bestaudio[ext=m4a]/bestaudio',
            'quiet': True,
            'no_warnings': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            if not info.get('url') or info.get('duration', 0) > 1800:
                raise ValueError("Audio too long/unavailable.")
            return info['url'], info.get('title', 'Unknown Audio')
    except Exception as e:
        logger.error(f"Audio error: {e}")
        raise ValueError("Audio failed—skipping.")

async def smart_play(chat_id: int, video_id: str, title: str, update_or_query, context: ContextTypes.DEFAULT_TYPE, recommend_after: bool = True) -> None:
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        await update_or_query.message.reply_text(f"🎧 Streaming audio '{title}'...")
        audio_url, actual_title = get_audio_url(video_url)
        message = await update_or_query.message.reply_audio(
            audio=audio_url,
            title=actual_title or title,
            performer="Audio Bot",
            caption=f"🎵 {title} (Audio Only)",
            duration=0
        )
        current_playing[chat_id] = {'video_id': video_id, 'title': title}
        history.setdefault(chat_id, []).append({'video_id': video_id, 'title': title})
        if len(history[chat_id]) > 50:
            history[chat_id].pop(0)
        if recommend_after:
            keyboard = [
                [InlineKeyboardButton("🎯 More Like This", callback_data=f"recommend:{video_id}:{title}")],
                [InlineKeyboardButton("➕ Add to Queue", callback_data=f"queue_add:{video_id}:{title}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await message.reply_text("More?", reply_markup=reply_markup)
    except ValueError as e:
        await update_or_query.message.reply_text(f"⚠️ {str(e)}. Skipping...")
        await next_smart(chat_id, update_or_query, context)
    except Exception as e:
        logger.error(f"Play error: {e}")
        await update_or_query.message.reply_text('Audio failed.')

async def get_recommendations(related_video_id: str, orig_query: str, max_results: int = 3) -> List[Dict]:
    try:
        rec_response = youtube.search().list(
            part='id,snippet',
            maxResults=max_results,
            relatedToVideoId=related_video_id,
            type='video',
            q=orig_query
        ).execute()
        return rec_response['items'][:3]
    except Exception:
        fallback_response = youtube.search().list(q=orig_query + ' similar audio', part='id,snippet', maxResults=3, type='video').execute()
        return fallback_response['items'][:3]

async def next_smart(chat_id: int, update_or_query, context: ContextTypes.DEFAULT_TYPE) -> None:
    queue = queues.get(chat_id, [])
    if queue:
        next_song = queue.pop(0)
        queues[chat_id] = queue
        await smart_play(chat_id, next_song['video_id'], next_song['title'], update_or_query, context)
    else:
        await update_or_query.message.reply_text("Queue empty.")

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text('Usage: /play <query or URL>')
        return
    arg = ' '.join(context.args)
    video_id = None
    title = "Unknown"
    if 'youtube.com/watch?v=' in arg or 'youtu.be/' in arg:
        match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', arg)
        if match:
            video_id = match.group(1)
            title = f"Direct Audio"
        else:
            await update.message.reply_text('Invalid URL.')
            return
    else:
        try:
            search_response = youtube.search().list(
                q=enhance_query(arg),
                part='id,snippet',
                maxResults=1,
                type='video'
            ).execute()
            if search_response['items']:
                item = search_response['items'][0]
                video_id = item['id']['videoId']
                title = item['snippet']['title']
            else:
                await update.message.reply_text('No results for query.')
                return
        except Exception as e:
            logger.error(f"Play search error: {e}")
            await update.message.reply_text('Play failed.')
            return

    if video_id:
        song = {'video_id': video_id, 'title': title}
        queue = queues.setdefault(chat_id, [])
        if not current_playing.get(chat_id) and not queue:
            await smart_play(chat_id, video_id, title, update, context)
        else:
            queue.append(song)
            await update.message.reply_text(f"➕ Added '{title}' to queue (pos {len(queue)}).")
    else:
        await update.message.reply_text('No video ID found.')

async def queue_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    queue = queues.get(chat_id, [])
    msg = "📋 Queue:\n"
    if current_playing.get(chat_id):
        msg += f"▶️ Now: {current_playing[chat_id]['title']}\n"
    for i, song in enumerate(queue, 1):
        msg += f"{i}. {song['title']}\n"
    if not queue and not current_playing.get(chat_id):
        msg = "Queue empty."
    keyboard = [
        [InlineKeyboardButton("⏭ Next", callback_data="next")],
        [InlineKeyboardButton("🗑 Clear", callback_data="clear_queue")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(msg, reply_markup=reply_markup)

async def next_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await next_smart(chat_id, update, context)

async def history_command(update: Update, context:
