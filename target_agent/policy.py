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
