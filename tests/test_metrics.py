from agentic_cpu_bench.command_runner import CommandResult
from agentic_cpu_bench.metrics import race_headline, summarize_commands, with_derived_metrics


def test_summarize_commands_groups_cpu_tool_time():
    commands = [
        CommandResult("python-tests", ("uv",), 0, "", "", 10.0),
        CommandResult("cpp-build", ("make",), 0, "", "", 20.0),
        CommandResult("cpp-tests", ("make",), 0, "", "", 30.0),
    ]
    summary = summarize_commands(commands, completion_ms=75.0)
    assert summary["completion_ms"] == 75.0
    assert summary["cpu_tool_step_ms"] == 60.0
    assert summary["command_count"] == 3


def test_with_derived_metrics_adds_dashboard_requirements():
    summaries = with_derived_metrics(
        [
            {
                "side": "grace",
                "label": "Grace",
                "completion_ms": 750.0,
                "cpu_tool_step_ms": 700.0,
                "agents_at_sla": 1,
            },
            {
                "side": "x86",
                "label": "x86",
                "completion_ms": 1200.0,
                "cpu_tool_step_ms": 1100.0,
                "agents_at_sla": 1,
            },
        ]
    )

    grace, x86 = summaries
    assert grace["gpu_wait_proxy_ms"] == 700.0
    assert x86["equal_vcpu_completion_ms"] == 1200.0
    assert x86["equal_physical_core_est_completion_ms"] == 600.0
    assert grace["composite_score"] > x86["composite_score"]
    assert set(grace["composite_components"]) == {
        "completion",
        "agents_at_sla",
        "cpu_tool_step",
        "gpu_wait_proxy",
    }


def test_race_headline_names_winner_and_speedup():
    headline = race_headline(
        [
            {"side": "grace", "label": "Grace", "completion_ms": 500.0},
            {"side": "x86", "label": "x86", "completion_ms": 1000.0},
        ]
    )

    assert headline == "Grace leads at 2.00x completion speed"
