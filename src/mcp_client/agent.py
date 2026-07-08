import asyncio
import json
import sys
import anthropic
from mcp_client.client import connect
from mcp_client.guardrails import (
    validate_user_input,
    assert_role_alternation,
    validate_tool_result_ids,
    check_iteration_cap,
    sanitize_api_kwargs,
    check_token_budget,
    validate_tool_arguments,
    make_error_tool_result,
    sanitize_tool_result,
    MAX_OUTPUT_CHARS,
    TOOL_TIMEOUT_SECS,
)
from mcp_client.ai_guardrails import AIGuardrail, NoopGuardrail

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


async def run_agent(
    user_prompt: str,
    guardrail: AIGuardrail | None = None,
) -> None:
    """Drive a Claude agentic loop backed by the MCP server's tools.

    guardrail: optional AI-powered guardrail (e.g. BedrockGuardrail).
               Defaults to NoopGuardrail (no external API calls) for local dev.
    """
    if guardrail is None:
        guardrail = NoopGuardrail()

    # ------------------------------------------------------------------
    # Stage 1 — User Input
    # ------------------------------------------------------------------
    validate_user_input(user_prompt)          # G1.1 / G1.2 / G1.3 static
    guardrail.check_input(user_prompt)        # dynamic (Bedrock INPUT placeholder)

    client = anthropic.Anthropic()

    async with connect() as session:
        mcp_tools = (await session.list_tools()).tools
        tools = _to_anthropic_tools(mcp_tools)
        schema_by_name = {t.name: t.inputSchema for t in mcp_tools}  # for G4.1 / G4.3

        messages: list[dict] = [{"role": "user", "content": user_prompt}]
        print(f"User: {user_prompt}\n")

        iteration = 0
        while True:
            # ------------------------------------------------------------------
            # Stage 3 — Pre-API checks
            # ------------------------------------------------------------------
            check_iteration_cap(iteration)             # G3.1
            check_token_budget(MODEL, messages)        # G3.4 (warn only)
            api_kwargs = sanitize_api_kwargs(MODEL, {})  # G3.2 (model-param compat)

            response = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                tools=tools,
                messages=messages,
                **api_kwargs,
            )

            # ------------------------------------------------------------------
            # Stage 3 — G3.3: stop reason guard
            # ------------------------------------------------------------------
            if response.stop_reason == "refusal":
                print("[REFUSED] Claude refused to respond.", file=sys.stderr)
                break

            if response.stop_reason not in ("end_turn", "tool_use"):
                print(
                    f"[WARN] Unexpected stop_reason='{response.stop_reason}'. Aborting.",
                    file=sys.stderr,
                )
                break

            # ------------------------------------------------------------------
            # end_turn → Stage 7 (final output) then exit
            # ------------------------------------------------------------------
            if response.stop_reason == "end_turn":
                text_blocks = [
                    b for b in response.content
                    if hasattr(b, "text") and b.type == "text"
                ]
                if not text_blocks:
                    print("[NOTE] Claude returned an empty response.")  # G7.1
                    break

                for block in text_blocks:
                    output = block.text
                    # G7.2: output length cap
                    if len(output) > MAX_OUTPUT_CHARS:
                        output = output[:MAX_OUTPUT_CHARS] + "\n[OUTPUT TRUNCATED]"
                    guardrail.check_output(output)     # dynamic (Bedrock OUTPUT placeholder)
                    print(f"Assistant: {output}")
                break

            # ------------------------------------------------------------------
            # tool_use → Stages 4 / 5 / 6 then loop
            # ------------------------------------------------------------------
            messages.append({"role": "assistant", "content": response.content})
            assert_role_alternation(messages)          # G2.1

            expected_ids = {
                b.id for b in response.content if b.type == "tool_use"
            }
            tool_results: list[dict] = []

            for block in response.content:
                if block.type != "tool_use":
                    continue

                # --------------------------------------------------------------
                # Stage 4 — Tool Call Parsing
                # --------------------------------------------------------------

                # G4.1: tool name allowlist
                if block.name not in schema_by_name:
                    tool_results.append(make_error_tool_result(
                        block.id,
                        f"Unknown tool: '{block.name}'. "
                        f"Available: {list(schema_by_name)}",
                    ))
                    continue

                # G4.2: input must be a dict
                if not isinstance(block.input, dict):
                    tool_results.append(make_error_tool_result(
                        block.id,
                        f"Tool input must be a JSON object, "
                        f"got {type(block.input).__name__}",
                    ))
                    continue

                # G4.3: validate arguments against the tool's schema
                is_valid, error_msg = validate_tool_arguments(
                    block.input, schema_by_name[block.name]
                )
                if not is_valid:
                    tool_results.append(make_error_tool_result(
                        block.id, f"Invalid arguments: {error_msg}"
                    ))
                    continue

                print(f"  [tool] {block.name}({json.dumps(block.input)})")

                # --------------------------------------------------------------
                # Stage 5 — MCP Tool Execution
                # --------------------------------------------------------------

                # G5.1: per-call timeout
                try:
                    result = await asyncio.wait_for(
                        session.call_tool(block.name, block.input),
                        timeout=TOOL_TIMEOUT_SECS,
                    )
                except asyncio.TimeoutError:
                    tool_results.append(make_error_tool_result(
                        block.id,
                        f"Tool '{block.name}' timed out after {TOOL_TIMEOUT_SECS}s",
                    ))
                    continue

                text = " ".join(
                    c.text for c in result.content if hasattr(c, "text")
                )
                print(f"  [result] {text}")

                # --------------------------------------------------------------
                # Stage 6 — Tool Result Injection
                # --------------------------------------------------------------
                text = sanitize_tool_result(text, block.name)   # G6.1 / G6.2 / G6.3 static
                guardrail.check_tool_result(text, tool_name=block.name)  # dynamic (Bedrock INPUT placeholder)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": text,
                })

            # G2.3: guard against an empty tool_results list
            if not tool_results:
                print(
                    "[WARN] No tool results assembled despite tool_use stop reason. "
                    "Aborting loop.",
                    file=sys.stderr,
                )
                break

            validate_tool_result_ids(tool_results, expected_ids)  # G2.2

            messages.append({"role": "user", "content": tool_results})
            assert_role_alternation(messages)                      # G2.1

            iteration += 1


def main() -> None:
    prompt = (
        " ".join(sys.argv[1:])
        if len(sys.argv) > 1
        else "Echo 'hello from the agent', then add 3 and 7."
    )
    asyncio.run(run_agent(prompt))


if __name__ == "__main__":
    main()
