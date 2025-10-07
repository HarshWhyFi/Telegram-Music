questions = [
    {
        "question": "What is the capital of France?",
        "options": ["Paris", "London", "Berlin", "Rome"],
        "answer": "Paris"
    },
    {
        "question": "Who wrote 'Hamlet'?",
        "options": ["Shakespeare", "Dickens", "Tolkien", "Hemingway"],
        "answer": "Shakespeare"
    },
    {
        "question": "What is 2 + 2?",
        "options": ["3", "4", "5", "6"],
        "answer": "4"
    },
    {
        "question": "Which planet is known as the Red Planet?",
        "options": ["Mars", "Venus", "Jupiter", "Saturn"],
        "answer": "Mars"
    },
    {
        "question": "What is the largest ocean on Earth?",
        "options": ["Pacific", "Atlantic", "Indian", "Arctic"],
        "answer": "Pacific"
    },

    # BTech-related questions
    {
        "question": "Which programming language is widely used for Android app development?",
        "options": ["Java", "Python", "C++", "PHP"],
        "answer": "Java"
    },
    {
        "question": "What does CPU stand for in computer engineering?",
        "options": ["Central Processing Unit", "Control Program Unit", "Computer Processing Unit", "Central Program Unit"],
        "answer": "Central Processing Unit"
    },
    {
        "question": "Which data structure uses FIFO (First In First Out)?",
        "options": ["Queue", "Stack", "Tree", "Graph"],
        "answer": "Queue"
    },
    {
        "question": "In networking, what does LAN stand for?",
        "options": ["Local Area Network", "Large Area Network", "Light Access Network", "Linked Array Network"],
        "answer": "Local Area Network"
    },
    {
        "question": "Which logic gate outputs HIGH only when both inputs are HIGH?",
        "options": ["AND", "OR", "XOR", "NOT"],
        "answer": "AND"
    }
]

def get_question(index):
    return questions[index % len(questions)]
