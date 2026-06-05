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


def build_codex_command(
    workspace: Path,
    prompt: str,
    model: str | None = None,
    codex_binary: str = "codex",
) -> list[str]:
    command = [
        codex_binary,
        "--ask-for-approval",
        "never",
        "exec",
    ]
    if model:
        command.extend(["--model", model])
    command.extend(
        [
            "--json",
            "--cd",
            str(workspace),
            "--sandbox",
            "workspace-write",
            prompt,
        ]
    )
    return command
