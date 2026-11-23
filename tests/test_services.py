import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from google.genai import errors

from app.config import ConfigurationError
from app.schemas import Course
from app.services import gemini


@pytest.fixture
def sdk(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    monkeypatch.setattr(gemini, "gemini_settings", lambda: ("test-key", "test-model"))
    constructor = MagicMock()
    monkeypatch.setattr(gemini.genai, "Client", constructor)
    return constructor.return_value.__enter__.return_value.models.generate_content


def test_course_retries_invalid_output(sdk: MagicMock, course_data: dict) -> None:
    sdk.side_effect = [
        SimpleNamespace(text="invalid JSON"),
        SimpleNamespace(text=json.dumps(course_data)),
    ]
    assert gemini.generate_course("Python lists", "beginner") == Course(**course_data)
    assert sdk.call_count == 2
    kwargs = sdk.call_args_list[0].kwargs
    assert kwargs["model"] == "test-model"
    assert json.loads(kwargs["contents"])["topic"] == "Python lists"
    assert kwargs["config"].response_mime_type == "application/json"
    assert kwargs["config"].response_json_schema == Course.model_json_schema()


def test_official_sdk_serializes_schema_and_parses_response(
    monkeypatch: pytest.MonkeyPatch, course_data: dict
) -> None:
    monkeypatch.setattr(gemini, "gemini_settings", lambda: ("test-key", "test-model"))
    client_type = httpx.Client

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1beta/models/test-model:generateContent"
        body = json.loads(request.content)
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        assert body["generationConfig"]["responseJsonSchema"]["title"] == "Course"
        assert json.loads(body["contents"][0]["parts"][0]["text"])["topic"] == "Lists"
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": json.dumps(course_data)}]}}
                ]
            },
        )

    def mock_client(**kwargs: object) -> httpx.Client:
        return client_type(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(gemini.httpx, "Client", mock_client)
    assert gemini.generate_course("Lists", "beginner") == Course(**course_data)


def test_retry_stops_after_two_attempts(sdk: MagicMock) -> None:
    sdk.return_value = SimpleNamespace(text=None)
    with pytest.raises(gemini.InvalidOutputError):
        gemini.generate_course_from_content("Lists keep order.", "beginner")
    assert sdk.call_count == 2


def test_quiz_checks_requested_count(sdk: MagicMock, course_data: dict) -> None:
    sdk.side_effect = [
        SimpleNamespace(text=json.dumps({"questions": course_data["quiz"]})),
        SimpleNamespace(text=json.dumps({"questions": course_data["quiz"][:1]})),
    ]
    assert len(gemini.generate_quiz("Lists keep order.", 1).questions) == 1
    assert sdk.call_count == 2


def test_slide_update(sdk: MagicMock) -> None:
    data = {"title": "Lists", "content": "Store items in order.", "key_takeaway": "Use []."}
    sdk.return_value = SimpleNamespace(text=json.dumps(data))
    assert gemini.update_slide("Lists are ordered.", "Simplify").model_dump() == data


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (errors.ClientError(429, {"message": "secret"}), gemini.QuotaError),
        (errors.ServerError(503, {"status": "RESOURCE_EXHAUSTED"}), gemini.QuotaError),
        (errors.ClientError(400, {"status": "INVALID_ARGUMENT"}), gemini.GenerationError),
        (errors.ClientError(403, {"message": "secret"}), gemini.GenerationError),
        (httpx.ConnectError("secret"), gemini.GenerationError),
    ],
)
def test_provider_errors_are_sanitized(
    sdk: MagicMock, failure: Exception, expected: type[Exception]
) -> None:
    sdk.side_effect = failure
    with pytest.raises(expected) as caught:
        gemini.generate_course("Lists", "beginner")
    assert "secret" not in str(caught.value)
    sdk.assert_called_once()


def test_missing_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GEMINI_MODEL", "")
    with pytest.raises(ConfigurationError):
        gemini.generate_course("Lists", "beginner")


def test_provider_unavailability_retries_successfully(
    sdk: MagicMock, monkeypatch: pytest.MonkeyPatch, course_data: dict
) -> None:
    delay = MagicMock()
    monkeypatch.setattr(gemini, "sleep", delay)
    sdk.side_effect = [
        errors.ServerError(503, {"status": "UNAVAILABLE"}),
        SimpleNamespace(text=json.dumps(course_data)),
    ]
    assert gemini.generate_course("Lists", "beginner") == Course(**course_data)
    assert sdk.call_count == 2
    assert sdk.call_args_list[0] == sdk.call_args_list[1]
    delay.assert_called_once_with(1)


def test_provider_unavailability_stops_after_two_attempts(
    sdk: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    delay = MagicMock()
    monkeypatch.setattr(gemini, "sleep", delay)
    sdk.side_effect = errors.ServerError(
        503, {"status": "UNAVAILABLE", "message": "private upstream details"}
    )
    with pytest.raises(gemini.GenerationError, match="upstream HTTP 503") as caught:
        gemini.generate_course("Lists", "beginner")
    assert "private upstream details" not in str(caught.value)
    assert sdk.call_count == 2
    delay.assert_called_once_with(1)


def test_malformed_output_after_503_does_not_trigger_third_attempt(
    sdk: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gemini, "sleep", MagicMock())
    sdk.side_effect = [
        errors.ServerError(503, {"status": "UNAVAILABLE"}),
        SimpleNamespace(text="invalid JSON"),
    ]
    with pytest.raises(gemini.InvalidOutputError):
        gemini.generate_course("Lists", "beginner")
    assert sdk.call_count == 2
