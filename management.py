from telegram import Update
from telegram.ext import CommandHandler, Application, ContextTypes
from utils import is_admin

async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("❌ Only admins!")
        return
    await update.message.reply_text("👋 Welcome to the group!")

async def group_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("❌ Only admins!")
        return
    chat = update.effective_chat
    await update.message.reply_text(
        f"Group Name: {chat.title}\nID: {chat.id}\nMembers: {chat.get_members_count()}"
    )

async def pin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("❌ Only admins!")
        return
    if not context.args:
        await update.message.reply_text("Usage: /pin <message_id>")
        return
    try:
        message_id = int(context.args[0])
        await update.effective_chat.pin_message(message_id)
        await update.message.reply_text(f"📌 Message {message_id} pinned")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def unpin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("❌ Only admins!")
        return
    await update.effective_chat.unpin_all_messages()
    await update.message.reply_text("📌 All messages unpinned")

async def show_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    await update.message.reply_text(f"👤 Your User ID: {user_id}\n💬 Chat ID: {chat_id}")

def register_management_commands(app: Application):
    app.add_handler(CommandHandler("welcome", welcome))
    app.add_handler(CommandHandler("groupinfo", group_info))
    app.add_handler(CommandHandler("pin", pin))
    app.add_handler(CommandHandler("unpin", unpin))
    app.add_handler(CommandHandler("id", show_id))
