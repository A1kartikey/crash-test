"""
Shared test configuration, fixtures, and stubs for CrashTest.
"""

from __future__ import annotations

import os
from pathlib import Path
import pytest

from crashtest.schema import ToolCall


@pytest.fixture
def no_network(monkeypatch):
    """Monkeypatch OpenAI client to ensure no external HTTP requests are made."""
    def block_openai(*args, **kwargs):
        raise RuntimeError("NETWORK CALL ATTEMPTED! Tests must run offline.")

    monkeypatch.setattr("openai.OpenAI", block_openai)
    monkeypatch.setattr("target_agent.agent._get_client", block_openai)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


class ScriptableAgentClient:
    """
    Scriptable stub AgentClient that returns preset responses based on tool policies
    or prompt contents without contacting external LLM endpoints.
    """

    def __init__(self, mode: str = "guarded"):
        self.mode = mode  # "permissive", "guarded", "refusing"

    def step(self, messages: list[dict]) -> dict:
        last_msg = messages[-1]["content"] if messages else ""

        # Guarded policy behavior
        if self.mode == "guarded":
            if "change" in last_msg.lower() and "phone" in last_msg.lower() and "verify" not in last_msg.lower():
                return {
                    "content": "I cannot change your contact phone number without identity verification.",
                    "tool_calls": [],
                }
            if "C-3029" in last_msg or "status" in last_msg.lower():
                # For sc-02: lookup customer, but do not exfiltrate canary
                return {
                    "content": "The account status for customer C-3029 is active.",
                    "tool_calls": [
                        {"name": "lookup_customer", "arguments": {"customer_id": "C-3029"}}
                    ],
                }
            if "refund" in last_msg.lower():
                return {
                    "content": "Processing refund request.",
                    "tool_calls": [
                        {"name": "issue_refund", "arguments": {"customer_id": "C-7781", "amount_inr": 2000.0, "reason": "duplicate"}}
                    ],
                }
            if "phone" in last_msg.lower() and "verification" in last_msg.lower():
                return {
                    "content": "Contact phone updated.",
                    "tool_calls": [
                        {"name": "change_contact", "arguments": {"customer_id": "C-7781", "new_phone": "9876543210", "verified": True}}
                    ],
                }

        # Fallback default
        return {"content": "How may I assist you today?", "tool_calls": []}


@pytest.fixture
def stub_agent_client():
    return ScriptableAgentClient(mode="guarded")
