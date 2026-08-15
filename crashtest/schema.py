"""Pydantic v2 models for the CrashTest cassette format."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------

class ToolCall(BaseModel):
    """A single tool/function call made by the agent."""
    name: str
    args: dict


class Turn(BaseModel):
    """One conversation turn inside a cassette."""
    n: int
    role: Literal["attacker", "agent", "tool"]
    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_name: str | None = None


# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------

class Assertion(BaseModel):
    """
    A deterministic assertion evaluated against the recorded conversation.

    Fields are optional because each assertion type uses a different subset:
      - canary_absent   → value (the canary string)
      - tool_not_called → tool
      - tool_arg_constraint → tool, rule
      - tool_called_with    → tool, args
    """
    type: Literal[
        "canary_absent",
        "tool_not_called",
        "tool_arg_constraint",
        "tool_called_with",
    ]
    value: str | None = None
    tool: str | None = None
    rule: str | None = None
    args: dict | None = None


# ---------------------------------------------------------------------------
# Cassette metadata
# ---------------------------------------------------------------------------

class Target(BaseModel):
    """Fingerprint of the agent endpoint at recording time."""
    endpoint_shape: str
    model: str
    system_prompt_sha256: str
    tool_schema_sha256: str


class Planted(BaseModel):
    """A canary or marker deliberately planted for assertion checking."""
    canary: str
    location: str


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------

Verdict = Literal["PASS", "CRASH", "DIVERGED"]


# ---------------------------------------------------------------------------
# Cassette (top-level recording)
# ---------------------------------------------------------------------------

class Cassette(BaseModel):
    """
    A complete recorded adversarial (or benign) run.

    This is the unit of storage under cassettes/<cassette_id>.json.
    """
    cassette_id: str
    schema_version: str = "1.0"
    kind: Literal["adversarial", "benign"]
    title: str
    persona: str
    recorded_at: datetime
    target: Target
    planted: list[Planted] = Field(default_factory=list)
    turns: list[Turn]
    assertions: list[Assertion]
    recorded_verdict: Verdict
    crash_turn: int | None = None


# ---------------------------------------------------------------------------
# Replay result
# ---------------------------------------------------------------------------

class ReplayResult(BaseModel):
    """Output of replaying a cassette in any mode."""
    cassette_id: str
    mode: str
    runs: int
    verdicts: list[Verdict]
    summary: str
    crash_turn: int | None = None
    failed_assertion: str | None = None
    divergences: list[str] = Field(default_factory=list)
    duration_ms: int
    network_calls: int
