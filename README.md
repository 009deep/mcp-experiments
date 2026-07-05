# mcp-experiments

A local [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server built with Python. Use this as a starting point for building custom tools that Claude Desktop (or any MCP client) can call.

## Project layout

```
mcp-experiments/
├── src/
│   └── mcp_server/
│       ├── server.py          # MCP server entry point
│       └── tools/
│           ├── __init__.py
│           └── example.py     # Built-in example tools (echo, add)
├── tests/
│   └── test_server.py
├── pyproject.toml
└── claude_desktop_config.example.json
```

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) **or** pip

Install `uv` if you don't have it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Setup

### 1. Clone and enter the repo

```bash
git clone https://github.com/009deep/mcp-experiments.git
cd mcp-experiments
```

### 2. Create a virtual environment and install dependencies

```bash
uv venv
uv pip install -e ".[dev]"
```

Or with plain pip:

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### 3. Run the server manually (stdio mode)

```bash
uv run mcp-server
```

The server speaks the MCP stdio transport — it reads JSON-RPC from stdin and writes responses to stdout. You won't see output in the terminal unless a client connects.

## Connecting to Claude Desktop

1. Open Claude Desktop → **Settings → Developer → Edit Config**.
2. Merge the contents of `claude_desktop_config.example.json` into your config, replacing `/ABSOLUTE/PATH/TO/mcp-experiments` with the real path:

```json
{
  "mcpServers": {
    "mcp-experiments": {
      "command": "uv",
      "args": [
        "run",
        "--project",
        "/Users/you/mcp-experiments",
        "mcp-server"
      ]
    }
  }
}
```

3. Restart Claude Desktop. The tools listed below will appear when you start a new conversation.

## Built-in example tools

| Tool  | Description | Parameters |
|-------|-------------|------------|
| `echo` | Echoes back a message | `message` (string) |
| `add`  | Adds two numbers | `a`, `b` (number) |

## Adding your own tools

1. Open `src/mcp_server/tools/example.py` (or create a new file under `tools/`).
2. Add a `Tool` entry to the `TOOLS` list with a name, description, and JSON Schema for its inputs.
3. Add a matching branch in `handle_tool_call`.
4. Register the new module in `server.py` if you created a separate file.

Example skeleton:

```python
Tool(
    name="my_tool",
    description="Does something useful.",
    inputSchema={
        "type": "object",
        "properties": {
            "input": {"type": "string", "description": "Some input"}
        },
        "required": ["input"],
    },
),
```

```python
if name == "my_tool":
    return [TextContent(type="text", text=f"Result: {arguments['input']}")]
```

## Running tests

```bash
uv run pytest
```

## Using the MCP Inspector (optional)

The [MCP Inspector](https://github.com/modelcontextprotocol/inspector) is a browser-based UI for testing your server interactively:

```bash
npx @modelcontextprotocol/inspector uv run mcp-server
```

Then open `http://localhost:5173` in your browser.

## Resources

- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [MCP specification](https://modelcontextprotocol.io/docs)
- [MCP Inspector](https://github.com/modelcontextprotocol/inspector)
