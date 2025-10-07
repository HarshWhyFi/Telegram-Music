from telegram import Update
from telegram.ext import CommandHandler, Application, ContextTypes
from utils import is_admin, log_action, get_user_history
import asyncio

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("❌ Only admins!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /mute <user_id> <seconds>")
        return
    try:
        user_id = int(context.args[0])
        seconds = int(context.args[1])
        await update.effective_chat.restrict_member(user_id, can_send_messages=False)
        await update.message.reply_text(f"✅ User {user_id} muted for {seconds} seconds")
        await log_action(user_id, "mute", update.effective_chat.id, seconds)
        await asyncio.sleep(seconds)
        await update.effective_chat.restrict_member(user_id, can_send_messages=True)
        await update.message.reply_text(f"✅ User {user_id} unmuted")
        await log_action(user_id, "unmute", update.effective_chat.id)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("❌ Only admins!")
        return
    if not context.args:
        await update.message.reply_text("Usage: /unmute <user_id>")
        return
    try:
        user_id = int(context.args[0])
        await update.effective_chat.restrict_member(user_id, can_send_messages=True)
        await update.message.reply_text(f"✅ User {user_id} unmuted")
        await log_action(user_id, "unmute", update.effective_chat.id)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("❌ Only admins!")
        return
    if not context.args:
        await update.message.reply_text("Usage: /kick <user_id>")
        return
    try:
        user_id = int(context.args[0])
        await update.effective_chat.ban_member(user_id)
        await update.message.reply_text(f"✅ User {user_id} kicked")
        await log_action(user_id, "kick", update.effective_chat.id)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await kick(update, context)
    await log_action(int(context.args[0]), "ban", update.effective_chat.id)

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("❌ Only admins!")
        return
    if not context.args:
        await update.message.reply_text("Usage: /unban <user_id>")
        return
    try:
        user_id = int(context.args[0])
        await update.effective_chat.unban_member(user_id)
        await update.message.reply_text(f"✅ User {user_id} unbanned")
        await log_action(user_id, "unban", update.effective_chat.id)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def promote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("❌ Only admins!")
        return
    if not context.args:
        await update.message.reply_text("Usage: /promote <user_id>")
        return
    try:
        user_id = int(context.args[0])
        await update.effective_chat.promote_member(
            user_id,
            can_change_info=True,
            can_delete_messages=True,
            can_invite_users=True,
            can_pin_messages=True,
            can_manage_chat=True
        )
        await update.message.reply_text(f"✅ User {user_id} promoted to admin")
        await log_action(user_id, "promote", update.effective_chat.id)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def demote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("❌ Only admins!")
        return
    if not context.args:
        await update.message.reply_text("Usage: /demote <user_id>")
        return
    try:
        user_id = int(context.args[0])
        await update.effective_chat.promote_member(
            user_id,
            can_change_info=False,
            can_delete_messages=False,
            can_invite_users=False,
            can_pin_messages=False,
            can_manage_chat=False
        )
        await update.message.reply_text(f"✅ User {user_id} demoted")
        await log_action(user_id, "demote", update.effective_chat.id)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("❌ Only admins!")
        return
    if not context.args:
        await update.message.reply_text("Usage: /clear <count>")
        return
    try:
        count = int(context.args[0])
        messages = await update.effective_chat.get_history(limit=count)
        for msg in messages:
            await msg.delete()
        await update.message.reply_text(f"✅ Cleared last {count} messages")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("❌ Only admins!")
        return
    if not context.args:
        await update.message.reply_text("Usage: /history <user_id>")
        return
    try:
        user_id = int(context.args[0])
        rows = await get_user_history(user_id)
        if not rows:
            await update.message.reply_text("No history found for this user.")
            return
        text = "📜 User History:\n"
        for row in rows:
            action, chat_id, duration, timestamp = row
            duration_text = f" ({duration}s)" if duration else ""
            text += f"{timestamp} - {action} in chat {chat_id}{duration_text}\n"
        await update.message.reply_text(text)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

def register_moderation_commands(app: Application):
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("unmute", unmute))
    app.add_handler(CommandHandler("kick", kick))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("unban", unban))
    app.add_handler(CommandHandler("promote", promote))
    app.add_handler(CommandHandler("demote", demote))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CommandHandler("history", history))
