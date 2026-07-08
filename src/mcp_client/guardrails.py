import sys
from jsonschema import validate, ValidationError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_PROMPT_CHARS = 10_000
MAX_ITERATIONS = 10
TOOL_TIMEOUT_SECS = 30.0
MAX_TOOL_RESULT_CHARS = 8_000
MAX_OUTPUT_CHARS = 20_000

INJECTION_PATTERNS = ["\nHuman:", "\nAssistant:", "<system>", "[INST]"]

MODEL_CONTEXT_LIMITS: dict[str, int] = {
    "haiku": 200_000,
    "sonnet": 1_000_000,
    "opus": 1_000_000,
    "fable": 1_000_000,
}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class GuardrailError(ValueError):
    pass


class MessageSequenceError(GuardrailError):
    pass


# ---------------------------------------------------------------------------
# Stage 1 — User Input
# ---------------------------------------------------------------------------

def validate_user_input(prompt: str) -> None:
    """G1.1 + G1.2 + G1.3: reject empty/oversized prompts; warn on injection patterns."""
    if not prompt.strip():
        raise ValueError("Prompt cannot be empty")
    if len(prompt) > MAX_PROMPT_CHARS:
        raise ValueError(
            f"Prompt too long ({len(prompt):,} chars, max {MAX_PROMPT_CHARS:,})"
        )
    _check_injection_patterns(prompt, "user prompt")


def _check_injection_patterns(text: str, label: str) -> None:
    """G1.3 / G6.2: warn (do not block) when known injection markers are found."""
    for pattern in INJECTION_PATTERNS:
        if pattern in text:
            print(
                f"[WARN] Possible injection pattern {pattern!r} detected in {label}",
                file=sys.stderr,
            )


# ---------------------------------------------------------------------------
# Stage 2 — Message Array Construction
# ---------------------------------------------------------------------------

def assert_role_alternation(
    messages: list[dict], allow_roles: set[str] | None = None
) -> None:
    """G2.1: enforce strict user/assistant alternation required by the Claude API.

    allow_roles: roles to skip when checking (e.g. {"system", "tool"} for OpenAI
    compatibility — those roles sit outside the alternating pair).
    """
    skip = allow_roles or set()
    filtered = [m for m in messages if m.get("role") not in skip]
    expected = "user"
    for i, msg in enumerate(filtered):
        actual = msg.get("role")
        if actual != expected:
            raise MessageSequenceError(
                f"Role alternation violation: expected '{expected}', got '{actual}' "
                f"at message index {i}"
            )
        expected = "assistant" if expected == "user" else "user"


def validate_tool_result_ids(
    tool_results: list[dict],
    expected_ids: set[str],
    id_field: str = "tool_use_id",
) -> None:
    """G2.2: every tool_result must reference a tool_use id from the prior assistant turn."""
    for result in tool_results:
        rid = result.get(id_field)
        if rid not in expected_ids:
            raise MessageSequenceError(
                f"tool_result has {id_field}='{rid}' which does not match any "
                f"tool_use id in the prior turn. Expected one of: {expected_ids}"
            )


# ---------------------------------------------------------------------------
# Stage 3 — Pre-Claude API Invocation
# ---------------------------------------------------------------------------

def check_iteration_cap(
    iteration: int, max_iterations: int = MAX_ITERATIONS
) -> None:
    """G3.1: abort the agent loop if it exceeds the iteration limit."""
    if iteration >= max_iterations:
        raise GuardrailError(
            f"[ERROR] Agent loop exceeded MAX_ITERATIONS={max_iterations}. "
            "Aborting to prevent runaway API spend."
        )


def sanitize_api_kwargs(model: str, kwargs: dict) -> dict:
    """G3.2: strip or inject model-specific parameters.

    - Haiku: remove 'thinking' (unsupported).
    - Fable: inject fallbacks=True (required).
    """
    model_lower = model.lower()
    kwargs = dict(kwargs)
    if "haiku" in model_lower and "thinking" in kwargs:
        print(
            "[WARN] Removing 'thinking' parameter — not supported by Haiku models",
            file=sys.stderr,
        )
        del kwargs["thinking"]
    if "fable" in model_lower and "fallbacks" not in kwargs:
        print(
            "[WARN] Injecting fallbacks=True — required for Fable models",
            file=sys.stderr,
        )
        kwargs["fallbacks"] = True
    return kwargs


def estimate_token_count(messages: list[dict]) -> int:
    """Rough token estimate: total characters / 4. Handles both dict and SDK objects."""
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text") or block.get("content") or ""
                else:
                    # Anthropic SDK Pydantic content blocks
                    text = getattr(block, "text", None) or getattr(block, "content", None) or ""
                total += len(str(text))
    return total // 4


def check_token_budget(model: str, messages: list[dict]) -> None:
    """G3.4: warn (non-blocking) when estimated token usage exceeds 80% of context limit."""
    estimated = estimate_token_count(messages)
    model_lower = model.lower()
    limit = MODEL_CONTEXT_LIMITS.get("sonnet", 1_000_000)
    for key, val in MODEL_CONTEXT_LIMITS.items():
        if key in model_lower:
            limit = val
            break
    threshold = int(limit * 0.8)
    if estimated > threshold:
        print(
            f"[WARN] Estimated token count ({estimated:,}) exceeds 80% of context "
            f"limit ({limit:,}) for model '{model}'",
            file=sys.stderr,
        )


# ---------------------------------------------------------------------------
# Stage 4 — Tool Call Parsing
# ---------------------------------------------------------------------------

def validate_tool_arguments(arguments: dict, schema: dict) -> tuple[bool, str]:
    """G4.3: validate tool arguments against the tool's JSON Schema.

    Returns (is_valid, error_message). Reuses jsonschema.validate() — same
    library already used in client.py.
    """
    try:
        validate(instance=arguments, schema=schema)
        return True, ""
    except ValidationError as e:
        return False, e.message


def make_error_tool_result(tool_use_id: str, message: str) -> dict:
    """Build an error tool_result block that Claude can reason about."""
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": f"[ERROR] {message}",
        "is_error": True,
    }


# ---------------------------------------------------------------------------
# Stage 6 — Tool Result Injection
# ---------------------------------------------------------------------------

def sanitize_tool_result(text: str, tool_name: str = "") -> str:
    """G6.1 + G6.2 + G6.3: sanitize tool output before injecting into messages."""
    # G6.3: replace invalid UTF-8 bytes rather than raising
    text = text.encode("utf-8", errors="replace").decode("utf-8")
    # G6.1: truncate oversized results to prevent context window bloat
    if len(text) > MAX_TOOL_RESULT_CHARS:
        text = text[:MAX_TOOL_RESULT_CHARS] + f"\n[RESULT TRUNCATED AT {MAX_TOOL_RESULT_CHARS} CHARS]"
    # G6.2: warn on injection patterns in tool output
    label = f"tool result from '{tool_name}'" if tool_name else "tool result"
    _check_injection_patterns(text, label)
    return text
