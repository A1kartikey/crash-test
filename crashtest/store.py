"""Cassette storage — save / load / list JSON cassettes."""

from __future__ import annotations

import json
from pathlib import Path

from .schema import Cassette

# Default cassette directory — sibling of the crashtest package.
_CASSETTES_DIR = Path(__file__).resolve().parent.parent / "cassettes"


def _cassettes_dir() -> Path:
    """Return (and create if needed) the cassettes directory."""
    _CASSETTES_DIR.mkdir(parents=True, exist_ok=True)
    return _CASSETTES_DIR


def save(cassette: Cassette) -> Path:
    """
    Persist a cassette to cassettes/<cassette_id>.json.

    Returns the path written.
    """
    dest = _cassettes_dir() / f"{cassette.cassette_id}.json"
    dest.write_text(
        cassette.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return dest


def load(cassette_id: str) -> Cassette:
    """
    Load a cassette by ID from the cassettes directory.

    Raises FileNotFoundError if the cassette does not exist.
    Raises ValueError if cassette JSON is invalid or missing required fields.
    """
    path = _cassettes_dir() / f"{cassette_id}.json"
    raw = path.read_text(encoding="utf-8")
    try:
        return Cassette.model_validate_json(raw)
    except Exception as e:
        from pydantic import ValidationError
        if isinstance(e, ValidationError) and e.errors():
            missing_fields = [err.get("loc", ["field"])[-1] for err in e.errors() if err.get("loc")]
            if missing_fields:
                raise ValueError(f"Corrupt cassette '{cassette_id}': missing required field(s) {missing_fields}")
        raise ValueError(f"Corrupt cassette '{cassette_id}': invalid JSON content ({e})")


def list_cassettes() -> list[str]:
    """
    Return a sorted list of cassette IDs present on disk.

    Each ID corresponds to a cassettes/<id>.json file.
    """
    directory = _cassettes_dir()
    return sorted(
        p.stem for p in directory.glob("*.json")
    )
