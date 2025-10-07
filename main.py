# === TERMUX TIMEZONE FIX ===
import pytz
import os
os.environ["TZ"] = "UTC"

# === STANDARD IMPORTS ===
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
)

# === CONFIGURATION ===
BOT_TOKEN = "7688931396:AAFCDZNlkOuYPn2aWVqZN2GOaYDX73Yfn8A"   # 🔹 Replace with your bot token
WELCOME_IMAGE = "IMG_20251003_154503.png"    # 🔹 Your welcome image file path
USER_LOG_FILE = "users_data.txt"    # 🔹 Text file for storing user info

# === LOGGING SETUP ===
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# === WELCOME FUNCTION ===
async def send_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        member = update.chat_member.new_chat_member
        user = member.user
        chat = update.chat_member.chat

        # Only trigger when a new member joins
        if member.status == "member":
            group_name = chat.title or "this group"

            # Styled welcome message
            welcome_text = f"""
╭──────────────────────────────╮
⚡ *WELCOME TO {group_name.upper()}* ⚡
╰──────────────────────────────╯

🌿 *NAME*      : {user.full_name}
🌿 *USERNAME*  : @{user.username if user.username else 'N/A'}
🌿 *USER ID*   : `{user.id}`
🌿 *MENTION*   : [{user.first_name}](tg://user?id={user.id})
🌿 *CHAT*      : {group_name}

╭──────────────────────────────╮
⚡ *THANKS FOR JOINING* ⚡
╰──────────────────────────────╯
"""

            # Send photo + welcome message
            await context.bot.send_photo(
                chat_id=chat.id,
                photo=open(WELCOME_IMAGE, "rb"),
                caption=welcome_text,
                parse_mode="Markdown"
            )

            # Store user data
            with open(USER_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(
                    f"Name: {user.full_name}\n"
                    f"Username: @{user.username if user.username else 'N/A'}\n"
                    f"User ID: {user.id}\n"
                    f"Chat: {group_name}\n"
                    f"Joined At: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"{'-'*40}\n"
                )

            logger.info(f"✅ Welcomed and saved {user.full_name} ({user.id}) in {group_name}")

    except Exception as e:
        logger.error(f"Error sending welcome: {e}")


# === /id COMMAND ===
async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    reply_text = f"""
🆔 *Your Info:*
• *User ID:* `{user.id}`
• *Chat ID:* `{chat.id}`
"""

    await update.message.reply_text(reply_text, parse_mode="Markdown")
    logger.info(f"/id command used by {user.full_name} ({user.id}) in {chat.title}")


# === MAIN FUNCTION ===
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(ChatMemberHandler(send_welcome, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(CommandHandler("id", get_id))

    logger.info("🤖 Infinity Bot is running and ready to welcome new members!")
    app.run_polling()


if __name__ == "__main__":
    main()
