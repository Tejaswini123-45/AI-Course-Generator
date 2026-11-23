"""Standalone MCP server exposing the shared Gemini generation service."""

from asyncio import to_thread
from collections.abc import Iterator
from contextlib import contextmanager

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from app.config import ConfigurationError
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
from app.services import gemini

mcp = FastMCP("eLearning Course Generator")


@contextmanager
def report_tool_errors() -> Iterator[None]:
    """Return safe provider errors to the MCP client."""
    try:
        yield
    except (ConfigurationError, gemini.GenerationError) as exc:
        raise ToolError(str(exc)) from None


@mcp.tool()
async def generate_course(topic: Topic, audience: Audience) -> Course:
    """Create a course with three objectives, four slides and three questions."""
    with report_tool_errors():
        return await to_thread(gemini.generate_course, topic, audience)


@mcp.tool()
async def generate_quiz(content: Content, num_questions: QuestionCount) -> Quiz:
    """Create 1–10 multiple-choice questions based on educational material."""
    with report_tool_errors():
        return await to_thread(gemini.generate_quiz, content, num_questions)


@mcp.tool()
async def update_slide(slide_content: Content, instruction: Instruction) -> SlideUpdate:
    """Revise a slide while preserving its educational meaning."""
    with report_tool_errors():
        return await to_thread(gemini.update_slide, slide_content, instruction)


if __name__ == "__main__":
    mcp.run(transport="stdio")
