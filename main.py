import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, InlineQueryHandler, MessageHandler, filters, ContextTypes
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import yt_dlp
import asyncio
from typing import Dict, List, Optional
from cachetools import TTLCache
import re

# Replace with your actual tokens/keys (URGENT: Get a NEW Telegram token!)
TELEGRAM_TOKEN = '7938834721:AAFj6sUtlCfH0VPVzUFspINeIrN65goNTLw'  # REPLACE WITH NEW TOKEN FROM BOTFATHER!
YOUTUBE_API_KEY = 'AIzaSyCZBf20AuQ2KS7M77YBrpCeEW6TZtwDg9A'  # Your provided key—keep private!

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
history: Dict[int, List[Dict]] = {}  # {chat_id: List[song info]}

# Smart query enhancements: Keyword mappings
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
    """Smartly enhance query with moods, aliases, etc."""
    query_lower = query.lower()
    enhanced = query

    # Alias replacement
    for alias, full in ARTIST_ALIASES.items():
        if alias in query_lower:
            enhanced = re.sub(r'\b' + re.escape(alias) + r'\b', full, enhanced, count=1)

    # Mood detection
    for mood, append in MOOD_KEYWORDS.items():
        if mood in query_lower:
            enhanced += f' {append}'
            break

    # Common additions
    if not any(word in query_lower for word in ['music', 'song', 'official', 'video']):
        enhanced += ' official music video'

    return enhanced

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Test responsiveness."""
    await update.message.reply_text('🏓 Pong! Bot is alive and responding.')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Smart welcome with trending recommendations."""
    chat_id = update.effective_chat.id
    try:
        # Get trending music (videoCategoryId=10 for music)
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

        rec_text = "\n".join(recs) if recs else "No trends available (check API quota)."

        keyboard = [
            [InlineKeyboardButton("🔥 Refresh Trending", callback_data="trending")],
            [InlineKeyboardButton("📜 My History", callback_data="history")],
            [InlineKeyboardButton("🔍 Smart Search", callback_data="search_menu")],
            [InlineKeyboardButton("❓ Help", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f'🧠 Welcome to Smart Music Bot!\n\n'
            f'Audio-only streaming from YouTube. Let\'s play!\n\n'
            f'🔥 Top Trending:\n{rec_text}\n\n'
            'Commands: /search <query>, /play <url/query>, /history, /ping',
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except HttpError as e:
        if e.resp.status in [403, 429]:
            await update.message.reply_text(f'API Error ({e.resp.status}): Check quota or key restrictions.')
        else:
            logger.error(f"Trending error: {e}")
            await update.message.reply_text('Welcome! Use /search to start. (Trending failed)')
    except Exception as e:
        logger.error(f"Start error: {e}")
        await update.message.reply_text('Welcome! Bot is responding. Use /search <query> for audio.')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Enhanced help."""
    help_text = (
        "🧠 **Smart Music Bot Guide:**\n\n"
        "**Audio-Only Features:**\n"
        "- 🔍 **Search**: Top 5 results, play audio streams (no video).\n"
        "- 🎯 **Recommendations**: Similar audio suggestions.\n"
        "- 📋 **Queue**: Add/play/skip audio tracks.\n"
        "- 📜 **History**: Past audio plays.\n\n"
        "**Commands:**\n"
        "/start - Menu & trending\n"
        "/search <query> - Top 5 audio search\n"
        "/play <url or query> - Queue & stream audio\n"
        "/queue - View queue with controls\n"
        "/next - Skip to next audio\n"
        "/history - Past plays\n"
        "/clear_queue - Reset queue\n"
        "/ping - Test response\n"
        "/help - This guide\n\n"
        "Inline: @yourbot <song> for quick audio search."
    )
    keyboard = [[InlineKeyboardButton("Test API", callback_data="test_api")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(help_text, reply_markup=reply_markup, parse_mode='Markdown')

async def test_api(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Test the API key."""
    try:
        response = youtube.search().list(q='test', part='id', maxResults=1).execute()
        await update.message.reply_text('✅ YouTube API Working!')
    except HttpError as e:
        error_msg = f'❌ API Error: {e.resp.status} - {e.resp.reason}\nCheck key/quotas.'
        await update.message.reply_text(error_msg)

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE, is_inline: bool = False) -> None:
    """Smart search limited to top 5 audio results."""
    if is_inline:
        query_input = update.inline_query.query.strip()
        chat_id = None
    else:
        query_input = ' '.join(context.args)
        chat_id = update.effective_chat.id
        if not query_input:
            await update.message.reply_text('Provide a query, e.g., /search bohemian rhapsody!')
            return
        await update.message.reply_text(f"🧠 Searching top 5 audio for '{query_input}'...")

    if not query_input:
        return

    query = enhance_query(query_input)
    cache_key = f"search:{query}"

    if cache_key in search_cache:
        results = search_cache[cache_key]
        enhanced_note = " (cached)"
    else:
        try:
            search_response = youtube.search().list(
                q=query,
                part='id,snippet',
                maxResults=5,  # Top 5 only
                type='video'
            ).execute()
            results = search_response['items'][:5]
            if results:
                search_cache[cache_key] = results
            else:
                fuzzy_query = re.sub(r' official music video$', '', query) + ' audio'
                fuzzy_response = youtube.search().list(q=fuzzy_query, part='id,snippet', maxResults=5, type='video').execute()
                results = fuzzy_response['items'][:5]
                enhanced_note = " (fuzzy match)"
                if results:
                    search_cache[cache_key] = results
        except HttpError as e:
            if e.resp.status in [403, 429]:
                msg = 'API quota hit. Try later.'
                if not is_inline:
                    await update.message.reply_text(msg)
                return
            raise
        except Exception as e:
            logger.error(f"Search error: {e}")
            if not is_inline:
                await update.message.reply_text('Search failed. Check API.')
            return

    if not results:
        if not is_inline:
            await update.message.reply_text(f'No top 5 audio results for "{query_input}". Try another query!')
        return

    enhanced_note = getattr(locals().get('enhanced_note'), 'value', '') if 'enhanced_note' in locals() else ''
    if not is_inline:
        keyboard = []
        for item in results:
            title = item['snippet']['title'][:40] + '...' if len(item['snippet']['title']) > 40 else item['snippet']['title']
            video_id = item['id']['videoId']
            callback_data = f"smart_play:{video_id}:{title}"
            keyboard.append([InlineKeyboardButton(title, callback_data=callback_data)])

        keyboard.append([InlineKeyboardButton("🎯 Recs", callback_data=f"recommend:{results[0]['id']['videoId']}:{query_input}")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"🧠 Top 5 audio results for '{query_input}'{enhanced_note}:", reply_markup=reply_markup)
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
    """Extract audio stream only."""
    try:
        ydl_opts = {
            'format': 'bestaudio/best[filesize<50M]/bestaudio[ext=m4a]/bestaudio',
            'quiet': True,
            'no_warnings': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            if not info.get('url') or info.get('duration', 0) > 1800:  # Limit to 30 min
                raise ValueError("Audio too long/unavailable.")
            return info['url'], info.get('title', 'Unknown Audio')
    except Exception as e:
        logger.error(f"Audio extract error: {e}")
        raise ValueError("Audio stream failed—skipping.")

async def smart_play(chat_id: int, video_id: str, title: str, update_or_query, context: ContextTypes.DEFAULT_TYPE, recommend_after: bool = True) -> None:
    """Stream audio only, update queue/history."""
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        await update_or_query.message.reply_text(f"🎧 Streaming audio for '{title}'...")

        audio_url, actual_title = get_audio_url(video_url)

        # Send audio message (no video)
        message = await update_or_query.message.reply_audio(
            audio=audio_url,
            title=actual_title or title,
            performer="Audio Bot",
            caption=f"🎵 {title} (Audio Only)\n🧠 Smart Stream",
            duration=0
        )

        # Update state
        current_playing[chat_id] = {'video_id': video_id, 'title': title}
        history.setdefault(chat_id, []).append({'video_id': video_id, 'title': title})
        if len(history[chat_id]) > 50:
            history[chat_id].pop(0)

        if recommend_after:
            keyboard = [
                [InlineKeyboardButton("🎯 More Audio Like This", callback_data=f"recommend:{video_id}:{title}")],
                [InlineKeyboardButton("➕ Queue Next", callback_data=f"queue_add:{video_id}:{title}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await message.reply_text("More audio?", reply_markup=reply_markup)

    except ValueError as e:
        await update_or_query.message.reply_text(f"⚠️ {str(e)}. Skipping...")
        await next_smart(chat_id, update_or_query, context)
    except Exception as e:
        logger.error(f"Play error: {e}")
        await update_or_query.message.reply_text('Audio play failed. Try another.')

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
        await update_or_query.message.reply_text("Queue empty. Add more with /play!")

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Play or queue audio from query/URL."""
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text('Usage: /play <query or YouTube URL>')
        return

    arg = ' '.join(context.args)
    if 'youtube.com/watch?v=' in arg or 'youtu.be/' in arg:
        # Extract video_id from URL
        match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', arg)
        if match:
            video_id = match.group(1)
            title = f"Direct Audio {video_id}"
        else:
            await update.message.reply_text('Invalid YouTube URL.')
            return
    else:
        # Search top 1
        try:
            search_response = youtube.search().list
