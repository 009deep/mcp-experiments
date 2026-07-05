from mcp.types import Tool, TextContent
from mcp import types


TOOLS = [
    Tool(
        name="echo",
        description="Echoes back the provided message. Useful for testing the server.",
        inputSchema={
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The message to echo back",
                }
            },
            "required": ["message"],
        },
    ),
    Tool(
        name="add",
        description="Adds two numbers together and returns the result.",
        inputSchema={
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "First number"},
                "b": {"type": "number", "description": "Second number"},
            },
            "required": ["a", "b"],
        },
    ),
]


async def handle_tool_call(name: str, arguments: dict) -> list[TextContent]:
    if name == "echo":
        message = arguments.get("message", "")
        return [TextContent(type="text", text=f"Echo: {message}")]

    if name == "add":
        result = arguments["a"] + arguments["b"]
        return [TextContent(type="text", text=str(result))]

    raise ValueError(f"Unknown tool: {name}")
