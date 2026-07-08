import asyncio
from jsonschema import validate, ValidationError
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from mcp_server.tools.example import TOOLS, handle_tool_call


app = Server("mcp-experiments")

# G5.2 / G5.3: build schema lookup once at startup for server-side validation
_SCHEMA_BY_NAME = {t.name: t.inputSchema for t in TOOLS}


@app.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    # G5.2: unknown tool — return structured error instead of propagating ValueError
    if name not in _SCHEMA_BY_NAME:
        return [TextContent(type="text", text=f"[ERROR] Unknown tool: '{name}'")]

    # G5.2: validate arguments against the tool's schema (defense-in-depth —
    # client-side already validates, but server validates independently)
    try:
        validate(instance=arguments, schema=_SCHEMA_BY_NAME[name])
    except ValidationError as e:
        return [TextContent(type="text", text=f"[ERROR] Invalid arguments: {e.message}")]

    # G5.3: catch unexpected exceptions so the MCP server stays alive
    try:
        return await handle_tool_call(name, arguments)
    except Exception as e:
        return [TextContent(type="text", text=f"[ERROR] Tool execution failed: {e}")]


async def _run():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


def main():
    asyncio.run(_run())


if __name__ == "__main__":
    main()
