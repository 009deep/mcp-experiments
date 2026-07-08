import asyncio
import json
import sys
import anthropic
from mcp_client.client import connect

MODEL = "claude-sonnet-4-6"


def _to_anthropic_tools(mcp_tools: list) -> list:
    return [
        {
            "name": t.name,
            "description": t.description or "",
            "input_schema": t.inputSchema,
        }
        for t in mcp_tools
    ]


async def run_agent(user_prompt: str) -> None:
    """Drive a Claude agentic loop backed by the MCP server's tools.

    Claude decides which tools to call; we execute them via the MCP session
    and feed the results back until Claude reaches end_turn.
    """
    client = anthropic.Anthropic()

    async with connect() as session:
        mcp_tools = (await session.list_tools()).tools
        tools = _to_anthropic_tools(mcp_tools)

        messages: list[dict] = [{"role": "user", "content": user_prompt}]
        print(f"User: {user_prompt}\n")

        while True:
            response = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                tools=tools,
                messages=messages,
            )
            # Append the full assistant turn (may include thinking + tool_use blocks)
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                for block in response.content:
                    if hasattr(block, "text") and block.type == "text":
                        print(f"Assistant: {block.text}")
                break

            # Execute every tool_use block Claude requested
            tool_results = []
            print("response.content", response.content) 
            for block in response.content:
                if block.type != "tool_use":
                    continue
                print(f"  [tool] {block.name}({json.dumps(block.input)})")
                result = await session.call_tool(block.name, block.input)
                text = " ".join(c.text for c in result.content if hasattr(c, "text"))
                print(f"  [result] {text}")
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": text,
                    }
                )

            messages.append({"role": "user", "content": tool_results})
            print("messages", messages)

def main() -> None:
    prompt = (
        " ".join(sys.argv[1:])
        if len(sys.argv) > 1
        else "Echo 'hello from the agent', then add 3 and 7."
    )
    asyncio.run(run_agent(prompt))


if __name__ == "__main__":
    main()
