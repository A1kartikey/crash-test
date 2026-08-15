"""
Replay engine — FROZEN and VERIFICATION replay modes.

FROZEN mode: ZERO network calls. Reads agent turns straight from the cassette and runs assertions.
VERIFICATION mode: Attacker turns & tool results come from cassette; agent turns come from LiveClient.
"""

from __future__ import annotations

import json
import time
import typer

from crashtest import assertions, client, divergence
from crashtest.schema import Cassette, ReplayResult, ToolCall, Turn, Verdict
from target_agent import policy, tools
from target_agent.agent import SYSTEM_PROMPT, system_prompt_sha256, tool_schema_sha256


def frozen(cassette: Cassette, runs: int = 1) -> ReplayResult:
    """
    Run frozen replay N times against a recorded cassette.

    FROZEN replay makes ZERO network calls and serves everything from the cassette.
    """
    # 1. Fingerprint check
    curr_prompt_sha = system_prompt_sha256()
    curr_tool_sha = tool_schema_sha256()
    if cassette.target.system_prompt_sha256 != curr_prompt_sha or cassette.target.tool_schema_sha256 != curr_tool_sha:
        typer.secho(
            "Warning: target changed since recording — re-record recommended",
            fg=typer.colors.YELLOW,
            err=True,
        )

    client.reset_network_calls()
    start_time = time.perf_counter()

    verdicts: list[Verdict] = []
    last_crash_turn: int | None = None
    last_failed_assertion: str | None = None

    for _ in range(runs):
        res = assertions.evaluate(cassette.assertions, cassette.turns)
        if res.passed:
            verdicts.append("PASS")
        else:
            verdicts.append("CRASH")
            last_crash_turn = res.crash_turn
            last_failed_assertion = res.failed_assertion

    duration_ms = int((time.perf_counter() - start_time) * 1000)

    crash_count = verdicts.count("CRASH")
    if crash_count > 0:
        summary = f"CRASH {crash_count}/{runs}"
    else:
        summary = f"PASS {runs}/{runs}"

    return ReplayResult(
        cassette_id=cassette.cassette_id,
        mode="frozen",
        runs=runs,
        verdicts=verdicts,
        summary=summary,
        crash_turn=last_crash_turn if crash_count > 0 else None,
        failed_assertion=last_failed_assertion if crash_count > 0 else None,
        divergences=[],
        duration_ms=duration_ms,
        network_calls=0,
    )


def verify(cassette: Cassette, agent_client: client.AgentClient | None = None, runs: int = 1) -> ReplayResult:
    """
    Run verification replay N times against a cassette with a live agent.

    Attacker turns and tool results come from the cassette.
    Agent turns come from the live agent client.
    """
    # 1. Fingerprint check
    curr_prompt_sha = system_prompt_sha256()
    curr_tool_sha = tool_schema_sha256()
    if cassette.target.system_prompt_sha256 != curr_prompt_sha or cassette.target.tool_schema_sha256 != curr_tool_sha:
        typer.secho(
            "Warning: target changed since recording — re-record recommended",
            fg=typer.colors.YELLOW,
            err=True,
        )

    if agent_client is None:
        agent_client = client.LiveClient()

    start_time = time.perf_counter()
    client.reset_network_calls()

    verdicts: list[Verdict] = []
    all_divergences: list[str] = []
    last_crash_turn: int | None = None
    last_failed_assertion: str | None = None

    for _ in range(runs):
        tools.reset_state()
        live_turns: list[Turn] = []
        openai_messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

        # Extract attacker turns from cassette
        attacker_turns = [t for t in cassette.turns if t.role == "attacker"]

        # Pre-index cassette tool results by tool_name/turn if needed
        recorded_tool_turns = [t for t in cassette.turns if t.role == "tool"]
        tool_turn_index = 0

        turn_n = 0

        for atk_turn in attacker_turns:
            live_turns.append(Turn(n=turn_n, role="attacker", content=atk_turn.content))
            openai_messages.append({"role": "user", "content": atk_turn.content})
            turn_n += 1

            # Step live agent
            step_res = agent_client.step(openai_messages)

            agent_tool_calls = [
                ToolCall(name=tc["name"], args=tc["arguments"])
                for tc in step_res.get("tool_calls", [])
                if not tc.get("blocked")
            ]

            live_agent_turn = Turn(
                n=turn_n,
                role="agent",
                content=step_res.get("content"),
                tool_calls=agent_tool_calls,
            )
            live_turns.append(live_agent_turn)
            turn_n += 1

            # Handle live tool calls
            if step_res.get("tool_calls"):
                for tc in step_res["tool_calls"]:
                    tc_name = tc["name"]
                    tc_args = tc["arguments"]

                    decision = policy.check(tc_name, tc_args, openai_messages)
                    if decision.allowed:
                        # Serve tool result from cassette if available, else execute
                        if tool_turn_index < len(recorded_tool_turns):
                            tool_out = recorded_tool_turns[tool_turn_index].content or "{}"
                            tool_turn_index += 1
                        else:
                            tool_out = tools.execute(tc_name, tc_args)
                    else:
                        tool_out = json.dumps({"error": f"Policy blocked: {decision.reason}"})

                    live_turns.append(Turn(n=turn_n, role="tool", content=tool_out, tool_name=tc_name))
                    openai_messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", f"call_{turn_n}"),
                        "content": tool_out,
                    })
                    turn_n += 1

        # Evaluate assertions on live turns
        eval_res = assertions.evaluate(cassette.assertions, live_turns)

        # Compare recorded agent turns vs live agent turns for divergence
        rec_agent_turns = [t for t in cassette.turns if t.role == "agent"]
        live_agent_turns = [t for t in live_turns if t.role == "agent"]

        run_divergence_labels = []

        for r_turn, l_turn in zip(rec_agent_turns, live_agent_turns):
            # Check if recorded turn violated assertion
            r_eval = assertions.evaluate(cassette.assertions, [r_turn])
            l_eval = assertions.evaluate(cassette.assertions, [l_turn])

            div = divergence.classify_turn(
                turn_n=l_turn.n,
                recorded_turn=r_turn,
                live_turn=l_turn,
                cassette_kind=cassette.kind,
                recorded_violating=(not r_eval.passed),
                live_violating=(not l_eval.passed),
            )
            if div.classification != "MATCHED":
                div_msg = f"DIVERGED @ turn {l_turn.n} ({div.classification}): {div.reason}"
                run_divergence_labels.append(div.classification)
                all_divergences.append(div_msg)

        if not eval_res.passed:
            verdicts.append("CRASH")
            last_crash_turn = eval_res.crash_turn
            last_failed_assertion = eval_res.failed_assertion
        elif "GUARDED" in run_divergence_labels:
            verdicts.append("DIVERGED")
            last_crash_turn = rec_agent_turns[0].n if rec_agent_turns else None
            last_failed_assertion = "Agent fixed: attack guarded"
        elif "DRIFTED" in run_divergence_labels:
            verdicts.append("DIVERGED")
        else:
            verdicts.append("PASS")

    duration_ms = int((time.perf_counter() - start_time) * 1000)

    crash_count = verdicts.count("CRASH")
    diverged_count = verdicts.count("DIVERGED")
    pass_count = verdicts.count("PASS")

    if crash_count > 0:
        summary = f"CRASH {crash_count}/{runs}"
    elif diverged_count > 0:
        summary = f"DIVERGED {diverged_count}/{runs}"
    else:
        summary = f"PASS {runs}/{runs}"

    return ReplayResult(
        cassette_id=cassette.cassette_id,
        mode="verify",
        runs=runs,
        verdicts=verdicts,
        summary=summary,
        crash_turn=last_crash_turn if (crash_count > 0 or diverged_count > 0) else None,
        failed_assertion=last_failed_assertion if (crash_count > 0 or diverged_count > 0) else None,
        divergences=all_divergences,
        duration_ms=duration_ms,
        network_calls=client.network_calls,
    )
