from __future__ import annotations

import html
from pathlib import Path
from typing import Any


def write_dashboard(path: Path, summaries: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for summary in summaries:
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(summary['side']))}</td>"
            f"<td>{html.escape(str(summary['task_id']))}</td>"
            f"<td>{'PASS' if summary['ok'] else 'FAIL'}</td>"
            f"<td>{summary['completion_ms']:.2f}</td>"
            f"<td>{summary['cpu_tool_step_ms']:.2f}</td>"
            "</tr>"
        )
    content = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Agentic CPU Bench</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 32px; color: #111827; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid #d1d5db; padding: 10px; text-align: left; }}
    .hero {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 24px; }}
    .badge {{ background: #76b900; color: white; padding: 6px 10px; border-radius: 4px; }}
  </style>
</head>
<body>
  <div class="hero">
    <h1>Race First: Grace vs x86</h1>
    <span class="badge">Agentic CPU Bench</span>
  </div>
  <table>
    <thead><tr><th>Side</th><th>Task</th><th>Result</th><th>Completion ms</th><th>CPU tool-step ms</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</body>
</html>
"""
    path.write_text(content, encoding="utf-8")
    return path
