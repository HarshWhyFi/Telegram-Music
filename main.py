from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from management import register_management_commands
from moderation import register_moderation_commands

TELEGRAM_TOKEN = "7938834721:AAFj6sUtlCfH0VPVzUFspINeIrN65goNTLw"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hello! I am your Group Manager Bot.\nUse /help to see commands."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
📌 Admin Commands:
/welcome - Send welcome message
/groupinfo - Get group info
/pin <message_id> - Pin message
/unpin - Unpin all
/id - Show your User ID and Chat ID
/mute <user_id> <seconds> - Mute user
/unmute <user_id> - Unmute user
/kick <user_id> - Kick user
/ban <user_id> - Ban user
/unban <user_id> - Unban user
/promote <user_id> - Promote to admin
/demote <user_id> - Demote admin
/clear <count> - Delete messages
/history <user_id> - Show user actions
    """
    await update.message.reply_text(help_text)

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))

    register_management_commands(app)
    register_moderation_commands(app)

    print("Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()
