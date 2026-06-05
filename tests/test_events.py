import json

import pytest

from agentic_cpu_bench.events import EventWriter


def test_event_writer_writes_jsonl(tmp_path):
    path = tmp_path / "events.jsonl"
    writer = EventWriter(path)
    writer.write("command_finished", run_id="r1", side="grace", command="pytest", duration_ms=12.5)
    data = json.loads(path.read_text(encoding="utf-8").strip())
    assert data["type"] == "command_finished"
    assert data["run_id"] == "r1"
    assert data["side"] == "grace"
    assert data["command"] == "pytest"
    assert data["duration_ms"] == 12.5
    assert isinstance(data["ts"], float)


def test_event_writer_can_stream_jsonl_to_stdout(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AGENTIC_GAUNTLET_STREAM_EVENTS", "1")
    writer = EventWriter(tmp_path / "events.jsonl")
    writer.write("run_started", run_id="r1", side="x86")

    streamed = json.loads(capsys.readouterr().out.strip())
    assert streamed["type"] == "run_started"
    assert streamed["run_id"] == "r1"
    assert streamed["side"] == "x86"


def test_event_writer_rejects_reserved_payload_keys(tmp_path):
    writer = EventWriter(tmp_path / "events.jsonl")
    with pytest.raises(ValueError):
        writer.write("x", type="bad")
    with pytest.raises(ValueError):
        writer.write("x", ts=1)
