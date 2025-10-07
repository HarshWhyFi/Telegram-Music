import asyncio
from bot import QuizBot, button_handler
from database import init_db
from telegram.ext import Application, CallbackQueryHandler
from config import TELEGRAM_TOKEN

async def main():
    init_db()
    quiz_bot = QuizBot()
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CallbackQueryHandler(button_handler))

    # Store current question info for button handler
    async def update_current_question():
        while True:
            if quiz_bot.current_question:
                app.bot_data["current_question_text"] = quiz_bot.current_question["question"]
                app.bot_data["current_correct_answer"] = quiz_bot.current_question["answer"]
            await asyncio.sleep(1)
    
    asyncio.create_task(quiz_bot.start_quiz())
    asyncio.create_task(update_current_question())
    
    print("Quiz bot started...")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
