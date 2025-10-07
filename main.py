from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from management import register_management_commands
from moderation import register_moderation_commands

# ✅ Replace with your actual bot token
TELEGRAM_TOKEN = "YOUR_BOT_TOKEN_HERE"

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hello! I am your Group Manager Bot.\nUse /help to see commands."
    )

# /help command
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

# Main function to start the bot
def main():
    # Build the async application
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Register core commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))

    # Register management & moderation commands
    register_management_commands(app)
    register_moderation_commands(app)

    print("Bot started...")
    app.run_polling()  # Start polling updates

# Run the bot
if __name__ == "__main__":
    main()
