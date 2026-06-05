from pathlib import Path

from agentic_cpu_bench.codex_agent import build_codex_command, build_live_prompt
from agentic_cpu_bench.task_model import load_task


def test_build_codex_command_places_approval_before_exec():
    cmd = build_codex_command(Path("/tmp/work"), "fix it")
    assert cmd == [
        "codex",
        "--ask-for-approval",
        "never",
        "exec",
        "--json",
        "--cd",
        "/tmp/work",
        "--sandbox",
        "workspace-write",
        "fix it",
    ]


def test_build_codex_command_places_model_after_exec():
    cmd = build_codex_command(Path("/tmp/work"), "fix it", model="gpt-5")
    assert cmd == [
        "codex",
        "--ask-for-approval",
        "never",
        "exec",
        "--model",
        "gpt-5",
        "--json",
        "--cd",
        "/tmp/work",
        "--sandbox",
        "workspace-write",
        "fix it",
    ]


def test_build_codex_command_allows_sandbox_override():
    cmd = build_codex_command(Path("/tmp/work"), "fix it", sandbox="danger-full-access")
    assert "--sandbox" in cmd
    assert cmd[cmd.index("--sandbox") + 1] == "danger-full-access"


def test_build_codex_command_allows_codex_binary_override():
    cmd = build_codex_command(Path("/tmp/work"), "fix it", codex_binary="/tmp/fake-codex")
    assert cmd[0] == "/tmp/fake-codex"


def test_build_live_prompt_includes_success_commands():
    task = load_task(Path("tasks/python_cpp_bugfix/manifest.json"))
    prompt = build_live_prompt(task)
    assert "uv run pytest -q" in prompt
    assert "make build" in prompt
    assert "make test" in prompt
