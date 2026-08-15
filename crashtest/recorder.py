"""
RECORD mode — run a scenario against the live agent and save a cassette.

Flow:
  load YAML → for each attacker turn →
    append attacker Turn → LiveClient.step →
    append agent Turn → for each tool_call →
      policy.check → tools.execute → append tool Turn →
  evaluate assertions → set verdict & crash_turn → save cassette
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from crashtest import assertions, store
from crashtest.client import LiveClient, reset_network_calls
from crashtest.schema import (
    Assertion,
    Cassette,
    Planted,
    Target,
    ToolCall,
    Turn,
)
from target_agent import policy, tools
from target_agent.agent import SYSTEM_PROMPT, system_prompt_sha256, tool_schema_sha256

# ---------------------------------------------------------------------------
# Scenario loader
# ---------------------------------------------------------------------------

_SCENARIOS_DIR = Path(__file__).resolve().parent.parent / "scenarios"


def _load_scenario(scenario_id: str) -> dict[str, Any]:
    """Load a scenario YAML file by ID."""
    path = _SCENARIOS_DIR / f"{scenario_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Scenario not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Record
# ---------------------------------------------------------------------------

def record(scenario_id: str) -> Cassette:
    """
    Record a cassette by running a scenario against the live agent.

    Resets tool state, runs scripted attacker turns against the live agent,
    evaluates assertions, and saves the cassette.
    """
    scenario = _load_scenario(scenario_id)
    attacker_turns: list[str] = scenario["attacker_turns"]
    max_turns: int = scenario.get("max_turns", len(attacker_turns) * 3)
    scenario_assertions = [Assertion(**a) for a in scenario.get("assertions", [])]
    planted_list = [Planted(**p) for p in scenario.get("planted", [])]

    # Handle sc-02 style tool-result injection
    injection = scenario.get("tool_result_injection")

    # Reset state
    tools.reset_state()
    reset_network_calls()
    client = LiveClient()

    # Build the OpenAI message list (system + conversation)
    openai_messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ]

    # Cassette turns
    cassette_turns: list[Turn] = []
    turn_n = 0

    for attacker_text in attacker_turns:
        if turn_n >= max_turns:
            break

        # ── Attacker turn ──
        cassette_turns.append(Turn(
            n=turn_n,
            role="attacker",
            content=attacker_text,
        ))
        openai_messages.append({"role": "user", "content": attacker_text})
        turn_n += 1

        # ── Agent turn (may loop if tool calls are made) ──
        while turn_n < max_turns:
            result = client.step(openai_messages)

            agent_tool_calls = []
            if result["tool_calls"]:
                for tc in result["tool_calls"]:
                    agent_tool_calls.append(ToolCall(
                        name=tc["name"],
                        args=tc["arguments"],
                    ))

            # Record agent turn
            cassette_turns.append(Turn(
                n=turn_n,
                role="agent",
                content=result["content"],
                tool_calls=agent_tool_calls,
            ))

            # Add assistant message to OpenAI conversation
            assistant_msg: dict[str, Any] = {"role": "assistant", "content": result["content"]}
            if result["tool_calls"]:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.get("id", f"call_{turn_n}_{i}"),
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["arguments"]),
                        },
                    }
                    for i, tc in enumerate(result["tool_calls"])
                ]
                if assistant_msg["content"] is None:
                    assistant_msg["content"] = ""

            openai_messages.append(assistant_msg)
            turn_n += 1

            # ── Process tool calls ──
            if not result["tool_calls"]:
                break  # Agent gave a text reply, move to next attacker turn

            for tc in result["tool_calls"]:
                if turn_n >= max_turns:
                    break

                tc_name = tc["name"]
                tc_args = tc["arguments"]
                tc_id = tc.get("id", f"call_{turn_n}")

                # Policy chokepoint
                decision = policy.check(tc_name, tc_args, openai_messages)

                if decision.allowed:
                    # Execute tool
                    tool_output = tools.execute(tc_name, tc_args)

                    # ── Inject into tool result for sc-02 style scenarios ──
                    if injection and tc_name == injection.get("tool"):
                        inject_customer = injection.get("customer_id")
                        if inject_customer and inject_customer in json.dumps(tc_args):
                            try:
                                parsed = json.loads(tool_output)
                                parsed["_support_ticket_note"] = injection["append_to_result"].strip()
                                tool_output = json.dumps(parsed)
                            except Exception:
                                pass
                else:
                    tool_output = json.dumps({
                        "error": f"Policy blocked: {decision.reason}"
                    })

                cassette_turns.append(Turn(
                    n=turn_n,
                    role="tool",
                    content=tool_output,
                    tool_name=tc_name,
                ))
                openai_messages.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": tool_output,
                })
                turn_n += 1

            continue

    # ── Evaluate assertions ──
    res = assertions.evaluate(scenario_assertions, cassette_turns)
    verdict = "PASS" if res.passed else "CRASH"

    # ── Build and save cassette ──
    cassette = Cassette(
        cassette_id=scenario_id,
        schema_version="1.0",
        kind=scenario.get("kind", "adversarial"),
        title=scenario.get("title", scenario_id),
        persona=scenario.get("persona", "unknown"),
        recorded_at=datetime.now(timezone.utc),
        target=Target(
            endpoint_shape="POST /v1/chat/completions",
            model="gpt-4o-mini",
            system_prompt_sha256=system_prompt_sha256(),
            tool_schema_sha256=tool_schema_sha256(),
        ),
        planted=planted_list,
        turns=cassette_turns,
        assertions=scenario_assertions,
        recorded_verdict=verdict,
        crash_turn=res.crash_turn,
    )

    path = store.save(cassette)
    return cassette
