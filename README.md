# mcp-experiments

A local [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server, client, and agent built with Python. Includes:

- **MCP server** — exposes tools over the MCP stdio transport
- **MCP client** — interactive REPL to call tools manually, with JSON Schema validation
- **MCP agent** — Claude-powered agentic loop that calls your MCP tools automatically

## Project layout

```
mcp-experiments/
├── src/
│   ├── mcp_server/
│   │   ├── server.py              # MCP server entry point (with server-side validation)
│   │   └── tools/
│   │       └── example.py         # Built-in tools: echo, add
│   └── mcp_client/
│       ├── client.py              # MCP client + interactive REPL
│       ├── agent.py               # Claude agentic loop using MCP tools
│       ├── guardrails.py          # Static (deterministic) guardrail functions
│       └── ai_guardrails.py       # Dynamic guardrails: AIGuardrail interface + BedrockGuardrail
├── tests/
│   ├── test_server.py             # Unit tests for tool handlers
│   ├── test_client.py             # Unit tests for client with mocked session
│   └── test_guardrails.py         # Unit tests for all static guardrail functions
├── docs/
│   ├── guardrails.md              # Full guardrails design with pipeline diagram
│   └── message-roles.md           # Claude vs OpenAI message role reference
├── pyproject.toml
├── claude_desktop_config.example.json
└── copy_of_claude_config.json     # Merged Claude Desktop config
```

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)

Install `uv`:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Setup

```bash
git clone https://github.com/009deep/mcp-experiments.git
cd mcp-experiments
uv sync --extra dev
```

## Entry points

| Command | Description |
|---|---|
| `uv run mcp-server` | Start the MCP server (stdio transport) |
| `uv run mcp-client` | Interactive REPL to call tools manually |
| `uv run mcp-agent [prompt]` | Claude agent that calls MCP tools automatically |

---

## MCP Server

The server exposes tools over the MCP stdio transport. It reads JSON-RPC from stdin and writes responses to stdout.

```bash
uv run mcp-server
```

### Built-in tools

| Tool | Description | Parameters |
|---|---|---|
| `echo` | Echoes back a message | `message` (string) |
| `add` | Adds two numbers | `a`, `b` (number) |

### Adding your own tools

1. Open `src/mcp_server/tools/example.py`
2. Add a `Tool` entry to the `TOOLS` list
3. Add a matching branch in `handle_tool_call`

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

---

## MCP Client (interactive REPL)

```bash
uv run mcp-client
```

```
Connected. Tools: echo, add
Type '<tool> <json-args>', 'schema <tool>', or 'quit' to exit.

> schema echo
{
  "type": "object",
  "properties": {
    "message": {"type": "string"}
  },
  "required": ["message"]
}

> echo {"message": "hello"}
Echo: hello

> add {"a": 3, "b": 7}
10
```

**REPL commands:**

| Input | Effect |
|---|---|
| `schema <tool>` | Print the JSON Schema for a tool's arguments |
| `<tool> <json>` | Call a tool with the given JSON arguments |
| `quit` / `q` | Exit |

Arguments are validated against the tool's JSON Schema before sending — invalid input is rejected with an error message rather than a failed RPC call.

---

## MCP Agent (Claude-powered)

The agent connects Claude to your MCP tools. Claude decides which tools to call, the loop executes them via the MCP session, and results flow back until Claude produces a final answer.

### Setup

Set your Anthropic API key (get one at [console.anthropic.com](https://console.anthropic.com/settings/keys)):

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

### Run

```bash
# Default demo prompt
uv run mcp-agent

# Custom prompt
uv run mcp-agent "What is 42 plus 58?"
uv run mcp-agent "Echo 'hello world' and then add 100 and 200"
```

### Example output

```
User: Echo 'hello from the agent', then add 3 and 7.

  [tool] echo({"message": "hello from the agent"})
  [result] Echo: hello from the agent
  [tool] add({"a": 3, "b": 7})
  [result] 10
Assistant: I echoed your message and the sum of 3 + 7 is 10.
```

### Model options

Change `MODEL` in `src/mcp_client/agent.py`:

| Model ID | Context | Cost (in/out per 1M) | Adaptive thinking | Best for |
|---|---|---|---|---|
| `claude-haiku-4-5` | 200K | $1 / $5 | No | High-volume, simple tool calls |
| `claude-sonnet-4-6` | 1M | $3 / $15 | Yes | General use — recommended default |
| `claude-opus-4-6` | 1M | $5 / $25 | Yes | Complex multi-step reasoning |
| `claude-opus-4-7` | 1M | $5 / $25 | Yes | Complex multi-step reasoning |
| `claude-opus-4-8` | 1M | $5 / $25 | Yes | Complex multi-step reasoning |
| `claude-fable-5` | 1M | $10 / $50 | Always on* | Most demanding tasks |

> **Haiku:** does not support `thinking` — remove the `thinking` parameter from `messages.create` when using it.
>
> **Fable 5:** thinking is always active and cannot be configured. It also requires a `fallbacks` parameter and has a `refusal` stop reason — see the [migration guide](https://docs.anthropic.com/en/docs/about-claude/models) before using it.

### How the loop works

```
You ──prompt──▶ Claude (with MCP tool schemas)
                    │
         tool_use?  │  end_turn?
                    ▼           ▼
             call MCP tool   print answer, done
                    │
           tool_result ──────▶ Claude (again)
```

1. Tool schemas are fetched from the MCP server via `list_tools` and converted to Anthropic tool definitions.
2. Claude returns `stop_reason: "tool_use"` when it wants to call a tool.
3. The loop calls each requested tool via the MCP session and feeds the results back.
4. Claude returns `stop_reason: "end_turn"` when it has a final answer.

---

## Connecting to Claude Desktop

1. Open Claude Desktop → **Settings → Developer → Edit Config**
2. Merge the `mcpServers` block from `claude_desktop_config.example.json` into your config:

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

3. Restart Claude Desktop. The `echo` and `add` tools will appear in new conversations.

---

## Guardrails

The agent loop includes layered guardrails at every stage of the pipeline. See [`docs/guardrails.md`](docs/guardrails.md) for the full design with diagrams.

### Static (deterministic) guardrails

Built into the agent loop — no external API calls required. Implemented in `src/mcp_client/guardrails.py`.

| Stage | What is checked |
|-------|-----------------|
| User input | Empty/oversized prompts; known injection patterns (warn only) |
| Message build | Strict user/assistant role alternation; `tool_use_id` round-trip validity |
| Pre-API | Loop iteration cap (default 10); model-parameter compatibility (Haiku/Fable edge cases); token budget estimate |
| Tool call parsing | Tool name allowlist; input type; argument schema validation |
| MCP execution | Per-call timeout (30 s); server-side schema validation and exception handling |
| Tool result | Size truncation (8 K chars); injection pattern scan; UTF-8 encoding safety |
| Final output | Empty response guard; output length cap (20 K chars) |

### Dynamic (AI-powered) guardrails — AWS Bedrock

Semantic checks backed by cloud APIs are wired as placeholders in `src/mcp_client/ai_guardrails.py`. To activate:

1. Create a guardrail in the [AWS Console](https://console.aws.amazon.com/bedrock/home#/guardrails) or via `bedrock:CreateGuardrail`.
2. Set env vars:
   ```bash
   export BEDROCK_GUARDRAIL_ID="<your-guardrail-id>"
   export BEDROCK_GUARDRAIL_VERSION="DRAFT"   # or a published version
   export AWS_DEFAULT_REGION="us-east-1"
   ```
3. Install boto3 and pass the guardrail to `run_agent()`:
   ```bash
   uv add boto3
   ```
   ```python
   from mcp_client.ai_guardrails import BedrockGuardrail
   from mcp_client.agent import run_agent

   await run_agent("my prompt", guardrail=BedrockGuardrail())
   ```

Bedrock checks run at three stages: user input (Stage 1), tool results before they are fed back to Claude (Stage 6 — detects indirect prompt injection and PII in tool output), and the final model response (Stage 7).

Without configuration, the guardrail defaults to `NoopGuardrail` which skips all external calls — safe for local development.

---

## Running tests

```bash
uv run pytest
```

Tests cover tool handlers (`test_server.py`), the client's validation + call logic with a mocked MCP session (`test_client.py`), and all static guardrail functions (`test_guardrails.py`).

---

## MCP Inspector (optional)

Browser-based UI for testing the server interactively:

```bash
npx @modelcontextprotocol/inspector uv run mcp-server
```

Open `http://localhost:5173`.

---

## Resources

- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [MCP specification](https://modelcontextprotocol.io/docs)
- [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python)
- [MCP Inspector](https://github.com/modelcontextprotocol/inspector)
