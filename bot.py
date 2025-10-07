import asyncio
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes
from config import TELEGRAM_TOKEN, GROUP_CHAT_ID
from questions import get_question
from database import save_result, get_question_stats

class QuizBot:
    def __init__(self):
        self.bot = Bot(token=TELEGRAM_TOKEN)
        self.index = 0
        self.current_question = None

    async def start_quiz(self):
        while True:
            self.current_question = get_question(self.index)
            question_text = self.current_question["question"]
            options = self.current_question["options"]

            # Buttons
            buttons = [[InlineKeyboardButton(opt, callback_data=opt)] for opt in options]
            reply_markup = InlineKeyboardMarkup(buttons)

            await self.bot.send_message(chat_id=GROUP_CHAT_ID, text=question_text, reply_markup=reply_markup)
            self.index += 1
            await asyncio.sleep(60)  # every 1 min

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    username = query.from_user.username or query.from_user.first_name
    selected = query.data
    question_text = context.bot_data.get("current_question_text", query.message.text)
    
    # Check correct answer
    correct_answer = context.bot_data.get("current_correct_answer")
    is_correct = int(selected == correct_answer)

    # Save to DB
    from database import save_result, get_question_stats
    save_result(user_id, username, question_text, selected, is_correct)

    # Get stats
    correct_count, wrong_count = get_question_stats(question_text)
    
    await query.edit_message_text(
        f"Question: {question_text}\n"
        f"You selected: {selected}\n"
        f"Correct: {correct_answer}\n"
        f"✅ Correct answers: {correct_count}\n"
        f"❌ Wrong answers: {wrong_count}"
    )
