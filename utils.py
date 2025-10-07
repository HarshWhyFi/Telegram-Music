import aiosqlite
from telegram import Update

DB_FILE = "user.db"

async def is_admin(update: Update):
    try:
        user_id = update.effective_user.id
        member = await update.effective_chat.get_member(user_id)
        return member.status in ["administrator", "creator"]
    except:
        return False

async def log_action(user_id: int, action: str, chat_id: int, duration: int = None):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS user_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            chat_id INTEGER,
            duration INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)
        await db.execute(
            "INSERT INTO user_actions (user_id, action, chat_id, duration) VALUES (?, ?, ?, ?)",
            (user_id, action, chat_id, duration)
        )
        await db.commit()

async def get_user_history(user_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS user_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            chat_id INTEGER,
            duration INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor = await db.execute(
            "SELECT action, chat_id, duration, timestamp FROM user_actions WHERE user_id=? ORDER BY timestamp DESC",
            (user_id,)
        )
        rows = await cursor.fetchall()
        return rows
