import json

import pytest

from agentic_cpu_bench.artifacts import summarize_events, summarize_run_root


def _write_events(path, *, side="grace", ok=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    events = [
        {"type": "run_started", "run_id": f"r-{side}", "side": side, "task_id": "task1", "mode": "replay"},
        {"type": "command_finished", "run_id": f"r-{side}", "side": side, "command": "a", "duration_ms": 10.0},
        {"type": "command_finished", "run_id": f"r-{side}", "side": side, "command": "b", "duration_ms": 20.0},
        {"type": "run_finished", "run_id": f"r-{side}", "side": side, "ok": ok, "completion_ms": 40.0},
    ]
    path.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")


def test_summarize_events_derives_dashboard_fields(tmp_path):
    events_path = tmp_path / "events.jsonl"
    _write_events(events_path, side="x86")

    summary = summarize_events(events_path)

    assert summary["run_id"] == "r-x86"
    assert summary["side"] == "x86"
    assert summary["task_id"] == "task1"
    assert summary["mode"] == "replay"
    assert summary["ok"] is True
    assert summary["command_count"] == 2
    assert summary["cpu_tool_step_ms"] == 30.0
    assert summary["completion_ms"] == 40.0
    assert summary["agents_at_sla"] == 1


def test_summarize_run_root_reads_grace_and_x86(tmp_path):
    _write_events(tmp_path / "grace" / "artifacts" / "events.jsonl", side="grace")
    _write_events(tmp_path / "x86" / "artifacts" / "events.jsonl", side="x86", ok=False)

    summaries = summarize_run_root(tmp_path)

    assert [summary["side"] for summary in summaries] == ["grace", "x86"]
    assert summaries[1]["agents_at_sla"] == 0


def test_summarize_events_rejects_incomplete_events(tmp_path):
    events_path = tmp_path / "events.jsonl"
    events_path.write_text(json.dumps({"type": "run_started"}) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="run_finished"):
        summarize_events(events_path)
