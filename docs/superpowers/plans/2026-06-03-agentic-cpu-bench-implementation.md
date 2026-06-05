# Agentic CPU Bench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable MVP of the Agentic CPU Bench: deterministic Python+C++ bug-fix tasks, replayable CPU tool-step measurement, Codex CLI live mode, Race First dashboard/reporting, and Kubernetes scheduling for Grace and x86 in `agentic-cpu-bench-demo`.

**Architecture:** The repo contains a Python CLI package named `agentic_cpu_bench`. A checked-in fixture repo supplies broken Python+C++ tasks; the harness creates per-run workspaces, validates tasks, executes allowed commands with timing, records JSONL events/traces, renders static dashboard/report artifacts, and generates Kubernetes manifests for Grace/x86 jobs. Codex live mode is an adapter over `codex exec --json`; replay mode is deterministic and does not call an LLM.

**Tech Stack:** Python 3.12 via `uv`, pytest, stdlib JSON/subprocess/dataclasses, Makefile + `c++`, Codex CLI, Kubernetes YAML, static HTML/CSS/JS.

---

## File Structure

```text
agentic-cpu-bench/
├── pyproject.toml
├── README.md
├── docs/superpowers/specs/2026-06-03-agentic-cpu-bench-design.md
├── docs/superpowers/plans/2026-06-03-agentic-cpu-bench-implementation.md
├── fixtures/bug_repo/
│   ├── Makefile
│   ├── pyproject.toml
│   ├── cpp/calc.cpp
│   ├── src/cpu_bench_demo/__init__.py
│   ├── src/cpu_bench_demo/text_stats.py
│   └── tests/test_text_stats.py
├── tasks/python_cpp_bugfix/
│   ├── manifest.json
│   ├── prompt.md
│   └── expected.patch
├── src/agentic_cpu_bench/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── codex_agent.py
│   ├── command_runner.py
│   ├── dashboard.py
│   ├── events.py
│   ├── k8s.py
│   ├── metrics.py
│   ├── paths.py
│   ├── report.py
│   ├── replay.py
│   ├── task_model.py
│   └── workspace.py
├── tests/
│   ├── test_codex_agent.py
│   ├── test_command_runner.py
│   ├── test_dashboard_report.py
│   ├── test_events.py
│   ├── test_k8s.py
│   ├── test_metrics.py
│   ├── test_replay.py
│   ├── test_task_model.py
│   └── test_workspace.py
└── scripts/
    ├── cluster_smoke.sh
    └── run_local_short.sh
```

Responsibilities:

- `fixtures/bug_repo/`: deterministic broken Python+C++ repo used by live and replay modes.
- `tasks/python_cpp_bugfix/`: task metadata, agent prompt, and expected patch.
- `task_model.py`: validates and loads task manifests.
- `workspace.py`: creates isolated run workspaces and applies/reset fixtures.
- `command_runner.py`: runs allowed commands with timing and captures stdout/stderr.
- `events.py`: JSONL event schema and writer.
- `replay.py`: deterministic trace/patch replay without LLM calls.
- `codex_agent.py`: Codex CLI live-mode adapter.
- `metrics.py`: aggregation and composite-score inputs.
- `dashboard.py`: static Race First HTML dashboard.
- `report.py`: Markdown/JSON follow-up report.
- `k8s.py`: namespace, node selectors, tolerations, and job manifest generation.
- `cli.py`: user entrypoints.

## Implementation Tasks

### Task 1: Python Package Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/agentic_cpu_bench/__init__.py`
- Create: `src/agentic_cpu_bench/__main__.py`
- Create: `src/agentic_cpu_bench/cli.py`
- Create: `tests/test_task_model.py`
- Modify: `README.md`

- [ ] **Step 1: Write the first failing CLI import test**

Create `tests/test_task_model.py`:

```python
from agentic_cpu_bench.cli import build_parser


def test_build_parser_has_expected_commands():
    parser = build_parser()
    commands = parser._subparsers._group_actions[0].choices
    assert set(commands) == {"validate-task", "replay", "codex-live", "dashboard", "report", "k8s-smoke"}
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest tests/test_task_model.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'agentic_cpu_bench'`.

- [ ] **Step 3: Create packaging and CLI skeleton**

Create `pyproject.toml`:

```toml
[project]
name = "agentic-cpu-bench"
version = "0.1.0"
description = "Race First agentic CPU bench for Grace/x86 demos with a future Vera target"
requires-python = ">=3.12"
dependencies = []

[project.scripts]
agentic-cpu-bench = "agentic_cpu_bench.cli:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]

[tool.ruff]
line-length = 120
target-version = "py312"
```

Create `src/agentic_cpu_bench/__init__.py`:

```python
__all__ = ["__version__"]

__version__ = "0.1.0"
```

Create `src/agentic_cpu_bench/__main__.py`:

```python
from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())
```

Create `src/agentic_cpu_bench/cli.py`:

```python
from __future__ import annotations

import argparse


COMMANDS = ("validate-task", "replay", "codex-live", "dashboard", "report", "k8s-smoke")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentic-cpu-bench")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in COMMANDS:
        subparsers.add_parser(command)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    return 0
```

Update `README.md` by adding:

```markdown
## Local Development

```bash
uv run pytest -q
uv run agentic-cpu-bench --help
```
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
uv run pytest tests/test_task_model.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml README.md src/agentic_cpu_bench tests/test_task_model.py
git commit -m "chore: scaffold agentic CPU bench package"
```

### Task 2: Task Manifest Model

**Files:**
- Create: `src/agentic_cpu_bench/task_model.py`
- Replace: `tests/test_task_model.py`
- Create: `tasks/python_cpp_bugfix/manifest.json`
- Create: `tasks/python_cpp_bugfix/prompt.md`

- [ ] **Step 1: Replace the test with manifest-loading coverage**

Replace `tests/test_task_model.py`:

```python
import json
from pathlib import Path

import pytest

from agentic_cpu_bench.task_model import CommandSpec, TaskSpec, load_task


def test_loads_python_cpp_bugfix_manifest():
    task = load_task(Path("tasks/python_cpp_bugfix/manifest.json"))
    assert task.task_id == "python_cpp_bugfix"
    assert task.fixture_repo == Path("fixtures/bug_repo")
    assert task.timeout_seconds == 180
    assert task.tags == ["python", "cpp", "pytest", "compile", "regex"]
    assert task.success_commands == [
        CommandSpec(name="python-tests", argv=["uv", "run", "pytest", "-q"]),
        CommandSpec(name="cpp-build", argv=["make", "build"]),
        CommandSpec(name="cpp-tests", argv=["make", "test"]),
    ]


def test_rejects_empty_success_commands(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "task_id": "bad",
                "fixture_repo": "fixtures/bug_repo",
                "prompt": "prompt.md",
                "expected_patch": "expected.patch",
                "timeout_seconds": 60,
                "tags": ["python"],
                "success_commands": [],
                "allowed_commands": ["uv"],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="success_commands"):
        load_task(manifest)
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest tests/test_task_model.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'agentic_cpu_bench.task_model'`.

- [ ] **Step 3: Create the implementation**

Create `src/agentic_cpu_bench/task_model.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommandSpec:
    name: str
    argv: list[str]


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    fixture_repo: Path
    prompt: Path
    expected_patch: Path
    timeout_seconds: int
    tags: list[str]
    success_commands: list[CommandSpec]
    allowed_commands: list[str]


def _command(value: dict[str, object]) -> CommandSpec:
    name = value.get("name")
    argv = value.get("argv")
    if not isinstance(name, str) or not name:
        raise ValueError("command name must be a non-empty string")
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item for item in argv):
        raise ValueError(f"command {name!r} argv must be a non-empty list of strings")
    return CommandSpec(name=name, argv=argv)


def load_task(path: Path) -> TaskSpec:
    raw = json.loads(path.read_text(encoding="utf-8"))
    success_commands = [_command(item) for item in raw.get("success_commands", [])]
    allowed_commands = raw.get("allowed_commands", [])
    tags = raw.get("tags", [])
    if not success_commands:
        raise ValueError("manifest must define at least one success_commands entry")
    if not isinstance(allowed_commands, list) or not all(isinstance(item, str) and item for item in allowed_commands):
        raise ValueError("allowed_commands must be a list of non-empty strings")
    if not isinstance(tags, list) or not all(isinstance(item, str) and item for item in tags):
        raise ValueError("tags must be a list of strings")
    return TaskSpec(
        task_id=str(raw["task_id"]),
        fixture_repo=Path(str(raw["fixture_repo"])),
        prompt=path.parent / str(raw["prompt"]),
        expected_patch=path.parent / str(raw["expected_patch"]),
        timeout_seconds=int(raw["timeout_seconds"]),
        tags=tags,
        success_commands=success_commands,
        allowed_commands=allowed_commands,
    )
```

Create `tasks/python_cpp_bugfix/manifest.json`:

```json
{
  "task_id": "python_cpp_bugfix",
  "fixture_repo": "fixtures/bug_repo",
  "prompt": "prompt.md",
  "expected_patch": "expected.patch",
  "timeout_seconds": 180,
  "tags": ["python", "cpp", "pytest", "compile", "regex"],
  "success_commands": [
    {"name": "python-tests", "argv": ["uv", "run", "pytest", "-q"]},
    {"name": "cpp-build", "argv": ["make", "build"]},
    {"name": "cpp-tests", "argv": ["make", "test"]}
  ],
  "allowed_commands": ["uv", "pytest", "python", "make", "c++", "sed", "rg", "cat", "ls"]
}
```

Create `tasks/python_cpp_bugfix/prompt.md`:

```markdown
You are fixing a small Python+C++ repository.

Goal:
- Make `uv run pytest -q` pass.
- Make `make build` pass.
- Make `make test` pass.

Constraints:
- Keep the fix minimal.
- Do not delete tests.
- Use only ordinary repo commands such as reading files, editing files, running pytest, and running make.
- Stop once all three success commands pass.
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
uv run pytest tests/test_task_model.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/agentic_cpu_bench/task_model.py tests/test_task_model.py tasks/python_cpp_bugfix
git commit -m "feat: add task manifest model"
```

### Task 3: Python+C++ Broken Fixture Repo

**Files:**
- Create: `fixtures/bug_repo/Makefile`
- Create: `fixtures/bug_repo/pyproject.toml`
- Create: `fixtures/bug_repo/cpp/calc.cpp`
- Create: `fixtures/bug_repo/src/cpu_bench_demo/__init__.py`
- Create: `fixtures/bug_repo/src/cpu_bench_demo/text_stats.py`
- Create: `fixtures/bug_repo/tests/test_text_stats.py`
- Create: `tasks/python_cpp_bugfix/expected.patch`
- Create: `tests/test_workspace.py`
- Create: `src/agentic_cpu_bench/workspace.py`

- [ ] **Step 1: Write workspace validation tests**

Create `tests/test_workspace.py`:

```python
import subprocess
from pathlib import Path

from agentic_cpu_bench.task_model import load_task
from agentic_cpu_bench.workspace import create_workspace, run_success_commands


def test_fixture_starts_broken_then_expected_patch_passes(tmp_path):
    task = load_task(Path("tasks/python_cpp_bugfix/manifest.json"))
    workspace = create_workspace(task, tmp_path / "run")

    broken = run_success_commands(task, workspace)
    assert broken.ok is False
    assert "python-tests" in broken.failed_command_names or "cpp-tests" in broken.failed_command_names

    subprocess.run(["git", "apply", str(task.expected_patch.resolve())], cwd=workspace, check=True)
    fixed = run_success_commands(task, workspace)
    assert fixed.ok is True
    assert fixed.failed_command_names == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest tests/test_workspace.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'agentic_cpu_bench.workspace'`.

- [ ] **Step 3: Create the broken fixture repo**

Create `fixtures/bug_repo/pyproject.toml`:

```toml
[project]
name = "cpu-bench-demo"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = []

[tool.pytest.ini_options]
pythonpath = ["src"]
```

Create `fixtures/bug_repo/Makefile`:

```makefile
CXX ?= c++
CXXFLAGS ?= -O2 -std=c++17 -Wall -Wextra -Werror

.PHONY: build test clean

build:
	mkdir -p build
	$(CXX) $(CXXFLAGS) cpp/calc.cpp -o build/calc

test: build
	./build/calc add 2 3 | grep '^5$$'
	./build/calc scale 7 6 | grep '^42$$'
	./build/calc clamp 13 0 10 | grep '^10$$'

clean:
	rm -rf build
```

Create `fixtures/bug_repo/cpp/calc.cpp`:

```cpp
#include <iostream>
#include <string>

int main(int argc, char** argv) {
    if (argc < 4) {
        std::cerr << "usage: calc <add|scale|clamp> ...\n";
        return 2;
    }

    std::string op = argv[1];
    int a = std::stoi(argv[2]);
    int b = std::stoi(argv[3]);

    if (op == "add") {
        std::cout << (a + b) << "\n";
        return 0;
    }
    if (op == "scale") {
        std::cout << (a + b) << "\n";
        return 0;
    }
    if (op == "clamp") {
        if (argc != 5) {
            std::cerr << "usage: calc clamp <value> <low> <high>\n";
            return 2;
        }
        int high = std::stoi(argv[4]);
        if (a < b) {
            std::cout << b << "\n";
        } else if (a > high) {
            std::cout << high << "\n";
        } else {
            std::cout << a << "\n";
        }
        return 0;
    }

    std::cerr << "unknown op\n";
    return 2;
}
```

Create `fixtures/bug_repo/src/cpu_bench_demo/__init__.py`:

```python
from .text_stats import extract_error_codes, summarize_counts

__all__ = ["extract_error_codes", "summarize_counts"]
```

Create `fixtures/bug_repo/src/cpu_bench_demo/text_stats.py`:

```python
from __future__ import annotations

import re


def extract_error_codes(log_text: str) -> list[str]:
    return re.findall(r"ERR-(\\d+)", log_text)


def summarize_counts(values: list[int]) -> dict[str, float]:
    if not values:
        return {"count": 0, "mean": 0.0}
    return {"count": len(values), "mean": float(sum(values) // len(values))}
```

Create `fixtures/bug_repo/tests/test_text_stats.py`:

```python
from cpu_bench_demo import extract_error_codes, summarize_counts


def test_extract_error_codes_keeps_prefix():
    assert extract_error_codes("ok ERR-104 retry ERR-205 done") == ["ERR-104", "ERR-205"]


def test_summarize_counts_uses_float_mean():
    assert summarize_counts([1, 2]) == {"count": 2, "mean": 1.5}
```

Create `tasks/python_cpp_bugfix/expected.patch`:

```diff
diff --git a/cpp/calc.cpp b/cpp/calc.cpp
index 3be7a29..35e97da 100644
--- a/cpp/calc.cpp
+++ b/cpp/calc.cpp
@@ -18,7 +18,7 @@ int main(int argc, char** argv) {
         return 0;
     }
     if (op == "scale") {
-        std::cout << (a + b) << "\n";
+        std::cout << (a * b) << "\n";
         return 0;
     }
     if (op == "clamp") {
diff --git a/src/cpu_bench_demo/text_stats.py b/src/cpu_bench_demo/text_stats.py
index b79d31c..2890ed1 100644
--- a/src/cpu_bench_demo/text_stats.py
+++ b/src/cpu_bench_demo/text_stats.py
@@ -5,11 +5,11 @@ import re
 
 
 def extract_error_codes(log_text: str) -> list[str]:
-    return re.findall(r"ERR-(\\d+)", log_text)
+    return re.findall(r"ERR-\\d+", log_text)
 
 
 def summarize_counts(values: list[int]) -> dict[str, float]:
     if not values:
         return {"count": 0, "mean": 0.0}
-    return {"count": len(values), "mean": float(sum(values) // len(values))}
+    return {"count": len(values), "mean": float(sum(values) / len(values))}
```

- [ ] **Step 4: Create workspace helpers**

Create `src/agentic_cpu_bench/workspace.py`:

```python
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .task_model import TaskSpec


@dataclass(frozen=True)
class SuccessResult:
    ok: bool
    failed_command_names: list[str]


def create_workspace(task: TaskSpec, destination: Path) -> Path:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(task.fixture_repo, destination)
    subprocess.run(["git", "init", "-q"], cwd=destination, check=True)
    subprocess.run(["git", "add", "."], cwd=destination, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Agentic CPU Bench",
            "-c",
            "user.email=agentic-cpu-bench@example.invalid",
            "commit",
            "-q",
            "-m",
            "initial broken fixture",
        ],
        cwd=destination,
        check=True,
    )
    return destination


def run_success_commands(task: TaskSpec, workspace: Path) -> SuccessResult:
    failed: list[str] = []
    for command in task.success_commands:
        result = subprocess.run(command.argv, cwd=workspace, text=True, capture_output=True)
        if result.returncode != 0:
            failed.append(command.name)
    return SuccessResult(ok=not failed, failed_command_names=failed)
```

- [ ] **Step 5: Run the test to verify it passes**

Run:

```bash
uv run pytest tests/test_workspace.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add fixtures/bug_repo tasks/python_cpp_bugfix/expected.patch src/agentic_cpu_bench/workspace.py tests/test_workspace.py
git commit -m "feat: add python cpp bugfix fixture"
```

### Task 4: Event Schema and Timed Command Runner

**Files:**
- Create: `src/agentic_cpu_bench/events.py`
- Create: `src/agentic_cpu_bench/command_runner.py`
- Create: `tests/test_events.py`
- Create: `tests/test_command_runner.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_events.py`:

```python
import json

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
```

Create `tests/test_command_runner.py`:

```python
from agentic_cpu_bench.command_runner import CommandRunner


def test_command_runner_allows_listed_command(tmp_path):
    runner = CommandRunner(allowed_commands=["python"])
    result = runner.run(["python", "-c", "print('ok')"], cwd=tmp_path, name="hello")
    assert result.name == "hello"
    assert result.returncode == 0
    assert result.stdout.strip() == "ok"
    assert result.duration_ms >= 0


def test_command_runner_blocks_unlisted_command(tmp_path):
    runner = CommandRunner(allowed_commands=["python"])
    result = runner.run(["bash", "-lc", "echo bad"], cwd=tmp_path, name="blocked")
    assert result.returncode == 126
    assert "not allowed" in result.stderr
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_events.py tests/test_command_runner.py -q
```

Expected: FAIL because both modules are missing.

- [ ] **Step 3: Implement events and command runner**

Create `src/agentic_cpu_bench/events.py`:

```python
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class EventWriter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event_type: str, **payload: Any) -> None:
        event = {"type": event_type, "ts": time.time(), **payload}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
```

Create `src/agentic_cpu_bench/command_runner.py`:

```python
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommandResult:
    name: str
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str
    duration_ms: float


class CommandRunner:
    def __init__(self, allowed_commands: list[str], timeout_seconds: int = 180) -> None:
        self.allowed_commands = set(allowed_commands)
        self.timeout_seconds = timeout_seconds

    def run(self, argv: list[str], cwd: Path, name: str) -> CommandResult:
        start = time.perf_counter()
        if not argv or argv[0] not in self.allowed_commands:
            return CommandResult(
                name=name,
                argv=argv,
                returncode=126,
                stdout="",
                stderr=f"command not allowed: {argv[0] if argv else '<empty>'}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        try:
            completed = subprocess.run(
                argv,
                cwd=cwd,
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
            )
            return CommandResult(
                name=name,
                argv=argv,
                returncode=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                name=name,
                argv=argv,
                returncode=124,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "command timed out",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
uv run pytest tests/test_events.py tests/test_command_runner.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/agentic_cpu_bench/events.py src/agentic_cpu_bench/command_runner.py tests/test_events.py tests/test_command_runner.py
git commit -m "feat: add event and command runner primitives"
```

### Task 5: Deterministic Replay Runner

**Files:**
- Create: `src/agentic_cpu_bench/replay.py`
- Create: `tests/test_replay.py`
- Modify: `src/agentic_cpu_bench/cli.py`

- [ ] **Step 1: Write failing replay test**

Create `tests/test_replay.py`:

```python
from pathlib import Path

from agentic_cpu_bench.replay import replay_expected_patch
from agentic_cpu_bench.task_model import load_task


def test_replay_expected_patch_records_events_and_passes(tmp_path):
    task = load_task(Path("tasks/python_cpp_bugfix/manifest.json"))
    result = replay_expected_patch(task, tmp_path / "run", run_id="r1", side="grace")
    assert result.ok is True
    assert result.completion_ms > 0
    assert [item.name for item in result.commands] == ["apply-patch", "python-tests", "cpp-build", "cpp-tests"]
    events = (tmp_path / "run" / "artifacts" / "events.jsonl").read_text(encoding="utf-8")
    assert "run_started" in events
    assert "command_finished" in events
    assert "run_finished" in events
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest tests/test_replay.py -q
```

Expected: FAIL because `agentic_cpu_bench.replay` is missing.

- [ ] **Step 3: Implement replay**

Create `src/agentic_cpu_bench/replay.py`:

```python
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .command_runner import CommandResult, CommandRunner
from .events import EventWriter
from .task_model import TaskSpec
from .workspace import create_workspace


@dataclass(frozen=True)
class ReplayResult:
    ok: bool
    completion_ms: float
    commands: list[CommandResult]
    workspace: Path
    events_path: Path


def replay_expected_patch(task: TaskSpec, run_dir: Path, run_id: str, side: str) -> ReplayResult:
    workspace = create_workspace(task, run_dir / "workspace")
    artifacts = run_dir / "artifacts"
    events = EventWriter(artifacts / "events.jsonl")
    events.write("run_started", run_id=run_id, side=side, task_id=task.task_id, mode="replay")
    start = time.perf_counter()
    commands: list[CommandResult] = []

    patch_start = time.perf_counter()
    patch = subprocess.run(["git", "apply", str(task.expected_patch.resolve())], cwd=workspace, text=True, capture_output=True)
    patch_result = CommandResult(
        name="apply-patch",
        argv=["git", "apply", str(task.expected_patch.resolve())],
        returncode=patch.returncode,
        stdout=patch.stdout,
        stderr=patch.stderr,
        duration_ms=(time.perf_counter() - patch_start) * 1000,
    )
    commands.append(patch_result)
    events.write(
        "command_finished",
        run_id=run_id,
        side=side,
        command=patch_result.name,
        returncode=patch_result.returncode,
        duration_ms=patch_result.duration_ms,
    )

    runner = CommandRunner(task.allowed_commands, timeout_seconds=task.timeout_seconds)
    if patch_result.returncode == 0:
        for command in task.success_commands:
            result = runner.run(command.argv, cwd=workspace, name=command.name)
            commands.append(result)
            events.write(
                "command_finished",
                run_id=run_id,
                side=side,
                command=result.name,
                returncode=result.returncode,
                duration_ms=result.duration_ms,
            )

    ok = all(item.returncode == 0 for item in commands)
    completion_ms = (time.perf_counter() - start) * 1000
    events.write("run_finished", run_id=run_id, side=side, ok=ok, completion_ms=completion_ms)
    return ReplayResult(ok=ok, completion_ms=completion_ms, commands=commands, workspace=workspace, events_path=artifacts / "events.jsonl")
```

- [ ] **Step 4: Wire the replay CLI**

Replace `src/agentic_cpu_bench/cli.py` with:

```python
from __future__ import annotations

import argparse
from pathlib import Path

from .replay import replay_expected_patch
from .task_model import load_task


COMMANDS = ("validate-task", "replay", "codex-live", "dashboard", "report", "k8s-smoke")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentic-cpu-bench")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("validate-task")

    replay = subparsers.add_parser("replay")
    replay.add_argument("--task", default="tasks/python_cpp_bugfix/manifest.json")
    replay.add_argument("--run-dir", required=True)
    replay.add_argument("--run-id", default="local-replay")
    replay.add_argument("--side", default="local")

    subparsers.add_parser("codex-live")
    subparsers.add_parser("dashboard")
    subparsers.add_parser("report")
    subparsers.add_parser("k8s-smoke")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "replay":
        task = load_task(Path(args.task))
        result = replay_expected_patch(task, Path(args.run_dir), run_id=args.run_id, side=args.side)
        print(f"ok={result.ok} completion_ms={result.completion_ms:.2f} events={result.events_path}")
        return 0 if result.ok else 1
    return 0
```

- [ ] **Step 5: Run tests and CLI smoke**

Run:

```bash
uv run pytest tests/test_replay.py tests/test_task_model.py -q
uv run agentic-cpu-bench replay --run-dir tmp/replay-smoke --run-id smoke --side local
```

Expected: tests PASS and CLI prints `ok=True`.

- [ ] **Step 6: Commit**

```bash
git add src/agentic_cpu_bench/replay.py src/agentic_cpu_bench/cli.py tests/test_replay.py
git commit -m "feat: add deterministic replay mode"
```

### Task 6: Metrics, Report, and Dashboard Artifacts

**Files:**
- Create: `src/agentic_cpu_bench/metrics.py`
- Create: `src/agentic_cpu_bench/report.py`
- Create: `src/agentic_cpu_bench/dashboard.py`
- Create: `tests/test_metrics.py`
- Create: `tests/test_dashboard_report.py`
- Modify: `src/agentic_cpu_bench/cli.py`

- [ ] **Step 1: Write failing metrics/report/dashboard tests**

Create `tests/test_metrics.py`:

```python
from agentic_cpu_bench.command_runner import CommandResult
from agentic_cpu_bench.metrics import summarize_commands


def test_summarize_commands_groups_cpu_tool_time():
    commands = [
        CommandResult("python-tests", ["uv"], 0, "", "", 10.0),
        CommandResult("cpp-build", ["make"], 0, "", "", 20.0),
        CommandResult("cpp-tests", ["make"], 0, "", "", 30.0),
    ]
    summary = summarize_commands(commands, completion_ms=75.0)
    assert summary["completion_ms"] == 75.0
    assert summary["cpu_tool_step_ms"] == 60.0
    assert summary["command_count"] == 3
```

Create `tests/test_dashboard_report.py`:

```python
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
    assert "python_cpp_bugfix" in report.read_text(encoding="utf-8")
    assert "Race First" in dashboard.read_text(encoding="utf-8")
    data = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert data[0]["side"] == "grace"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_metrics.py tests/test_dashboard_report.py -q
```

Expected: FAIL because modules are missing.

- [ ] **Step 3: Implement metrics**

Create `src/agentic_cpu_bench/metrics.py`:

```python
from __future__ import annotations

from .command_runner import CommandResult


def summarize_commands(commands: list[CommandResult], completion_ms: float) -> dict[str, float | int]:
    return {
        "completion_ms": completion_ms,
        "cpu_tool_step_ms": sum(command.duration_ms for command in commands),
        "command_count": len(commands),
    }
```

Create `src/agentic_cpu_bench/report.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_report(path: Path, summaries: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Agentic CPU Bench Report", ""]
    for summary in summaries:
        lines.extend(
            [
                f"## {summary['side']} - {summary['task_id']}",
                "",
                f"- Result: {'PASS' if summary['ok'] else 'FAIL'}",
                f"- Completion time: {summary['completion_ms']:.2f} ms",
                f"- CPU tool-step time: {summary['cpu_tool_step_ms']:.2f} ms",
                f"- Agents at SLA: {summary.get('agents_at_sla', 1)}",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")
    (path.parent / "results.json").write_text(json.dumps(summaries, indent=2, sort_keys=True), encoding="utf-8")
    return path
```

Create `src/agentic_cpu_bench/dashboard.py`:

```python
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
```

- [ ] **Step 4: Run tests**

Run:

```bash
uv run pytest tests/test_metrics.py tests/test_dashboard_report.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/agentic_cpu_bench/metrics.py src/agentic_cpu_bench/report.py src/agentic_cpu_bench/dashboard.py tests/test_metrics.py tests/test_dashboard_report.py
git commit -m "feat: add report and dashboard artifacts"
```

### Task 7: Codex CLI Live-Mode Adapter

**Files:**
- Create: `src/agentic_cpu_bench/codex_agent.py`
- Create: `tests/test_codex_agent.py`
- Modify: `src/agentic_cpu_bench/cli.py`

- [ ] **Step 1: Write failing Codex adapter tests**

Create `tests/test_codex_agent.py`:

```python
from pathlib import Path

from agentic_cpu_bench.codex_agent import build_codex_command, build_live_prompt
from agentic_cpu_bench.task_model import load_task


def test_build_codex_command_uses_workspace_write_and_json():
    cmd = build_codex_command(Path("/tmp/work"), "fix it", model="gpt-5")
    assert cmd[:2] == ["codex", "exec"]
    assert "--json" in cmd
    assert "--cd" in cmd
    assert "/tmp/work" in cmd
    assert "--sandbox" in cmd
    assert "workspace-write" in cmd
    assert "--ask-for-approval" in cmd
    assert "never" in cmd


def test_build_live_prompt_includes_success_commands():
    task = load_task(Path("tasks/python_cpp_bugfix/manifest.json"))
    prompt = build_live_prompt(task)
    assert "uv run pytest -q" in prompt
    assert "make build" in prompt
    assert "make test" in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_codex_agent.py -q
```

Expected: FAIL because `agentic_cpu_bench.codex_agent` is missing.

- [ ] **Step 3: Implement Codex adapter command construction**

Create `src/agentic_cpu_bench/codex_agent.py`:

```python
from __future__ import annotations

from pathlib import Path

from .task_model import TaskSpec


def build_live_prompt(task: TaskSpec) -> str:
    prompt = task.prompt.read_text(encoding="utf-8")
    commands = "\n".join("- " + " ".join(command.argv) for command in task.success_commands)
    allowed = ", ".join(task.allowed_commands)
    return (
        f"{prompt}\n\n"
        "Success commands:\n"
        f"{commands}\n\n"
        "Allowed command roots:\n"
        f"{allowed}\n\n"
        "When all success commands pass, stop and summarize the changed files."
    )


def build_codex_command(workspace: Path, prompt: str, model: str | None = None) -> list[str]:
    command = [
        "codex",
        "exec",
        "--json",
        "--cd",
        str(workspace),
        "--sandbox",
        "workspace-write",
        "--ask-for-approval",
        "never",
        prompt,
    ]
    if model:
        command[2:2] = ["--model", model]
    return command
```

- [ ] **Step 4: Run tests**

Run:

```bash
uv run pytest tests/test_codex_agent.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/agentic_cpu_bench/codex_agent.py tests/test_codex_agent.py
git commit -m "feat: add codex live mode adapter"
```

### Task 8: Kubernetes Manifest Generation and Cluster Smoke Script

**Files:**
- Create: `src/agentic_cpu_bench/k8s.py`
- Create: `tests/test_k8s.py`
- Create: `scripts/cluster_smoke.sh`
- Modify: `src/agentic_cpu_bench/cli.py`

- [ ] **Step 1: Write failing Kubernetes manifest tests**

Create `tests/test_k8s.py`:

```python
from agentic_cpu_bench.k8s import grace_pod_spec, x86_pod_spec


def test_grace_pod_spec_targets_validated_pool_and_toleration():
    spec = grace_pod_spec("smoke-grace", image="registry.k8s.io/pause:3.10")
    assert "namespace: agentic-cpu-bench-demo" in spec
    assert "kubernetes.io/arch: arm64" in spec
    assert "node.kubernetes.io/instance-type: a4x-highgpu-4g" in spec
    assert "cloud.google.com/gke-nodepool: customer-gpu-w0e" in spec
    assert "value: arm64" in spec


def test_x86_pod_spec_targets_customer_cpu_without_toleration():
    spec = x86_pod_spec("smoke-x86", image="registry.k8s.io/pause:3.10")
    assert "namespace: agentic-cpu-bench-demo" in spec
    assert "kubernetes.io/arch: amd64" in spec
    assert "node.kubernetes.io/instance-type: n2d-standard-8" in spec
    assert "cloud.google.com/gke-nodepool: customer-cpu" in spec
    assert "tolerations:" not in spec
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_k8s.py -q
```

Expected: FAIL because `agentic_cpu_bench.k8s` is missing.

- [ ] **Step 3: Implement manifest generation**

Create `src/agentic_cpu_bench/k8s.py`:

```python
from __future__ import annotations


NAMESPACE = "agentic-cpu-bench-demo"


def x86_pod_spec(name: str, image: str) -> str:
    return f"""apiVersion: v1
kind: Pod
metadata:
  name: {name}
  namespace: {NAMESPACE}
  labels:
    app: agentic-cpu-bench-smoke
spec:
  restartPolicy: Never
  nodeSelector:
    kubernetes.io/arch: amd64
    node.kubernetes.io/instance-type: n2d-standard-8
    cloud.google.com/gke-nodepool: customer-cpu
  containers:
    - name: runner
      image: {image}
      resources:
        requests:
          cpu: "100m"
          memory: "64Mi"
        limits:
          cpu: "100m"
          memory: "64Mi"
"""


def grace_pod_spec(name: str, image: str) -> str:
    return f"""apiVersion: v1
kind: Pod
metadata:
  name: {name}
  namespace: {NAMESPACE}
  labels:
    app: agentic-cpu-bench-smoke
spec:
  restartPolicy: Never
  nodeSelector:
    kubernetes.io/arch: arm64
    node.kubernetes.io/instance-type: a4x-highgpu-4g
    cloud.google.com/gke-nodepool: customer-gpu-w0e
  tolerations:
    - key: kubernetes.io/arch
      operator: Equal
      value: arm64
      effect: NoSchedule
  containers:
    - name: runner
      image: {image}
      resources:
        requests:
          cpu: "100m"
          memory: "64Mi"
        limits:
          cpu: "100m"
          memory: "64Mi"
"""
```

Create `scripts/cluster_smoke.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

NS="agentic-cpu-bench-demo"
IMAGE="registry.k8s.io/pause:3.10"

kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f -

uv run python - <<'PY' | kubectl apply -f -
from agentic_cpu_bench.k8s import grace_pod_spec, x86_pod_spec
print(x86_pod_spec("agentic-cpu-bench-smoke-x86", "registry.k8s.io/pause:3.10"))
print("---")
print(grace_pod_spec("agentic-cpu-bench-smoke-grace", "registry.k8s.io/pause:3.10"))
PY

kubectl wait -n "$NS" --for=condition=Ready pod/agentic-cpu-bench-smoke-x86 --timeout=60s
kubectl wait -n "$NS" --for=condition=Ready pod/agentic-cpu-bench-smoke-grace --timeout=60s
kubectl get pods -n "$NS" -l app=agentic-cpu-bench-smoke -o wide
kubectl delete pods -n "$NS" -l app=agentic-cpu-bench-smoke --wait=false
```

Run:

```bash
chmod +x scripts/cluster_smoke.sh
```

- [ ] **Step 4: Run tests and optional cluster smoke**

Run:

```bash
uv run pytest tests/test_k8s.py -q
./scripts/cluster_smoke.sh
```

Expected: pytest PASS. Cluster smoke creates two pods in `agentic-cpu-bench-demo`, both reach Ready, and both are deleted.

- [ ] **Step 5: Commit**

```bash
git add src/agentic_cpu_bench/k8s.py tests/test_k8s.py scripts/cluster_smoke.sh
git commit -m "feat: add k8s scheduling smoke"
```

### Task 9: Local Short-Run Script and Final Verification

**Files:**
- Create: `scripts/run_local_short.sh`
- Modify: `README.md`

- [ ] **Step 1: Create local short-run script**

Create `scripts/run_local_short.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

RUN_ROOT="${1:-tmp/local-short}"
rm -rf "$RUN_ROOT"
mkdir -p "$RUN_ROOT"

uv run agentic-cpu-bench replay --run-dir "$RUN_ROOT/grace" --run-id local-grace --side grace
uv run agentic-cpu-bench replay --run-dir "$RUN_ROOT/x86" --run-id local-x86 --side x86
```

Run:

```bash
chmod +x scripts/run_local_short.sh
```

- [ ] **Step 2: Update README with run commands**

Append to `README.md`:

```markdown
## MVP Commands

Validate locally:

```bash
uv run pytest -q
./scripts/run_local_short.sh
```

Check Grace/x86 scheduling in the dedicated namespace:

```bash
./scripts/cluster_smoke.sh
```
```

- [ ] **Step 3: Run full local verification**

Run:

```bash
uv run pytest -q
./scripts/run_local_short.sh
git status --short
```

Expected:

- pytest PASS;
- both local replay runs print `ok=True`;
- `git status --short` shows only intended README/script changes before commit.

- [ ] **Step 4: Commit**

```bash
git add README.md scripts/run_local_short.sh
git commit -m "docs: add local mvp runbook"
```

### Task 10: End-to-End Cluster Readiness Check

**Files:**
- No new files.

- [ ] **Step 1: Confirm namespace and node pools**

Run:

```bash
kubectl config current-context
kubectl get ns agentic-cpu-bench-demo -o name
kubectl get nodes -L kubernetes.io/arch,node.kubernetes.io/instance-type,cloud.google.com/gke-nodepool
```

Expected:

- current context is `your-k8s-context`;
- namespace exists;
- output includes `arm64/a4x-highgpu-4g/customer-gpu-w0e`;
- output includes `amd64/n2d-standard-8/customer-cpu`.

- [ ] **Step 2: Run cluster smoke**

Run:

```bash
./scripts/cluster_smoke.sh
```

Expected: x86 and Grace smoke pods reach Ready and are deleted.

- [ ] **Step 3: Run final status**

Run:

```bash
git status --short
git log --oneline -5
```

Expected:

- clean git status;
- recent commits show the completed MVP implementation tasks.

## Self-Review

Spec coverage:

- Task suite and validation are covered by Tasks 2 and 3.
- Replay mode and CPU tool-step timing are covered by Tasks 4, 5, and 6.
- Codex CLI live-mode adapter is covered by Task 7.
- Dashboard and report artifacts are covered by Task 6.
- Dedicated namespace, Grace/x86 node selectors, and scheduler smoke are covered by Task 8 and Task 10.
- Local MVP run commands are covered by Task 9.

Known implementation boundary:

- The first MVP records replay metrics and provides the Codex command adapter. A later extension can add a richer live dashboard stream from Codex JSONL events once the core harness is stable.
