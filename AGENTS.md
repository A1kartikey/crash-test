# CrashTest — Agent Remediation Loop

## Overview

CrashTest records adversarial failures against an AI agent as JSON "cassettes"
and replays them deterministically as regression tests. When a cassette reports
`CRASH`, the failing tool call and assertion are surfaced as structured JSON
so a coding agent can patch the safety policy.

## Cassette Format

Each cassette (`cassettes/<id>.json`) contains:

| Field              | Description                                              |
|--------------------|----------------------------------------------------------|
| `cassette_id`      | Unique identifier (e.g. `sc-01`)                         |
| `kind`             | `adversarial` or `benign`                                |
| `turns`            | Ordered list of attacker, agent, and tool turns           |
| `assertions`       | Deterministic checks (canary_absent, tool_arg_constraint…)|
| `recorded_verdict` | `PASS`, `CRASH`, or `DIVERGED`                           |
| `crash_turn`       | Turn number where the first assertion failed (if any)     |

Agent turns may contain `tool_calls` — each with `name` and `args`.

## Patch Surface

**`target_agent/policy.py` is the ONLY file you may modify.**

It exports a single function:

```python
def check(tool_name: str, args: dict, history: list) -> Decision:
```

- Return `Decision(allowed=True)` to permit the tool call.
- Return `Decision(allowed=False, reason="...")` to block it.

The agent calls `policy.check()` before executing every tool call. Guards
added here are the mechanism for fixing adversarial failures.

## Remediation Workflow

When a CrashTest cassette fails:

1. **Identify failures.**
   Run `crashtest replay --failing --json`.
   This outputs one JSON object per failing cassette containing:
   `id`, `crash_turn`, `offending_tool_call`, `failed_assertion`, `observed_args`.

2. **Read the crash evidence.**
   From the JSON output, note the crash turn number, the offending tool call
   name, and the assertion that fired (e.g. `tool_arg_constraint` requiring
   `args.verified == true` on `change_contact`).

3. **Patch `target_agent/policy.py`.**
   Write the smallest guard that satisfies the assertion. For example:
   ```python
   if tool_name == "change_contact" and not args.get("verified"):
       return Decision(allowed=False, reason="Identity verification required")
   ```
   **Do not edit any other file.** If a guard cannot be written without
   touching another file, report that — do not widen scope.

4. **Verify the fix.**
   Run `crashtest replay --all --mode verify`.
   Every cassette must show its expected verdict:
   - Adversarial cassettes: `PASS` or `DIVERGED(GUARDED)`
   - Benign cassettes: `PASS`

5. **Check for over-broad guards.**
   If any benign cassette returns `BROKEN`, your guard is too broad.
   Revert the change and write a narrower guard that blocks only the
   adversarial pattern without disrupting legitimate requests.

6. **Report results.**
   Output before/after verdicts per cassette so the change is auditable.

## Quick Reference

```bash
# See what's failing
crashtest replay --failing --json

# Replay everything after a fix (frozen, offline)
crashtest replay --all --mode frozen

# Replay everything with the live agent
crashtest replay --all --mode verify

# Show a specific cassette turn-by-turn
crashtest show sc-01

# Exit codes
#   0 = all pass
#   1 = any CRASH (adversarial failure)
#   2 = any BROKEN (benign regression)
#   3 = usage error
```

## Constraints

- **policy.py is the ONLY file you may modify.** Period.
- Do not add new tools, change the system prompt, or modify the agent loop.
- Do not use an LLM to judge verdicts — all assertions are deterministic.
- If a guard cannot be expressed in `policy.check()`, report that and stop.
