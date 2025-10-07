import logging
import sqlite3
from telegram import Update, ChatMember
from telegram.ext import ApplicationBuilder, CommandHandler, ChatMemberHandler, ContextTypes

# === BOT TOKEN ===
BOT_TOKEN = "7688931396:AAFCDZNlkOuYPn2aWVqZN2GOaYDX73Yfn8A"

# === LOGGING ===
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === DATABASE ===
conn = sqlite3.connect("users.db", check_same_thread=False)
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    first_name TEXT,
    joined_times INTEGER DEFAULT 0
)
""")
conn.commit()

# === COMMANDS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    group_name = chat.title if chat.title else "this chat"
    await update.message.reply_text(
        f"Hey there {user.first_name}, and welcome to {group_name}! 👋\nHow are you today?"
    )

async def show_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    await update.message.reply_text(
        f"👤 Your ID: `{user.id}`\n💬 Chat ID: `{chat.id}`",
        parse_mode="Markdown"
    )

# === JOIN / LEAVE EVENTS ===
async def greet_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.chat_member
    chat = result.chat
    old_status = result.old_chat_member.status
    new_status = result.new_chat_member.status
    user = result.new_chat_member.user

    # User joined
    if old_status in ["left", "kicked"] and new_status == "member":
        user_id = user.id
        name = user.first_name

        cur.execute("SELECT joined_times FROM users WHERE user_id=?", (user_id,))
        data = cur.fetchone()

        if data:
            joined_times = data[0] + 1
            cur.execute("UPDATE users SET joined_times=? WHERE user_id=?", (joined_times, user_id))
            conn.commit()
            msg = f"🎉 Welcome back {name}! You've rejoined {chat.title or 'the group'} {joined_times} times!"
        else:
            cur.execute("INSERT INTO users (user_id, first_name, joined_times) VALUES (?, ?, ?)", (user_id, name, 1))
            conn.commit()
            msg = f"Hey there {name}, and welcome to {chat.title or 'the group'}! 💫"

        await chat.send_message(msg)

    # User left
    elif new_status in ["left", "kicked"]:
        name = result.old_chat_member.user.first_name
        await chat.send_message(f"👋 {name} has left {chat.title or 'the group'}.")

# === MAIN FUNCTION ===
def main():
    print("🚀 Bot starting...")
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", show_id))
    app.add_handler(ChatMemberHandler(greet_user, ChatMemberHandler.CHAT_MEMBER))

    print("✅ Bot running. Press Ctrl+C to stop.")
    app.run_polling()

if __name__ == "__main__":
    main()
