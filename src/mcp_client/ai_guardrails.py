"""AI-powered (dynamic) guardrails backed by cloud provider APIs.

Usage in agent.py:
    from mcp_client.ai_guardrails import BedrockGuardrail, NoopGuardrail

    guardrail = BedrockGuardrail()          # requires BEDROCK_GUARDRAIL_ID env var
    guardrail = NoopGuardrail()             # no-op, safe for local dev (default)

    await run_agent("my prompt", guardrail=guardrail)
"""

import os
import sys
from abc import ABC, abstractmethod

from mcp_client.guardrails import GuardrailError


class AIGuardrail(ABC):
    """Interface for AI-powered semantic guardrail checks."""

    @abstractmethod
    def check_input(self, text: str) -> None:
        """Stage 1: check user prompt before sending to the model.
        Raise GuardrailError if the text fails the check.
        """

    @abstractmethod
    def check_output(self, text: str) -> None:
        """Stage 7: check model response before showing to the user.
        Raise GuardrailError if the text fails the check.
        """

    def check_tool_result(self, text: str, tool_name: str = "") -> None:
        """Stage 6: check tool output before injecting back into the conversation.

        Default implementation reuses check_input. Override for providers that
        have a dedicated document-level injection check (e.g. Azure Prompt Shield
        with documents= param, which is purpose-built for indirect prompt injection
        in tool / RAG results).
        """
        self.check_input(text)


class NoopGuardrail(AIGuardrail):
    """Passes all checks. Default for local development — no external API calls."""

    def check_input(self, text: str) -> None:
        pass

    def check_output(self, text: str) -> None:
        pass

    def check_tool_result(self, text: str, tool_name: str = "") -> None:
        pass


class BedrockGuardrail(AIGuardrail):
    """Calls AWS Bedrock ApplyGuardrail for semantic safety checks.

    Stages covered:
      Stage 1 (check_input)       — source="INPUT", checks user prompt for injection /
                                    jailbreak / PII / content policy
      Stage 6 (check_tool_result) — source="INPUT", checks tool output for indirect
                                    prompt injection and PII before feeding back to Claude
      Stage 7 (check_output)      — source="OUTPUT", checks model response before
                                    displaying to user

    Required env vars:
      BEDROCK_GUARDRAIL_ID       Guardrail identifier (from AWS Console or CreateGuardrail)
      BEDROCK_GUARDRAIL_VERSION  Guardrail version (default: DRAFT)
      AWS_DEFAULT_REGION         AWS region (default: us-east-1)

    AWS credentials are resolved via the standard boto3 chain:
      AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY env vars, ~/.aws/credentials,
      EC2/ECS/Lambda IAM role, etc.

    boto3 is an optional dependency — install with:
      pip install boto3
      # or: uv add boto3
    """

    def __init__(
        self,
        guardrail_id: str | None = None,
        guardrail_version: str | None = None,
        region: str | None = None,
    ) -> None:
        self.guardrail_id = guardrail_id or os.environ.get("BEDROCK_GUARDRAIL_ID", "")
        self.guardrail_version = (
            guardrail_version or os.environ.get("BEDROCK_GUARDRAIL_VERSION", "DRAFT")
        )
        self._region = region or os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
        self._client = None  # lazy-init — avoid boto3 import cost when not used

    def _bedrock(self):
        if self._client is None:
            try:
                import boto3
            except ImportError as e:
                raise ImportError(
                    "boto3 is required for BedrockGuardrail. Install with: pip install boto3"
                ) from e
            self._client = boto3.client("bedrock-runtime", region_name=self._region)
        return self._client

    def _apply(self, text: str, source: str, label: str) -> None:
        """Call ApplyGuardrail and raise GuardrailError on intervention.

        source: "INPUT"  — content going into the model (user prompt, tool results)
                "OUTPUT" — content coming out of the model (final response)
        """
        if not self.guardrail_id:
            # TODO: Remove this guard once BEDROCK_GUARDRAIL_ID is configured.
            # Until then, log a notice and skip so the agent loop continues.
            print(
                f"[Bedrock PLACEHOLDER] check({label!r}, source={source!r}) "
                "— skipped: BEDROCK_GUARDRAIL_ID not set",
                file=sys.stderr,
            )
            return

        # --- Actual Bedrock call (uncomment once guardrail_id is configured) ---
        #
        # response = self._bedrock().apply_guardrail(
        #     guardrailIdentifier=self.guardrail_id,
        #     guardrailVersion=self.guardrail_version,
        #     source=source,
        #     content=[{"text": {"text": text}}],
        # )
        #
        # if response["action"] == "GUARDRAIL_INTERVENED":
        #     reason = (response.get("outputs") or [{}])[0].get("text", "Guardrail intervened")
        #     # response["assessments"] contains per-policy detail — log it for observability
        #     print(f"[Bedrock] assessments: {response.get('assessments')}", file=sys.stderr)
        #     raise GuardrailError(f"[Bedrock] {label} blocked: {reason}")
        #
        # -------------------------------------------------------------------------

        # TODO: Delete the placeholder print below once the call above is active.
        print(
            f"[Bedrock PLACEHOLDER] check({label!r}, source={source!r}) "
            f"— guardrail_id={self.guardrail_id!r}, version={self.guardrail_version!r}",
            file=sys.stderr,
        )

    def check_input(self, text: str) -> None:
        """Stage 1: scan user prompt for prompt injection, jailbreaks, PII, and
        content policy violations before sending to Claude."""
        self._apply(text, source="INPUT", label="user prompt")

    def check_output(self, text: str) -> None:
        """Stage 7: scan model response for content policy violations and PII
        before displaying to the user."""
        self._apply(text, source="OUTPUT", label="model response")

    def check_tool_result(self, text: str, tool_name: str = "") -> None:
        """Stage 6: scan tool output for indirect prompt injection and PII before
        injecting back into the conversation as a tool_result message.

        Uses source="INPUT" because Bedrock evaluates this content as if it were
        input to the model — which it will be, as a tool_result user message.

        Key advantage over other providers at this stage: Bedrock can also detect
        and redact PII (names, SSNs, credit cards) in tool output — useful when
        tools query databases or APIs that may return sensitive user data.
        """
        label = f"tool result from '{tool_name}'" if tool_name else "tool result"
        self._apply(text, source="INPUT", label=label)
