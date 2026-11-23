"""REST entry point for the course generator."""

from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from app.config import MAX_PDF_BYTES, MAX_TEXT_LENGTH, ConfigurationError
from app.schemas import Course, CourseRequest
from app.services import gemini, pdf

app = FastAPI(title="AI-Powered eLearning Course Generator")

MAX_JSON_BYTES = MAX_TEXT_LENGTH * 12 + 4096
MAX_MULTIPART_BYTES = MAX_PDF_BYTES + MAX_TEXT_LENGTH * 4 + 16_384


class RequestTooLarge(MultiPartException):
    """The streamed request exceeds its byte limit."""


async def bounded_body(request: Request, limit: int) -> AsyncIterator[bytes]:
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise RequestTooLarge("The request exceeds the size limit.")
        yield chunk


async def parse_course_request(request: Request) -> CourseRequest:
    media_type = request.headers.get("content-type", "").split(";", 1)[0]
    media_type = media_type.strip().lower()
    if media_type == "application/json":
        body = bytearray()
        async for chunk in bounded_body(request, MAX_JSON_BYTES):
            body.extend(chunk)
        return CourseRequest.model_validate_json(body)

    if media_type != "multipart/form-data":
        raise HTTPException(415, "Use application/json or multipart/form-data.")

    parser = MultiPartParser(
        request.headers,
        bounded_body(request, MAX_MULTIPART_BYTES),
        max_files=1,
        max_fields=2,
        max_part_size=MAX_TEXT_LENGTH * 4,
    )
    form = await parser.parse()
    try:
        if len(form.multi_items()) != len(form) or set(form) - {"content", "pdf", "audience"}:
            raise HTTPException(422, "Use unique fields named content, pdf and audience.")
        content, upload = form.get("content"), form.get("pdf")
        audience = form.get("audience")
        if (content is None) == (upload is None):
            raise HTTPException(422, "Provide exactly one source: content or pdf.")
        if upload is None:
            return CourseRequest(content=content, audience=audience)
        if not isinstance(upload, UploadFile):
            raise HTTPException(422, "The pdf field must be an uploaded file.")
        # Validate the audience before doing any PDF processing.
        CourseRequest(content="PDF", audience=audience)
        data = await upload.read(MAX_PDF_BYTES + 1)
        content = await run_in_threadpool(pdf.extract_text, data)
        return CourseRequest(content=content, audience=audience)
    finally:
        await form.close()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


COURSE_BODY: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {"schema": CourseRequest.model_json_schema()},
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "description": "Supply exactly one of content and pdf.",
                    "required": ["audience"],
                    "properties": {
                        "audience": {
                            "type": "string",
                            "enum": ["beginner", "intermediate", "advanced"],
                        },
                        "content": {"type": "string"},
                        "pdf": {"type": "string", "format": "binary"},
                    },
                },
            },
        },
    },
}


@app.post("/generate-course", response_model=Course, openapi_extra=COURSE_BODY)
async def generate_course(request: Request) -> Course:
    try:
        source = await parse_course_request(request)
        return await run_in_threadpool(
            gemini.generate_course_from_content, source.content, source.audience
        )
    except ValidationError as exc:
        raise HTTPException(
            422, exc.errors(include_input=False, include_context=False, include_url=False)
        ) from None
    except (RequestTooLarge, pdf.PDFSizeError) as exc:
        raise HTTPException(413, str(exc)) from None
    except MultiPartException:
        raise HTTPException(
            400, "Invalid multipart data or multipart limits exceeded."
        ) from None
    except pdf.PDFError as exc:
        raise HTTPException(422, str(exc)) from None
    except ConfigurationError as exc:
        raise HTTPException(503, str(exc)) from None
    except gemini.QuotaError as exc:
        raise HTTPException(429, str(exc)) from None
    except gemini.GenerationError as exc:
        raise HTTPException(502, str(exc)) from None
