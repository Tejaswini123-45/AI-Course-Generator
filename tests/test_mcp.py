import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.memory import create_connected_server_and_client_session

from app.config import ConfigurationError
from app.mcp_server import mcp
from app.schemas import Course, Quiz, SlideUpdate
from app.services import gemini

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_tools_return_structured_results(
    monkeypatch: pytest.MonkeyPatch, course_data: dict
) -> None:
    course = Course.model_validate(course_data)
    quiz = Quiz(questions=course.quiz[:2])
    slide = SlideUpdate(title="Lists", content="Keep items ordered.", key_takeaway="Use [].")
    examples = {
        "generate_course": ({"topic": "Lists", "audience": "beginner"}, course),
        "generate_quiz": ({"content": "Lists keep order.", "num_questions": 2}, quiz),
        "update_slide": ({"slide_content": "Lists keep order.", "instruction": "Shorten"}, slide),
    }
    for name, (_, output) in examples.items():
        monkeypatch.setattr(gemini, name, Mock(return_value=output))

    async with create_connected_server_and_client_session(mcp) as client:
        tools = (await client.list_tools()).tools
        assert {tool.name for tool in tools} == examples.keys()
        for tool in tools:
            assert tool.outputSchema
            arguments, expected = examples[tool.name]
            result = await client.call_tool(tool.name, arguments)
            assert not result.isError
            assert result.structuredContent == expected.model_dump()
            getattr(gemini, tool.name).assert_called_once_with(*arguments.values())


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("generate_course", {"topic": " ", "audience": "beginner"}),
        ("generate_quiz", {"content": "Lists", "num_questions": 11}),
        ("update_slide", {"slide_content": "Lists", "instruction": ""}),
    ],
)
async def test_invalid_inputs_stop_before_generation(
    monkeypatch: pytest.MonkeyPatch, tool: str, arguments: dict
) -> None:
    generate = Mock()
    monkeypatch.setattr(gemini, tool, generate)
    async with create_connected_server_and_client_session(mcp) as client:
        assert (await client.call_tool(tool, arguments)).isError
    generate.assert_not_called()


async def test_configuration_error_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        gemini, "generate_course", Mock(side_effect=ConfigurationError("Set GEMINI_API_KEY."))
    )
    async with create_connected_server_and_client_session(mcp) as client:
        result = await client.call_tool(
            "generate_course", {"topic": "Lists", "audience": "beginner"}
        )
    assert result.isError
    assert "Set GEMINI_API_KEY." in result.content[0].text


async def test_independent_stdio_startup() -> None:
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.mcp_server"],
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as client:
            await client.initialize()
            tools = (await client.list_tools()).tools
    assert {tool.name for tool in tools} == {
        "generate_course",
        "generate_quiz",
        "update_slide",
    }
