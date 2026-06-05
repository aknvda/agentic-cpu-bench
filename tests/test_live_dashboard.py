import json

from agentic_cpu_bench.live_dashboard import (
    dashboard_html,
    initial_dashboard_state,
    parse_streamed_events,
    transcript_tail,
    side_state_from_events,
    write_state,
    read_state,
)


def test_parse_streamed_events_ignores_non_json_log_lines():
    log_text = "\n".join(
        [
            "apt-get noise",
            json.dumps({"type": "run_started", "side": "grace", "ts": 100.0}),
            "__AGENTIC_GAUNTLET_ARTIFACTS_BEGIN_grace__",
            "not-json",
            json.dumps({"type": "command_finished", "command": "pytest", "duration_ms": 12.5}),
        ]
    )

    events = parse_streamed_events(log_text)

    assert [event["type"] for event in events] == ["run_started", "command_finished"]


def test_transcript_tail_keeps_high_signal_lines_and_filters_noise():
    log_text = "\n".join(
        [
            "tar: Ignoring unknown extended header keyword 'LIBARCHIVE.xattr.com.apple.provenance'",
            "Installing build dependencies: started",
            "waiting_for_synchronized_start target=1.000 delay=0.500s",
            json.dumps({"type": "command_started", "command": "python-tests"}),
            json.dumps({"type": "command_finished", "command": "python-tests", "returncode": 0, "duration_ms": 12.5}),
            "ok=True completion_ms=15.00 events=tmp/events.jsonl",
        ]
    )

    transcript = transcript_tail(log_text)

    assert "Installing build dependencies: started" not in transcript
    assert any("waiting_for_synchronized_start" in line for line in transcript)
    assert "started · python-tests" in transcript
    assert "finished · python-tests · rc=0 · 12.50 ms" in transcript


def test_side_state_shows_running_current_step_before_finish():
    events = [
        {"type": "run_started", "side": "x86", "ts": 100.0},
        {"type": "command_started", "side": "x86", "command": "python-tests", "ts": 101.0},
    ]

    state = side_state_from_events(
        "x86",
        events=events,
        job_status="running",
        pod_phase="Running",
        pod_name="worker-x86",
        node_name="node-x86",
        now=103.0,
    )

    assert state["status"] == "running"
    assert state["result"] == "RUNNING"
    assert state["current_step"] == "python-tests"
    assert state["elapsed_ms"] == 3000.0
    assert state["pod_name"] == "worker-x86"
    assert state["node_name"] == "node-x86"


def test_side_state_shows_pass_and_cpu_time_after_finish():
    events = [
        {"type": "run_started", "side": "grace", "ts": 100.0},
        {"type": "command_started", "side": "grace", "command": "python-tests", "ts": 101.0},
        {"type": "command_finished", "side": "grace", "command": "python-tests", "duration_ms": 20.0},
        {"type": "run_finished", "side": "grace", "ok": True, "completion_ms": 25.0},
    ]

    state = side_state_from_events("grace", events=events)

    assert state["status"] == "pass"
    assert state["result"] == "PASS"
    assert state["completion_ms"] == 25.0
    assert state["cpu_tool_step_ms"] == 20.0
    assert state["command_count"] == 1
    assert state["current_step"] == "complete"


def test_lint_and_static_analysis_wait_before_finished_run():
    events = [
        {"type": "run_started", "side": "grace", "ts": 100.0},
        {"type": "command_started", "side": "grace", "command": "python-tests", "ts": 101.0},
    ]

    state = side_state_from_events("grace", events=events)

    statuses = {step["key"]: step["status"] for step in state["step_statuses"]}
    assert statuses["lint"] == "waiting"
    assert statuses["static_analysis"] == "waiting"


def test_dashboard_state_round_trip_and_html_polling(tmp_path):
    path = tmp_path / "state.json"
    state = initial_dashboard_state("agentic-cpu-bench-demo", "replay")
    write_state(path, state)

    assert read_state(path)["namespace"] == "agentic-cpu-bench-demo"
    html = dashboard_html()
    assert "Race First: Grace vs x86" in html
    assert 'fetch("/state.json"' in html
