import json

from agentic_cpu_bench.dashboard import write_dashboard
from agentic_cpu_bench.report import write_report


def test_report_and_dashboard_are_written(tmp_path):
    summary = {
        "run_id": "r1",
        "task_id": "python_cpp_bugfix",
        "side": "grace",
        "ok": True,
        "completion_ms": 75.0,
        "cpu_tool_step_ms": 60.0,
        "agents_at_sla": 1,
    }
    report = write_report(tmp_path / "report.md", [summary])
    dashboard = write_dashboard(tmp_path / "dashboard.html", [summary])
    assert r"python\_cpp\_bugfix" in report.read_text(encoding="utf-8")
    assert "Race First" in dashboard.read_text(encoding="utf-8")
    data = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert data[0]["side"] == "grace"


def test_report_and_dashboard_escape_display_fields(tmp_path):
    summary = {
        "run_id": "r1",
        "task_id": 'python_cpp_bugfix "quoted"',
        "side": "grace<script>\n## injected",
        "ok": True,
        "completion_ms": 75.0,
        "cpu_tool_step_ms": 60.0,
        "agents_at_sla": 1,
    }
    report = write_report(tmp_path / "report.md", [summary])
    dashboard = write_dashboard(tmp_path / "dashboard.html", [summary])

    report_text = report.read_text(encoding="utf-8")
    assert "<script>" not in report_text
    assert "## injected" not in report_text
    assert "grace&lt;script&gt; \\#\\# injected" in report_text
    assert "&quot;quoted&quot;" in report_text

    dashboard_text = dashboard.read_text(encoding="utf-8")
    assert "<script>" not in dashboard_text
    assert "grace&lt;script&gt;" in dashboard_text


def test_report_escapes_markdown_link_and_image_syntax(tmp_path):
    summary = {
        "run_id": "r1",
        "task_id": "[task](https://example.invalid)",
        "side": "grace ![x](https://example.invalid/pixel)",
        "ok": True,
        "completion_ms": 75.0,
        "cpu_tool_step_ms": 60.0,
        "agents_at_sla": 1,
    }
    report = write_report(tmp_path / "report.md", [summary])
    dashboard = write_dashboard(tmp_path / "dashboard.html", [summary])

    report_text = report.read_text(encoding="utf-8")
    assert "![x](" not in report_text
    assert "[task](" not in report_text
    assert r"grace \!\[x\]\(https://example\.invalid/pixel\)" in report_text
    assert r"\[task\]\(https://example\.invalid\)" in report_text

    dashboard_text = dashboard.read_text(encoding="utf-8")
    assert "grace ![x](https://example.invalid/pixel)" in dashboard_text
    assert "[task](https://example.invalid)" in dashboard_text
