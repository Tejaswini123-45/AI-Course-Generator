import pytest


@pytest.fixture
def course_data() -> dict:
    question = {
        "question": "Which operation removes the last item?",
        "options": ["pop", "append", "extend", "copy"],
        "correct_answer": "pop",
        "explanation": "With no index supplied, pop removes the last item.",
    }
    return {
        "title": "Python lists",
        "description": "Practice storing and updating ordered collections.",
        "audience": "beginner",
        "learning_objectives": ["Create a list", "Append an item", "Remove an item"],
        "slides": [
            {
                "slide_number": number,
                "title": title,
                "content": "Apply the operation to a list of names.",
                "key_takeaway": "A list keeps items in order.",
            }
            for number, title in enumerate(
                ("Creation", "Indexing", "Adding items", "Removing items"), start=1
            )
        ],
        "quiz": [question.copy() for _ in range(3)],
    }
