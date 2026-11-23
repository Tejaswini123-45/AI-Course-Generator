"""Synchronous Gemini generation used by both application interfaces."""

import json
from collections.abc import Callable
from time import sleep

import httpx
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

from app.config import gemini_settings
from app.schemas import (
    Audience,
    Content,
    Course,
    Instruction,
    QuestionCount,
    Quiz,
    SlideUpdate,
    Topic,
)
from app.services import prompts


class GenerationError(Exception):
    """A request failed before a validated result could be returned."""


class QuotaError(GenerationError):
    """Gemini rejected the request because of a quota or rate limit."""


class InvalidOutputError(GenerationError):
    """Gemini failed to produce valid output within the retry limit."""


def _generate[Result: BaseModel](
    schema: type[Result],
    instructions: str,
    data: dict[str, str | int],
    matches_request: Callable[[Result], bool] | None = None,
) -> Result:
    api_key, model = gemini_settings()
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_json_schema=schema.model_json_schema(),
        system_instruction=f"{instructions}\n{prompts.SOURCE_BOUNDARY}",
    )
    payload = json.dumps(data, ensure_ascii=False)
    try:
        with (
            httpx.Client(timeout=30) as transport,
            genai.Client(
                api_key=api_key,
                vertexai=False,
                http_options=types.HttpOptions(
                    api_version="v1beta",
                    httpx_client=transport,
                    timeout=30_000,
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            ) as client,
        ):
            for attempt in range(2):
                try:
                    response = client.models.generate_content(
                        model=model, contents=payload, config=config
                    )
                except errors.APIError as exc:
                    if attempt == 0 and exc.code == 503 and exc.status != "RESOURCE_EXHAUSTED":
                        sleep(1)
                        continue
                    raise
                try:
                    result = schema.model_validate_json(response.text or "")
                except ValidationError:
                    pass
                else:
                    if matches_request is None or matches_request(result):
                        return result
                if attempt == 0:
                    payload += (
                        "\nRetry with valid JSON that satisfies every requested constraint."
                    )
    except errors.APIError as exc:
        if exc.code == 429 or exc.status == "RESOURCE_EXHAUSTED":
            raise QuotaError("Gemini quota exceeded. Try again later.") from None
        if exc.code == 503 or exc.status == "UNAVAILABLE":
            raise GenerationError(
                "Gemini is temporarily unavailable (upstream HTTP 503). "
                "Try again shortly."
            ) from None
        raise GenerationError(
            "Gemini rejected the request or is unavailable. Check the model and API key."
        ) from None
    except httpx.TransportError:
        raise GenerationError("Could not reach Gemini. Try again later.") from None
    raise InvalidOutputError("Gemini returned invalid output within the two-attempt limit.")


def generate_course(topic: Topic, audience: Audience) -> Course:
    return _generate(
        Course, prompts.COURSE, {"topic": topic, "audience": audience},
        lambda course: course.audience == audience,
    )


def generate_course_from_content(content: Content, audience: Audience) -> Course:
    return _generate(
        Course, prompts.COURSE, {"material": content, "audience": audience},
        lambda course: course.audience == audience,
    )


def generate_quiz(content: Content, num_questions: QuestionCount) -> Quiz:
    return _generate(
        Quiz, prompts.QUIZ, {"material": content, "num_questions": num_questions},
        lambda quiz: len(quiz.questions) == num_questions,
    )


def update_slide(slide_content: Content, instruction: Instruction) -> SlideUpdate:
    return _generate(
        SlideUpdate, prompts.SLIDE,
        {"slide_content": slide_content, "instruction": instruction},
    )
