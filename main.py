import os
import logging
import sqlite3
import pytz
from datetime import datetime
from telegram import Update, ChatMember
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    ChatMemberHandler,
)

# === FIX TERMUX TIMEZONE BUG ===
os.environ["TZ"] = "UTC"

# === BOT TOKEN ===
BOT_TOKEN = "7688931396:AAFCDZNlkOuYPn2aWVqZN2GOaYDX73Yfn8A"

# === LOGGING ===
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# === DATABASE ===
DB_FILE = "users.db"
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cur = conn.cursor()
cur.execute(
    """CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        first_name TEXT,
        joined_times INTEGER DEFAULT 0
    )"""
)
conn.commit()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Respond to /start command."""
    user = update.effective_user
    chat = update.effective_chat
    await update.message.reply_text(
        f"Hey there {user.first_name}, and welcome to {chat.title or 'this chat'}! 👋\nHow are you today?"
    )


async def show_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user and chat ID."""
    user = update.effective_user
    chat = update.effective_chat
    await update.message.reply_text(
        f"👤 Your ID: `{user.id}`\n💬 Chat ID: `{chat.id}`",
        parse_mode="Markdown",
    )


async def greet_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome or farewell when members join/leave."""
    result = update.chat_member
    chat = result.chat
    new = result.new_chat_member
    old = result.old_chat_member

    # User joined
    if old.status in ["left", "kicked"] and new.status == "member":
        user_id = new.user.id
        name = new.user.first_name

        cur.execute("SELECT joined_times FROM users WHERE user_id=?", (user_id,))
        row = cur.fetchone()

        if row:
            joined_times = row[0] + 1
            cur.execute(
                "UPDATE users SET joined_times=? WHERE user_id=?", (joined_times, user_id)
            )
            conn.commit()
            msg = f"🎉 Welcome back {name}! You've rejoined {chat.title or 'the group'} {joined_times} times!"
        else:
            cur.execute(
                "INSERT INTO users (user_id, first_name, joined_times) VALUES (?, ?, ?)",
                (user_id, name, 1),
            )
            conn.commit()
            msg = f"Hey there {name}, and welcome to {chat.title or 'the group'}! 💫"

        await chat.send_message(msg)

    # User left
    elif new.status in ["left", "kicked"]:
        name = old.user.first_name
        await chat.send_message(f"👋 {name} has left {chat.title or 'the group'}.")


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", show_id))

    # Join/Leave events
    app.add_handler(ChatMemberHandler(greet_user, ChatMemberHandler.CHAT_MEMBER))

    print("✅ Bot is running... Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
