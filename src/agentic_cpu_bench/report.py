from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


_MARKDOWN_META_CHARS = "[]()!*_#`>+-.|"


def _markdown_safe(value: object) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ")
    text = html.escape(text, quote=True).replace("\\", r"\\")
    for char in _MARKDOWN_META_CHARS:
        text = text.replace(char, f"\\{char}")
    return text


def write_report(path: Path, summaries: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Agentic CPU Bench Report", ""]
    for summary in summaries:
        side = _markdown_safe(summary["side"])
        task_id = _markdown_safe(summary["task_id"])
        agents_at_sla = _markdown_safe(summary.get("agents_at_sla", 1))
        lines.extend(
            [
                f"## {side} - {task_id}",
                "",
                f"- Result: {'PASS' if summary['ok'] else 'FAIL'}",
                f"- Completion time: {summary['completion_ms']:.2f} ms",
                f"- CPU tool-step time: {summary['cpu_tool_step_ms']:.2f} ms",
                f"- Agents at SLA: {agents_at_sla}",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")
    (path.parent / "results.json").write_text(json.dumps(summaries, indent=2, sort_keys=True), encoding="utf-8")
    return path
