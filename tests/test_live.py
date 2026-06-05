from pathlib import Path

from agentic_cpu_bench.live import run_codex_live
from agentic_cpu_bench.task_model import load_task


def test_run_codex_live_records_codex_and_success_artifacts(tmp_path):
    fake_codex = tmp_path / "fake-codex"
    fake_codex.write_text(
        """#!/usr/bin/env python3
from pathlib import Path
Path("src/cpu_bench_demo/text_stats.py").write_text('''from __future__ import annotations

import re


def extract_error_codes(log_text: str) -> list[str]:
    return re.findall(r"ERR-\\d+", log_text)


def summarize_counts(values: list[int]) -> dict[str, float]:
    if not values:
        return {"count": 0, "mean": 0.0}
    return {"count": len(values), "mean": float(sum(values) / len(values))}
''')
Path("cpp/calc.cpp").write_text('''#include <algorithm>
#include <iostream>
#include <string>

int main(int argc, char** argv) {
  if (argc < 4) {
    std::cerr << "usage: calc <add|scale|clamp> ...\\\\n";
    return 2;
  }
  const std::string op = argv[1];
  const int a = std::stoi(argv[2]);
  const int b = std::stoi(argv[3]);
  if (op == "add") {
    std::cout << a + b << "\\\\n";
  } else if (op == "scale") {
    std::cout << a * b << "\\\\n";
  } else if (op == "clamp") {
    if (argc != 5) {
      std::cerr << "usage: calc clamp <value> <low> <high>\\\\n";
      return 2;
    }
    const int high = std::stoi(argv[4]);
    std::cout << std::clamp(a, b, high) << "\\\\n";
  } else {
    std::cerr << "unknown op\\\\n";
    return 3;
  }
  return 0;
}
''')
print('{"type":"fake_codex_done"}')
""",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    task = load_task(Path("tasks/python_cpp_bugfix/manifest.json"))

    result = run_codex_live(
        task,
        tmp_path / "run",
        run_id="live-test",
        side="live",
        codex_binary=str(fake_codex),
        sandbox="danger-full-access",
        timeout_seconds=30,
    )

    assert result.ok is True
    assert result.events_path.exists()
    assert result.codex_stdout_path.read_text(encoding="utf-8").strip() == '{"type":"fake_codex_done"}'
    command_text = (tmp_path / "run" / "artifacts" / "codex.command.txt").read_text(encoding="utf-8")
    assert f"--cd {result.workspace.resolve()}" in command_text
    assert "--sandbox danger-full-access" in command_text
    assert "extract_error_codes" in result.patch_path.read_text(encoding="utf-8")
    assert [command.name for command in result.commands] == [
        "codex-agent",
        "python-tests",
        "cpp-build",
        "cpp-tests",
        "lint",
        "static-analysis",
    ]
