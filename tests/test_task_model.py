import json
from pathlib import Path

import pytest

from agentic_cpu_bench.task_model import CommandSpec, load_task


def test_loads_python_cpp_bugfix_manifest():
    task = load_task(Path("tasks/python_cpp_bugfix/manifest.json"))
    assert task.task_id == "python_cpp_bugfix"
    assert task.fixture_repo == Path("fixtures/bug_repo")
    assert task.prompt == Path("tasks/python_cpp_bugfix/prompt.md")
    assert task.expected_patch == Path("tasks/python_cpp_bugfix/expected.patch")
    assert task.timeout_seconds == 180
    assert task.tags == ["python", "cpp", "pytest", "compile", "regex"]
    assert task.success_commands == [
        CommandSpec(name="python-tests", argv=["uv", "run", "pytest", "-q"]),
        CommandSpec(name="cpp-build", argv=["make", "build"]),
        CommandSpec(name="cpp-tests", argv=["make", "test"]),
        CommandSpec(name="lint", argv=["python", "-m", "compileall", "-q", "src", "tests"]),
        CommandSpec(
            name="static-analysis",
            argv=["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-fsyntax-only", "cpp/calc.cpp"],
        ),
    ]
    assert task.allowed_commands == ["uv", "pytest", "python", "make", "c++", "sed", "rg", "cat", "ls"]


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
