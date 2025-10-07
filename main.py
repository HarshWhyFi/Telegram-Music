import os
import logging
from datetime import datetime
from random import choice
from telegram import Update, ChatMember
from telegram.ext import (
    ApplicationBuilder,
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
)
from dotenv import load_dotenv

# === LOAD ENV VARIABLES ===
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable not set!")

# === CONFIGURATION ===
WELCOME_IMAGES = ["1000050937.jpg", "welcome2.jpg", "welcome3.jpg"]
USER_LOG_FILE = "users_data.txt"

# === LOGGING SETUP ===
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === HELPER FUNCTIONS ===
def is_new_member(update: Update) -> bool:
    """Check if the user just joined the group."""
    change = update.chat_member.difference().get("status")
    return change and change[0] in [ChatMember.LEFT, ChatMember.KICKED] and change[1] == ChatMember.MEMBER

def escape_markdown(text: str) -> str:
    """Escape special Markdown characters."""
    escape_chars = "_*[]()~`>#+-=|{}.!"
    for char in escape_chars:
        text = text.replace(char, f"\\{char}")
    return text

# === WELCOME FUNCTION ===
async def send_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not is_new_member(update):
            return

        member = update.chat_member.new_chat_member
        user = member.user
        chat = update.chat_member.chat
        group_name = chat.title or "this group"

        # Pick a random welcome image
        image_path = choice(WELCOME_IMAGES)
        if not os.path.exists(image_path):
            logger.warning(f"Image not found: {image_path}")
            return

        # Escape user input for Markdown
        full_name = escape_markdown(user.full_name)
        username = escape_markdown(user.username) if user.username else "N/A"
        first_name = escape_markdown(user.first_name)

        welcome_text = f"""
╭──────────────────────────────╮
⚡ *WELCOME TO {escape_markdown(group_name.upper())}* ⚡
╰──────────────────────────────╯

🌿 *NAME*      : {full_name}
🌿 *USERNAME*  : @{username}
🌿 *USER ID*   : `{user.id}`
🌿 *MENTION*   : [{first_name}](tg://user?id={user.id})
🌿 *CHAT*      : {escape_markdown(group_name)}

╭──────────────────────────────╮
⚡ *THANKS FOR JOINING* ⚡
╰──────────────────────────────╯
"""

        # Send photo + message
        with open(image_path, "rb") as photo:
            await context.bot.send_photo(
                chat_id=chat.id,
                photo=photo,
                caption=welcome_text,
                parse_mode="Markdown"
            )

        # Store user info
        with open(USER_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(
                f"Name: {user.full_name}\n"
                f"Username: @{user.username if user.username else 'N/A'}\n"
                f"User ID: {user.id}\n"
                f"Chat: {group_name}\n"
                f"Joined At: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"{'-'*40}\n"
            )

        logger.info(f"✅ Welcomed {user.full_name} ({user.id}) in {group_name}")

    except Exception as e:
        logger.error(f"Error in send_welcome: {e}")

# === /id COMMAND ===
async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        chat = update.effective_chat
        reply_text = f"🆔 *Your Info:*\n• *User ID:* `{user.id}`\n• *Chat ID:* `{chat.id}`"
        await update.message.reply_text(reply_text, parse_mode="Markdown")
        logger.info(f"/id used by {user.full_name} ({user.id}) in {chat.title}")
    except Exception as e:
        logger.error(f"Error in /id command: {e}")

# === MAIN FUNCTION ===
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(ChatMemberHandler(send_welcome, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(CommandHandler("id", get_id))
    logger.info("🤖 Bot is running and ready!")
    app.run_polling()

if __name__ == "__main__":
    main()
