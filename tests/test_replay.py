import json
from pathlib import Path

from agentic_cpu_bench.replay import replay_expected_patch
from agentic_cpu_bench.task_model import load_task


def _read_events(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_replay_expected_patch_records_events_and_passes(tmp_path):
    task = load_task(Path("tasks/python_cpp_bugfix/manifest.json"))
    result = replay_expected_patch(task, tmp_path / "run", run_id="r1", side="grace")
    assert result.ok is True
    assert result.completion_ms > 0
    assert [item.name for item in result.commands] == [
        "apply-patch",
        "python-tests",
        "cpp-build",
        "cpp-tests",
        "lint",
        "static-analysis",
    ]
    events = (tmp_path / "run" / "artifacts" / "events.jsonl").read_text(encoding="utf-8")
    assert "run_started" in events
    assert "command_finished" in events
    assert "run_finished" in events


def test_replay_expected_patch_resets_events_when_reusing_run_dir(tmp_path):
    task = load_task(Path("tasks/python_cpp_bugfix/manifest.json"))
    run_dir = tmp_path / "run"

    replay_expected_patch(task, run_dir, run_id="first", side="grace")
    replay_expected_patch(task, run_dir, run_id="second", side="x86")

    events = _read_events(run_dir / "artifacts" / "events.jsonl")
    assert [event["type"] for event in events] == [
        "run_started",
        "command_started",
        "command_finished",
        "command_started",
        "command_finished",
        "command_started",
        "command_finished",
        "command_started",
        "command_finished",
        "command_started",
        "command_finished",
        "command_started",
        "command_finished",
        "run_finished",
    ]
    assert {event["run_id"] for event in events} == {"second"}
