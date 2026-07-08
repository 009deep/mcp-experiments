# Message Roles in LLM APIs

## Claude (Anthropic API)

Only two roles in the `messages` array:

| Role | Used for |
|---|---|
| `user` | Human turns — text, images, tool results |
| `assistant` | Model turns — text, tool_use blocks |

The system prompt is a **separate top-level parameter**, not a message role:

```python
client.messages.create(
    model="claude-sonnet-4-6",
    system="You are a helpful assistant.",   # top-level, not in messages
    messages=[
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
        {"role": "user", "content": "..."},
    ]
)
```

Tool results go back as `user` messages with `tool_result` content blocks:

```python
# After Claude requests a tool call, feed the result back like this:
messages.append({
    "role": "user",
    "content": [
        {
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": "the result text",
        }
    ]
})
```

---

## Comparison: Claude vs OpenAI vs Open-Source

| | Claude | OpenAI / GPT | Most OSS (Llama, Mistral, etc.) |
|---|---|---|---|
| System prompt | Top-level `system` param | `{"role": "system"}` in messages | Varies — usually OpenAI-compatible |
| Tool calls | `tool_use` block in `assistant` content | `tool_calls` field on `assistant` message | OpenAI-compatible format |
| Tool results | `tool_result` block in `user` content | Separate message with `role: "tool"` | OpenAI-compatible format |
| Extra roles | None | `tool` role | Sometimes `function` (legacy) |

Most open-source models (Ollama, vLLM, HuggingFace TGI) expose an **OpenAI-compatible API**, so they use the OpenAI role format (`system` / `user` / `assistant` / `tool`).

---

## Key gotcha

You cannot swap Claude's `messages` array directly into an OpenAI client call — two things differ:

1. **System prompt placement** — Claude takes it as a top-level param; OpenAI takes it as a `role: "system"` message.
2. **Tool result format** — Claude sends results as `tool_result` content blocks inside a `user` message; OpenAI sends them as a separate message with `role: "tool"`.
