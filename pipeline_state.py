"""
Pipeline State Tracker
======================

Manages pipeline_state.json manifests that track which steps have been
completed for each problem sheet. Enables human-in-the-loop workflows
by letting users inspect state between steps.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STEPS = ("parse", "route", "solve", "verify", "generate")

_EMPTY_STEP = {"status": "pending"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def state_path(work_dir: Path) -> Path:
    return work_dir / "pipeline_state.json"


def load_state(work_dir: Path) -> dict[str, Any]:
    """Load pipeline state from a work directory, or return empty state."""
    p = state_path(work_dir)
    if p.exists():
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {"steps": {s: dict(_EMPTY_STEP) for s in STEPS}}


def save_state(work_dir: Path, state: dict[str, Any]) -> None:
    """Persist pipeline state to disk."""
    p = state_path(work_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def init_state(
    work_dir: Path,
    sheet_id: int,
    sheet_file: str | None = None,
    config_file: str | None = None,
    course_id: str | None = None,
) -> dict[str, Any]:
    """Initialise a fresh pipeline state."""
    state = {
        "sheet_id": sheet_id,
        "sheet_file": sheet_file,
        "config_file": config_file,
        "course_id": course_id,
        "created": _now(),
        "steps": {s: dict(_EMPTY_STEP) for s in STEPS},
    }
    save_state(work_dir, state)
    return state


def mark_step(
    work_dir: Path,
    step: str,
    status: str = "done",
    **extra: Any,
) -> dict[str, Any]:
    """Update a step's status in the manifest."""
    state = load_state(work_dir)
    state["steps"].setdefault(step, {})
    state["steps"][step] = {"status": status, "timestamp": _now(), **extra}
    save_state(work_dir, state)
    return state


def get_step(work_dir: Path, step: str) -> dict[str, Any]:
    """Get a single step's state."""
    state = load_state(work_dir)
    return state.get("steps", {}).get(step, dict(_EMPTY_STEP))
