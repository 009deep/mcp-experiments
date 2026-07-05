import pytest
from mcp_server.tools.example import handle_tool_call


@pytest.mark.asyncio
async def test_echo():
    result = await handle_tool_call("echo", {"message": "hello"})
    assert result[0].text == "Echo: hello"


@pytest.mark.asyncio
async def test_add():
    result = await handle_tool_call("add", {"a": 3, "b": 4})
    assert result[0].text == "7"


@pytest.mark.asyncio
async def test_unknown_tool():
    with pytest.raises(ValueError, match="Unknown tool"):
        await handle_tool_call("nonexistent", {})
