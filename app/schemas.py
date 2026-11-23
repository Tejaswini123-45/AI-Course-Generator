"""Validated inputs and reusable output models."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.config import MAX_TEXT_LENGTH

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Content = Annotated[Text, StringConstraints(max_length=MAX_TEXT_LENGTH)]
Topic = Annotated[Text, StringConstraints(max_length=300)]
Instruction = Annotated[Text, StringConstraints(max_length=2000)]
Audience = Literal["beginner", "intermediate", "advanced"]
QuestionCount = Annotated[int, Field(strict=True, ge=1, le=10)]


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class CourseRequest(StrictModel):
    content: Content
    audience: Audience


class SlideUpdate(StrictModel):
    title: Text
    content: Text
    key_takeaway: Text


class Slide(SlideUpdate):
    slide_number: int = Field(ge=1, le=4)


class QuizQuestion(StrictModel):
    question: Text
    options: list[Text] = Field(min_length=4, max_length=4)
    correct_answer: Text
    explanation: Text

    @model_validator(mode="after")
    def check_options(self) -> Self:
        if len({option.casefold() for option in self.options}) != 4:
            raise ValueError("Quiz options must be distinct.")
        if self.correct_answer not in self.options:
            raise ValueError("The correct answer must exactly match one option.")
        return self


class Quiz(StrictModel):
    questions: list[QuizQuestion] = Field(min_length=1, max_length=10)


class Course(StrictModel):
    title: Text
    description: Text
    audience: Audience
    learning_objectives: list[Text] = Field(min_length=3, max_length=3)
    slides: list[Slide] = Field(min_length=4, max_length=4)
    quiz: list[QuizQuestion] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def check_slide_order(self) -> Self:
        if [slide.slide_number for slide in self.slides] != [1, 2, 3, 4]:
            raise ValueError("Slide numbers must be sequential from 1 to 4.")
        return self
