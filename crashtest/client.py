"""
Agent client abstraction — live and frozen variants.

LiveClient: delegates to target_agent.agent.step, counts network calls.
FrozenClient: serves recorded turns from a cassette, zero network calls.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from crashtest.schema import Cassette

# Module-level counter — tracks OpenAI calls made during this process.
network_calls: int = 0


def reset_network_calls() -> None:
    global network_calls
    network_calls = 0


@runtime_checkable
class AgentClient(Protocol):
    """Protocol every client variant must satisfy."""

    def step(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Run one agent turn.

        Returns dict with keys "content" (str|None) and "tool_calls" (list).
        """
        ...


# ---------------------------------------------------------------------------
# LiveClient — real OpenAI calls
# ---------------------------------------------------------------------------

class LiveClient:
    """Delegates to target_agent.agent.step; increments network_calls."""

    def step(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        global network_calls
        from target_agent.agent import step as agent_step

        network_calls += 1
        return agent_step(messages)


# ---------------------------------------------------------------------------
# FrozenClient — replays from cassette, zero network
# ---------------------------------------------------------------------------

class FrozenClient:
    """
    Returns the recorded agent turn for turn n.

    Raises RuntimeError if any network call is attempted — frozen replay
    must make ZERO network calls.
    """

    def __init__(self, cassette: Cassette) -> None:
        self._cassette = cassette
        # Pre-index agent turns by turn number
        self._agent_turns: dict[int, dict[str, Any]] = {}
        for turn in cassette.turns:
            if turn.role == "agent":
                entry: dict[str, Any] = {"content": turn.content, "tool_calls": []}
                for tc in turn.tool_calls:
                    entry["tool_calls"].append({
                        "id": f"frozen_{turn.n}_{tc.name}",
                        "name": tc.name,
                        "arguments": tc.args,
                        "blocked": False,
                    })
                self._agent_turns[turn.n] = entry
        self._call_index = 0
        self._agent_turn_numbers = sorted(self._agent_turns.keys())

    def step(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Return the next recorded agent turn. No network calls."""
        if self._call_index >= len(self._agent_turn_numbers):
            raise RuntimeError(
                "FrozenClient exhausted: no more recorded agent turns"
            )
        turn_n = self._agent_turn_numbers[self._call_index]
        self._call_index += 1
        return self._agent_turns[turn_n]
