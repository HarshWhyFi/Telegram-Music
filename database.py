import sqlite3

DB_NAME = "data.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS results (
            user_id INTEGER,
            username TEXT,
            question TEXT,
            selected_option TEXT,
            correct INTEGER
        )
    """)
    conn.commit()
    conn.close()

def save_result(user_id, username, question, selected_option, correct):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO results (user_id, username, question, selected_option, correct)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, username, question, selected_option, correct))
    conn.commit()
    conn.close()

def get_question_stats(question):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM results WHERE question=? AND correct=1", (question,))
    correct = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM results WHERE question=? AND correct=0", (question,))
    wrong = cursor.fetchone()[0]
    conn.close()
    return correct, wrong
