import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.config import ConfigurationError
from app import main
from app.main import app
from app.services import gemini
from tests.test_pdf import make_pdf

client = TestClient(app)


def test_health() -> None:
    assert client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize("source", ["json", "text-form", "pdf"])
def test_api_generates_course_with_mocked_gemini(
    monkeypatch: pytest.MonkeyPatch, course_data: dict, source: str
) -> None:
    monkeypatch.setattr(gemini, "gemini_settings", lambda: ("test-key", "test-model"))
    constructor = MagicMock()
    monkeypatch.setattr(gemini.genai, "Client", constructor)
    generate = constructor.return_value.__enter__.return_value.models.generate_content
    generate.return_value = SimpleNamespace(text=json.dumps(course_data))
    material = "Lists preserve order."
    if source == "json":
        response = client.post(
            "/generate-course", json={"content": material, "audience": "beginner"}
        )
    else:
        fields = {"audience": (None, "beginner")}
        if source == "pdf":
            fields["pdf"] = ("sample.pdf", make_pdf(material), "application/pdf")
        else:
            fields["content"] = (None, material)
        response = client.post("/generate-course", files=fields)
    assert response.status_code == 200, response.text
    assert response.json() == course_data
    assert json.loads(generate.call_args.kwargs["contents"])["material"] == material


@pytest.mark.parametrize(
    "payload",
    [{"audience": "beginner"}, {"content": " "}, {"content": "Lists", "audience": "expert"}],
)
def test_rejects_invalid_json_request(payload: dict) -> None:
    response = client.post("/generate-course", json=payload)
    assert response.status_code == 422
    assert all("input" not in error for error in response.json()["detail"])


def test_rejects_two_sources() -> None:
    response = client.post(
        "/generate-course",
        data={"audience": "beginner", "content": "list"},
        files={"pdf": ("sample.pdf", b"not a PDF")},
    )
    assert response.status_code == 422
    assert "exactly one" in response.json()["detail"]


def test_rejects_invalid_pdf() -> None:
    response = client.post(
        "/generate-course",
        data={"audience": "beginner"},
        files={"pdf": ("sample.pdf", b"not a PDF")},
    )
    assert response.status_code == 422


def test_rejects_oversized_multipart(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "MAX_MULTIPART_BYTES", 100)
    response = client.post(
        "/generate-course",
        data={"audience": "beginner"},
        files={"pdf": ("sample.pdf", make_pdf("Lists preserve order."))},
    )
    assert response.status_code == 413


def test_documents_both_request_formats() -> None:
    operation = client.get("/openapi.json").json()["paths"]["/generate-course"]["post"]
    assert set(operation["requestBody"]["content"]) == {"application/json", "multipart/form-data"}


@pytest.mark.parametrize(
    ("error", "status"),
    [(ConfigurationError, 503), (gemini.QuotaError, 429), (gemini.GenerationError, 502)],
)
def test_returns_service_error(
    monkeypatch: pytest.MonkeyPatch, error: type[Exception], status: int
) -> None:
    def fail(content: str, audience: str) -> None:
        raise error("Test service failure.")

    monkeypatch.setattr(gemini, "generate_course_from_content", fail)
    response = client.post(
        "/generate-course", json={"content": "Lists", "audience": "beginner"}
    )
    assert response.status_code == status
    assert response.json()["detail"] == "Test service failure."
