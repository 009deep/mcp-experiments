import asyncio
import json
from contextlib import asynccontextmanager
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp_client.guardrails import validate_tool_arguments


SERVER_PARAMS = StdioServerParameters(
    command="uv",
    args=["run", "--project", ".", "mcp-server"],
)


@asynccontextmanager
async def connect(params: StdioServerParameters = SERVER_PARAMS):
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def list_tools(session: ClientSession) -> None:
    result = await session.list_tools()
    print("Available tools:")
    for tool in result.tools:
        print(f"  {tool.name}: {tool.description}")


async def call_tool(
    session: ClientSession,
    name: str,
    arguments: dict,
    schema: dict | None = None,
):
    if schema is not None:
        is_valid, error_msg = validate_tool_arguments(arguments, schema)
        if not is_valid:
            print(f"Invalid arguments: {error_msg}")
            return None

    result = await session.call_tool(name, arguments)
    for content in result.content:
        print(content.text)
    return result


async def interactive(session: ClientSession) -> None:
    """Simple REPL for calling tools manually."""
    tools = (await session.list_tools()).tools
    schema_by_name = {t.name: t.inputSchema for t in tools}
    print(f"Connected. Tools: {', '.join(schema_by_name)}")
    print("Type '<tool> <json-args>', 'schema <tool>', or 'quit' to exit.\n")

    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if line in ("quit", "exit", "q"):
            break

        parts = line.split(" ", 1)
        tool_name = parts[0]
        raw_args = parts[1] if len(parts) > 1 else "{}"

        if tool_name == "schema":
            target = parts[1].strip() if len(parts) > 1 else ""
            if target not in schema_by_name:
                print(f"Unknown tool '{target}'. Available: {', '.join(schema_by_name)}")
            else:
                print(json.dumps(schema_by_name[target], indent=2))
            continue

        if tool_name not in schema_by_name:
            print(f"Unknown tool '{tool_name}'. Available: {', '.join(schema_by_name)}")
            continue

        try:
            args = json.loads(raw_args)
        except json.JSONDecodeError as e:
            print(f"Invalid JSON: {e}")
            continue

        await call_tool(session, tool_name, args, schema=schema_by_name[tool_name])


async def _main():
    async with connect() as session:
        await interactive(session)


def main():
    asyncio.run(_main())


if __name__ == "__main__":
    main()
