# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies (includes dev extras for pytest)
uv sync --extra dev

# Run the MCP server (stdio transport)
uv run mcp-server

# Run the interactive REPL client
uv run mcp-client

# Run the Claude agent loop
uv run mcp-agent "What is 42 plus 58?"

# Run all tests
uv run pytest

# Run a single test file
uv run pytest tests/test_server.py

# Run a single test by name
uv run pytest tests/test_server.py::test_echo
```

The agent requires `ANTHROPIC_API_KEY` set in the environment.

## Architecture

Three entry points, all defined in `pyproject.toml [project.scripts]`:

**`mcp-server`** (`src/mcp_server/`) — MCP server over stdio transport. `server.py` wires up the MCP `Server` instance and delegates to `tools/example.py`, which owns both the `TOOLS` list (schema definitions) and `handle_tool_call` (the dispatch function). Adding a tool means editing both in `example.py`.

**`mcp-client`** (`src/mcp_client/client.py`) — Interactive REPL. Spawns the server as a subprocess via `StdioServerParameters`, validates JSON arguments against each tool's `inputSchema` using `jsonschema` before sending, and prints results. The `connect()` async context manager is reused by the agent.

**`mcp-agent`** (`src/mcp_client/agent.py`) — Agentic loop that bridges Claude and the MCP server. Fetches tool schemas from the server via `list_tools`, converts them to Anthropic tool definitions, then drives a `while True` loop: send messages → if `stop_reason == "tool_use"` call MCP tools and feed back `tool_result` blocks → if `stop_reason == "end_turn"` print answer and exit.

## Key conventions

- **Tool results in the Anthropic API** are `user`-role messages containing `tool_result` content blocks (not a separate `tool` role). See `docs/message-roles.md` for the Claude vs OpenAI format differences.
- **System prompt** is a top-level `system=` parameter in `messages.create`, not a message in the array.
- **Model** is set as `MODEL = "claude-sonnet-4-6"` at the top of `agent.py`. Haiku models don't support `thinking`; Fable 5 requires `fallbacks` and has a `refusal` stop reason.
- Tests use `pytest-asyncio` with `asyncio_mode = "auto"` (no per-test decorator needed). `test_server.py` tests handlers directly; `test_client.py` mocks the MCP session with `AsyncMock`.
