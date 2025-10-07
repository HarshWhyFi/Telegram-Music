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

# Replace with your actual tokens/keys
TELEGRAM_TOKEN = 'YOUR_TELEGRAM_BOT_TOKEN'
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
            f'I use your API key to fetch smart, personalized music. Let\'s play!\n\n'
            f'🔥 Top Trending:\n{rec_text}\n\n'
            'Commands: /search <query>, /play <url/query>, /history\n'
            'Inline: @yourbot <song or mood>',
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except HttpError as e:
        if e.resp.status in [403, 429]:
            await update.message.reply_text(f'API Error ({e.resp.status}): Check quota or key restrictions in Google Cloud.')
        else:
            logger.error(f"Trending error: {e}")
            await update.message.reply_text('Welcome! Use /search to start. (Trending fetch failed)')
    except Exception as e:
        logger.error(f"Start error: {e}")
        await update.message.reply_text('Welcome! Use /search <query> to get smart results.')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Enhanced help."""
    help_text = (
        "🧠 **Smart Music Bot Guide:**\n\n"
        "**Features:**\n"
        "- 🔍 **Intelligent Search**: Auto-fixes queries (e.g., 'sad mj' → Michael Jackson sad ballads). Shows top 5 only.\n"
        "- 🎯 **Recommendations**: 'More like this' based on YouTube related videos.\n"
        "- 📜 **History**: Track plays.\n"
        "- 📋 **Smart Queue**: Auto-skip failed streams; mood-based adds.\n"
        "- 💾 **Caching**: Saves API quota with 5-min cache.\n\n"
        "**Commands:**\n"
        "/start - Trending & menu\n"
        "/search <query> - Smart search with buttons (top 5)\n"
        "/play <url or query> - Add & play (with recs)\n"
        "/queue - View with controls\n"
        "/next - Skip smartly\n"
        "/history - Past plays\n"
        "/clear_queue - Reset\n\n"
        "**Inline Mode:** Type @yourbot <happy song> in any chat (top 5 results).\n\n"
        "**API Tip:** Your key is active—monitor usage at console.cloud.google.com!"
    )
    keyboard = [[InlineKeyboardButton("Test API", callback_data="test_api")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(help_text, reply_markup=reply_markup, parse_mode='Markdown')

async def test_api(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Test the provided API key."""
    try:
        response = youtube.search().list(q='test', part='id', maxResults=1).execute()
        await update.message.reply_text('✅ API Key Working! (Test search succeeded.)')
    except HttpError as e:
        error_msg = f'❌ API Error: {e.resp.status} - {e.resp.reason}\nCheck key, quotas, or enable YouTube Data API v3.'
        await update.message.reply_text(error_msg)

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE, is_inline: bool = False) -> None:
    """Smart search with caching, enhancements, and fuzzy fallback. Limited to top 5."""
    if is_inline:
        query_input = update.inline_query.query.strip()
        chat_id = None
    else:
        query_input = ' '.join(context.args)
        chat_id = update.effective_chat.id
        if not query_input:
            await update.message.reply_text('Provide a query, e.g., /search happy workout!')
            return
        await update.message.reply_text(f"🧠 Enhancing & searching for '{query_input}'...")

    if not query_input:
        return

    query = enhance_query(query_input)
    cache_key = f"search:{query}"

    if cache_key in search_cache:
        results = search_cache[cache_key]
        enhanced_note = " (from cache)"
    else:
        try:
            search_response = youtube.search().list(
                q=query,
                part='id,snippet',
                maxResults=5,  # Strictly top 5 for all
                type='video'
            ).execute()
            results = search_response['items']
            if results:
                search_cache[cache_key] = results
            else:
                # Fuzzy fallback, also top 5
                fuzzy_query = re.sub(r' official music video$', '', query) + ' lyrics audio'
                fuzzy_response = youtube.search().list(q=fuzzy_query, part='id,snippet', maxResults=5, type='video').execute()
                results = fuzzy_response['items']
                enhanced_note = " (smart fuzzy match!)"
                if results:
                    search_cache[cache_key] = results

        except HttpError as e:
            if e.resp.status in [403, 429]:
                msg = 'API quota exceeded or forbidden. Wait or check key.'
                if not is_inline:
                    await update.message.reply_text(msg)
                return
            raise
        except Exception as e:
            logger.error(f"Search error: {e}")
            if not is_inline:
                await update.message.reply_text('Search failed—try a simpler query or check API.')
            return

    if not results:
        if not is_inline:
            await update.message.reply_text(f'No results for "{query_input}". Try a different mood/artist!')
        return

    enhanced_note = enhanced_note if 'enhanced_note' in locals() else ''
    if not is_inline:
        # Display top 5 with buttons
        keyboard = []
        for item in results[:5]:  # Ensure only 5
            title = item['snippet']['title'][:40] + '...' if len(item['snippet']['title']) > 40 else item['snippet']['title']
            video_id = item['id']['videoId']
            callback_data = f"smart_play:{video_id}:{title}"
            keyboard.append([InlineKeyboardButton(title, callback_data=callback_data)])

        if len(results) >= 1:
            keyboard.append([InlineKeyboardButton("🎯 Add Recs to Queue", callback_data=f"rec_queue:{results[0]['id']['videoId']}:{query_input}")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"🧠 Top 5 smart results for '{query_input}'{enhanced_note}:\nPick one!", reply_markup=reply_markup)
    else:
        # Inline: Top 5 with thumbnails
        inline_results = []
        for item in results[:5]:  # Limit to top 5
            title = item['snippet']['title']
            video_id = item['id']['videoId']
            link = f"https://www.youtube.com/watch?v={video_id}"
            description = item['snippet']['description'][:80] + '...'
            thumb_url = item['snippet'].get('thumbnails', {}).get('medium', {}).get('url', '')

            inline_results.append(
                InlineQueryResultArticle(
                    id=video_id,
                    title=title,
                    description=description + f' (Smart: {query_input})',
                    thumb_url=thumb_url,
                    input_message_content=InputTextMessageContent(f"🎵 {title}\n{link}"),
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🧠 Smart Play", callback_data=f"smart_play:{video_id}:{title}")]])
                )
            )
        await update.inline_query.answer(inline_results, cache_time=60, is_personal=True)

async def inline_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inline handler."""
    await search(update, context, is_inline=True)

def get_audio_url(video_url: str) -> tuple[str, str]:
    """Extract audio with smart size/duration checks."""
    try:
        ydl_opts = {
            'format': 'bestaudio/best[filesize<50M]/bestaudio[ext=m4a]/bestaudio',
            'quiet': True,
            'no_warnings': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            if not info.get('url') or info.get('duration', 0) > 3600:  # Skip >1hr videos
                raise ValueError("Audio too long or unavailable.")
            return info['url'], info.get('title', 'Unknown')
    except Exception as e:
        logger.error(f"yt-dlp error: {e}")
        raise ValueError("Stream failed—video may be restricted or private.")

async def smart_play(chat_id: int, video_id: str, title: str, update_or_query, context: ContextTypes.DEFAULT_TYPE, recommend_after: bool = True) -> None:
    """Smart play: Stream, add to history, auto-skip on fail."""
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        await update_or_query.message.reply_text(f"🎧 Preparing smart stream for '{title}'...")

        audio_url, actual_title = get_audio_url(video_url)

        # Send as audio
        message = await update_or_query.message.reply_audio(
            audio=audio_url,
            title=actual_title or title,
            performer="Smart Music Bot",
            caption=f"🎵 {title}\n🧠 Powered by YouTube API",
            duration=0  # Auto-detect
        )

        # Update state
        current_playing[chat_id] = {'video_id': video_id, 'title': title}
        history.setdefault(chat_id, []).append({'video_id': video_id, 'title': title})
        if len(history[chat_id]) > 50:  # Limit
            history[chat_id].pop(0)

        # Recommendations
        if recommend_after:
            keyboard = [
                [InlineKeyboardButton("🎯 More Like This", callback_data=f"recommend:{video_id}:{title}")],
                [InlineKeyboardButton("➕ Add to Queue", callback_data=f"queue_add:{video_id}:{title}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await message.reply_text("Enjoying? Get smart suggestions!", reply_markup=reply_markup)

    except ValueError as e:
        error_msg = f"⚠️ {str(e)}. Auto-skipping to next..."
        await update_or_query.message.reply_text(error_msg)
        await next_smart(chat_id, update_or_query, context)
    except Exception as e:
        logger.error(f"Smart play error: {e}")
        await update_or_query.message.reply_text('Play failed—try another video.')

async def get_recommendations(related_video_id: str, orig_query: str, max_results: int = 3) -> List[Dict]:
    """Fetch related videos for recommendations."""
    try:
        rec_response = youtube.search().list(
            part='id,snippet',
            maxResults=max_results,
            relatedToVideoId=related_video_id,
            type='video',
            q=orig_query  # Refine with original query
        ).execute()
        return rec_response['items']
    except Exception:
        # Fallback: General search
        fallback_response = youtube.search().list(q=orig_query + ' similar', part='id,snippet', maxResults=max_results, type='video').execute()
        return fallback_response['items']

async def next_smart(chat_id: int, update_or_query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Smart next: Pop queue and play, or suggest if empty."""
    queue = queues.get(chat_id, [])
    if queue:
        next_song = queue.pop(0)
        queues[chat_id] = queue  # Update
        await smart_play(chat_id, next_song['video_id'], next_song['title'], update_or_query, context)
    else:
        await update_or_query.message.reply_text("No more songs in queue. Try /search for more!")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Enhanced button handler with smart logic."""
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat_id

    if data == "trending":
        await start(update, context)  # Refresh
        await query.edit_message_text("🔥 Trending refreshed!")
    elif data == "history":
        hist = history.get(chat_id, [])
        if not hist:
            await query.edit_message_text("No play history yet. Play something first!")
        else:
            msg = "📜 Your Smart History (last 5):\n" + "\n".join([f"• {song['title']}" for song in hist[-5:]])
            if hist:
                last_song = hist[-1]
                keyboard = [[InlineKeyboardButton("🎯 Recs from History", callback_data=f"recommend:{last_song['video_id']}:{last_song['title']}")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
            else:
                reply_markup = None
            await query.edit_message_text(msg, reply_markup=reply_markup)
    elif data == "search_menu":
        await query.edit_message_text("Type /search <your mood or song> for top 5 smart results! E.g., /search party taylor")
    elif data == "help":
        await help_command(update, context)
        await query.delete_message()
    elif data == "test_api":
        await test_api(update, context)
        await query.delete_message()
    elif data.startswith("smart_play:"):
        _, video_id, title = data.split(":", 2)
        await smart_play(chat_id, video_id, title, query, context)
        await query.edit_message_text(f"✅ Smartly playing '{title}'!")
    elif data.startswith("recommend:"):
        _, video_id, orig_query = data.split(":", 2)
        recs = await get_recommendations(video_id, orig_query)
        if recs:
            keyboard = []
            for item in recs:
                r_title = item['snippet']['title'][:30] + '...' if len(item['snippet']['title']) > 30 else item['snippet']['title']
                r_id = item['id']['videoId']
               
