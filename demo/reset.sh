#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# demo/reset.sh — Restore clean permissive policy and confirm cassette state
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

echo "[RESET] Restoring permissive target_agent/policy.py..."

cat << 'EOF' > target_agent/policy.py
"""
Safety policy for the banking-support agent.

╔══════════════════════════════════════════════════════════════════════╗
║  This is the ONLY file CrashTest's fix loop edits.                 ║
║                                                                     ║
║  It ships PERMISSIVE BY DEFAULT so CrashTest has something real     ║
║  to catch. Guards are added here iteratively until all adversarial  ║
║  scenarios pass without breaking benign ones.                       ║
╚══════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Decision:
    allowed: bool
    reason: str = ""


def check(tool_name: str, args: dict, history: list) -> Decision:
    """
    Evaluate whether a tool call should be permitted.

    Parameters
    ----------
    tool_name : str
        Name of the tool being invoked (e.g. "change_contact").
    args : dict
        The arguments the agent wants to pass to the tool.
    history : list
        The conversation history up to this point (list of message dicts).

    Returns
    -------
    Decision
        Decision.allowed=True  → proceed with the tool call.
        Decision.allowed=False → block the call; reason is returned to the agent.
    """
    # PERMISSIVE BY DEFAULT — guards are added here by the fix loop.
    return Decision(allowed=True)
EOF

echo "[RESET] Clean state restored successfully."
echo "[RESET] Running verification replay..."

python3 -c "
from crashtest import store, replay

sc01 = store.load('sc-01')
b01 = store.load('b-01')

res_sc01 = replay.frozen(sc01, runs=1)
res_b01 = replay.frozen(b01, runs=1)

assert 'CRASH' in res_sc01.verdicts, 'sc-01 must CRASH on permissive policy'
assert 'PASS' in res_b01.verdicts, 'b-01 must PASS on permissive policy'
print('[RESET] Verified: sc-01 CRASH, b-01 PASS.')
"
