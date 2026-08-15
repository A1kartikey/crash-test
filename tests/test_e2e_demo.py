"""
End-to-end test suite for CrashTest demo path and negative edge cases (all offline).
"""

from __future__ import annotations

import json
import pytest

from crashtest import replay, store
from crashtest.client import LiveClient


def test_e2e_demo_path_frozen(no_network):
    """
    Step 1: Load the 4 committed cassettes.
    Step 2: Frozen replay each.
    Assert sc-01 and sc-02 CRASH, b-01 and b-02 PASS.
    """
    sc01 = store.load("sc-01")
    sc02 = store.load("sc-02")
    b01 = store.load("b-01")
    b02 = store.load("b-02")

    res_sc01 = replay.frozen(sc01, runs=1)
    res_sc02 = replay.frozen(sc02, runs=1)
    res_b01 = replay.frozen(b01, runs=1)
    res_b02 = replay.frozen(b02, runs=1)

    assert "CRASH" in res_sc01.verdicts
    assert "CRASH" in res_sc02.verdicts
    assert "PASS" in res_b01.verdicts
    assert "PASS" in res_b02.verdicts


def test_e2e_demo_path_guarded_verify(stub_agent_client, no_network):
    """
    Step 3: Apply policy guard / use stub agent client with guarded behavior.
    Step 4: Verify replay with stub client.
    Assert all four pass or report DIVERGED(GUARDED), zero CRASHes on benign/adversarial.
    """
    sc01 = store.load("sc-01")
    sc02 = store.load("sc-02")
    b01 = store.load("b-01")
    b02 = store.load("b-02")

    res_sc01 = replay.verify(sc01, agent_client=stub_agent_client, runs=1)
    res_sc02 = replay.verify(sc02, agent_client=stub_agent_client, runs=1)
    res_b01 = replay.verify(b01, agent_client=stub_agent_client, runs=1)
    res_b02 = replay.verify(b02, agent_client=stub_agent_client, runs=1)

    # Adversarial cassettes become PASS or DIVERGED (GUARDED)
    assert res_sc01.verdicts[0] in ("PASS", "DIVERGED")
    assert res_sc02.verdicts[0] in ("PASS", "DIVERGED")
    # Benign cassettes pass without CRASH
    assert "CRASH" not in res_b01.verdicts
    assert "CRASH" not in res_b02.verdicts


# ---------------------------------------------------------------------------
# Negative Tests
# ---------------------------------------------------------------------------

def test_negative_malformed_cassette(tmp_path, monkeypatch):
    """Assert malformed JSON in cassette directory raises a clear error."""
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{this is not valid json")

    monkeypatch.setattr(store, "_CASSETTES_DIR", tmp_path)

    with pytest.raises(Exception) as exc_info:
        store.load("bad")
    assert "JSON" in str(exc_info.value) or "Expecting value" in str(exc_info.value) or "invalid" in str(exc_info.value).lower()


def test_negative_missing_openai_key_live_client(monkeypatch):
    """
    Assert missing OPENAI_API_KEY causes LiveClient.step to raise an actionable RuntimeError,
    while frozen replay still works offline without key.
    """
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    # 1. Frozen replay still works
    sc01 = store.load("sc-01")
    res = replay.frozen(sc01, runs=1)
    assert res.network_calls == 0

    # 2. LiveClient step raises actionable RuntimeError
    client = LiveClient()
    with pytest.raises(RuntimeError) as exc:
        client.step([{"role": "user", "content": "hello"}])
    assert "OPENAI_API_KEY" in str(exc.value)


@pytest.mark.live
def test_live_model_call_stub():
    """Stub test marked @pytest.mark.live for external model verification when key is present."""
    pass
