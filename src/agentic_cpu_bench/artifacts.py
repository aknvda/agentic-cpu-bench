from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"events file not found: {path}")
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON event at {path}:{line_number}") from exc
        if not isinstance(event, dict):
            raise ValueError(f"event at {path}:{line_number} is not an object")
        events.append(event)
    return events


def summarize_events(path: Path) -> dict[str, Any]:
    events = read_events(path)
    started = next((event for event in events if event.get("type") == "run_started"), None)
    finished = next((event for event in reversed(events) if event.get("type") == "run_finished"), None)
    if started is None:
        raise ValueError(f"events file missing run_started: {path}")
    if finished is None:
        raise ValueError(f"events file missing run_finished: {path}")

    command_events = [event for event in events if event.get("type") == "command_finished"]
    ok = bool(finished.get("ok"))
    return {
        "run_id": started.get("run_id", "unknown"),
        "task_id": started.get("task_id", "unknown"),
        "side": started.get("side", "unknown"),
        "mode": started.get("mode", "unknown"),
        "ok": ok,
        "completion_ms": float(finished.get("completion_ms", 0.0)),
        "cpu_tool_step_ms": sum(float(event.get("duration_ms", 0.0)) for event in command_events),
        "command_count": len(command_events),
        "agents_at_sla": 1 if ok else 0,
    }


def summarize_run_root(run_root: Path, sides: tuple[str, ...] = ("grace", "x86")) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for side in sides:
        summaries.append(summarize_events(run_root / side / "artifacts" / "events.jsonl"))
    return summaries
