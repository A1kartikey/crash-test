"""
FastAPI application exposing CrashTest functionality over HTTP.

Endpoints:
  GET  /api/health        -> {"ok": true, "offline_capable": true}
  GET  /api/cassettes     -> list of cassette summaries [{id, kind, title, persona, recorded_verdict, crash_turn, turn_count}]
  GET  /api/cassettes/{id}-> full cassette JSON
  POST /api/replay/{id}   -> body {mode, runs}; returns ReplayResult
  GET  /                  -> serves ui/index.html
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from crashtest import replay, store
from crashtest.schema import ReplayResult

app = FastAPI(title="CrashTest API", version="0.1.0")

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"
if _UI_DIR.exists():
    app.mount("/ui", StaticFiles(directory=_UI_DIR), name="ui")


class ReplayRequest(BaseModel):
    mode: str = "frozen"
    runs: int = 1


@app.get("/api/health")
def get_health() -> dict[str, bool]:
    """Health check endpoint."""
    return {"ok": True, "offline_capable": True}


@app.get("/api/cassettes")
def list_cassettes() -> list[dict[str, Any]]:
    """List all recorded cassettes with metadata summary."""
    cassette_ids = store.list_cassettes()
    summaries = []
    for cid in cassette_ids:
        c = store.load(cid)
        summaries.append({
            "id": c.cassette_id,
            "kind": c.kind,
            "title": c.title,
            "persona": c.persona,
            "recorded_verdict": c.recorded_verdict,
            "crash_turn": c.crash_turn,
            "turn_count": len(c.turns),
        })
    return summaries


@app.get("/api/cassettes/{cassette_id}")
def get_cassette(cassette_id: str) -> dict[str, Any]:
    """Get full cassette by ID."""
    try:
        c = store.load(cassette_id)
        return c.model_dump(mode="json")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Cassette not found: {cassette_id}")


@app.post("/api/replay/{cassette_id}", response_model=ReplayResult)
def replay_cassette_api(cassette_id: str, body: ReplayRequest) -> ReplayResult:
    """Replay a cassette in frozen or verify mode."""
    try:
        c = store.load(cassette_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Cassette not found: {cassette_id}")

    try:
        if body.mode == "frozen":
            return replay.frozen(c, runs=body.runs)
        elif body.mode == "verify":
            return replay.verify(c, runs=body.runs)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported replay mode: {body.mode}")
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/")
def get_index():
    """Serve the single-page UI index HTML."""
    index_path = _UI_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "CrashTest API online. UI index.html not yet created."}
