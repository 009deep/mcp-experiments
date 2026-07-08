import pytest
from unittest.mock import AsyncMock, MagicMock
from mcp_client.client import call_tool, list_tools


@pytest.fixture
def mock_session():
    session = AsyncMock()

    tool = MagicMock()
    tool.name = "echo"
    tool.description = "Echoes back the provided message."
    session.list_tools.return_value = MagicMock(tools=[tool])

    content = MagicMock()
    content.text = "Echo: hello"
    session.call_tool.return_value = MagicMock(content=[content])

    return session


@pytest.mark.asyncio
async def test_list_tools(mock_session, capsys):
    await list_tools(mock_session)
    captured = capsys.readouterr()
    assert "echo" in captured.out


ECHO_SCHEMA = {
    "type": "object",
    "properties": {
        "message": {"type": "string"},
    },
    "required": ["message"],
}


@pytest.mark.asyncio
async def test_call_tool(mock_session, capsys):
    await call_tool(mock_session, "echo", {"message": "hello"}, schema=ECHO_SCHEMA)
    captured = capsys.readouterr()
    assert "Echo: hello" in captured.out
    mock_session.call_tool.assert_called_once_with("echo", {"message": "hello"})


@pytest.mark.asyncio
async def test_call_tool_invalid_args(mock_session, capsys):
    result = await call_tool(mock_session, "echo", {"message": 123}, schema=ECHO_SCHEMA)
    captured = capsys.readouterr()
    assert "Invalid arguments" in captured.out
    assert result is None
    mock_session.call_tool.assert_not_called()


@pytest.mark.asyncio
async def test_call_tool_missing_required(mock_session, capsys):
    result = await call_tool(mock_session, "echo", {}, schema=ECHO_SCHEMA)
    captured = capsys.readouterr()
    assert "Invalid arguments" in captured.out
    assert result is None
    mock_session.call_tool.assert_not_called()
