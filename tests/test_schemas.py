import pytest
from pydantic import ValidationError

from app.schemas import Course


def test_accepts_valid_course(course_data: dict) -> None:
    assert Course.model_validate(course_data).model_dump() == course_data


@pytest.mark.parametrize("field", ["learning_objectives", "slides", "quiz"])
def test_rejects_wrong_counts(course_data: dict, field: str) -> None:
    course_data[field].pop()
    with pytest.raises(ValidationError):
        Course.model_validate(course_data)


def test_rejects_out_of_order_slides(course_data: dict) -> None:
    course_data["slides"].reverse()
    with pytest.raises(ValidationError, match="sequential"):
        Course.model_validate(course_data)


@pytest.mark.parametrize("answer", ["remove", "Pop"])
def test_rejects_invalid_quiz_answer(course_data: dict, answer: str) -> None:
    course_data["quiz"][0]["correct_answer"] = answer
    with pytest.raises(ValidationError, match="exactly match"):
        Course.model_validate(course_data)
