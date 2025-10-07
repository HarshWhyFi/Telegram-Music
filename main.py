import logging
import sqlite3
from telegram import Update, ChatMember, ChatMemberUpdated
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    ChatMemberHandler,
)
import os
from dotenv import load_dotenv

# === Load environment variables ===
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

# === Logging ===
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# === Database setup ===
def init_db():
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER,
            chat_id INTEGER,
            username TEXT,
            first_joined INTEGER DEFAULT 1
        )"""
    )
    conn.commit()
    conn.close()

def user_exists(user_id, chat_id):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=? AND chat_id=?", (user_id, chat_id))
    data = c.fetchone()
    conn.close()
    return data

def add_or_update_user(user_id, chat_id, username):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    if user_exists(user_id, chat_id):
        c.execute("UPDATE users SET first_joined = 0 WHERE user_id=? AND chat_id=?", (user_id, chat_id))
    else:
        c.execute("INSERT INTO users (user_id, chat_id, username, first_joined) VALUES (?, ?, ?, 1)",
                  (user_id, chat_id, username))
    conn.commit()
    conn.close()

def remove_user(user_id, chat_id):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE user_id=? AND chat_id=?", (user_id, chat_id))
    conn.commit()
    conn.close()

# === Commands ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    add_or_update_user(user.id, chat.id, user.username)

    chat_name = chat.title if chat.title else "this chat"
    message = f"🎉 Hey there {user.first_name}, and welcome to *{chat_name}*! How are you?"
    await update.message.reply_text(message, parse_mode="Markdown")

async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    await update.message.reply_text(
        f"👤 **Your ID:** `{user.id}`\n💬 **Chat ID:** `{chat.id}`",
        parse_mode="Markdown"
    )

# === Chat Member Updates ===
async def track_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.chat_member
    member = result.new_chat_member
    chat = update.effective_chat

    user_id = member.user.id
    username = member.user.username or member.user.first_name
    chat_name = chat.title or "this chat"

    if member.status == ChatMember.MEMBER:  # User joined
        existed = user_exists(user_id, chat.id)
        add_or_update_user(user_id, chat.id, username)
        if existed:
            msg = f"👋 Welcome back, {member.user.first_name}! Glad to see you again in *{chat_name}*."
        else:
            msg = f"🎉 Hey there {member.user.first_name}, and welcome to *{chat_name}*! How are you?"
        await context.bot.send_message(chat.id, msg, parse_mode="Markdown")

    elif member.status in [ChatMember.LEFT, ChatMember.KICKED]:  # User left
        remove_user(user_id, chat.id)
        logger.info(f"User {username} left {chat_name}")

# === Main ===
def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", id_command))
    app.add_handler(ChatMemberHandler(track_members, ChatMemberHandler.CHAT_MEMBER))

    logger.info("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
