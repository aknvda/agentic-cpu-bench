from __future__ import annotations

import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .codex_agent import build_codex_command, build_live_prompt
from .command_runner import CommandResult, CommandRunner
from .events import EventWriter
from .task_model import TaskSpec
from .workspace import create_workspace


@dataclass(frozen=True)
class LiveResult:
    ok: bool
    completion_ms: float
    commands: list[CommandResult]
    workspace: Path
    events_path: Path
    codex_stdout_path: Path
    codex_stderr_path: Path
    patch_path: Path


def _write_solution_patch(workspace: Path, patch_path: Path) -> None:
    completed = subprocess.run(
        ["git", "diff", "--binary"],
        cwd=workspace,
        text=True,
        capture_output=True,
    )
    patch_path.write_text(completed.stdout, encoding="utf-8")


def _run_codex_command(command: list[str], workspace: Path, timeout_seconds: int) -> CommandResult:
    start = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=workspace,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
        return CommandResult(
            name="codex-agent",
            argv=tuple(command),
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            duration_ms=(time.perf_counter() - start) * 1000,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else exc.stdout or ""
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else exc.stderr or ""
        return CommandResult(
            name="codex-agent",
            argv=tuple(command),
            returncode=124,
            stdout=stdout,
            stderr=stderr or "codex command timed out",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


def run_codex_live(
    task: TaskSpec,
    run_dir: Path,
    run_id: str,
    side: str,
    model: str | None = None,
    codex_binary: str = "codex",
    sandbox: str = "workspace-write",
    timeout_seconds: int | None = None,
) -> LiveResult:
    workspace = create_workspace(task, run_dir / "workspace")
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    events_path = artifacts / "events.jsonl"
    codex_stdout_path = artifacts / "codex.stdout.jsonl"
    codex_stderr_path = artifacts / "codex.stderr.log"
    command_path = artifacts / "codex.command.txt"
    patch_path = artifacts / "solution.patch"
    for path in (events_path, codex_stdout_path, codex_stderr_path, command_path, patch_path):
        if path.exists():
            path.unlink()

    prompt = build_live_prompt(task)
    command = build_codex_command(
        workspace.resolve(),
        prompt,
        model=model,
        codex_binary=codex_binary,
        sandbox=sandbox,
    )
    command_path.write_text(shlex.join(command) + "\n", encoding="utf-8")

    events = EventWriter(events_path)
    events.write("run_started", run_id=run_id, side=side, task_id=task.task_id, mode="live")
    start = time.perf_counter()
    commands: list[CommandResult] = []

    codex_timeout = timeout_seconds if timeout_seconds is not None else task.timeout_seconds * 4
    events.write("command_started", run_id=run_id, side=side, command="codex-agent")
    codex_result = _run_codex_command(command, workspace=workspace, timeout_seconds=codex_timeout)
    codex_stdout_path.write_text(codex_result.stdout, encoding="utf-8")
    codex_stderr_path.write_text(codex_result.stderr, encoding="utf-8")
    commands.append(codex_result)
    events.write(
        "command_finished",
        run_id=run_id,
        side=side,
        command=codex_result.name,
        returncode=codex_result.returncode,
        duration_ms=codex_result.duration_ms,
    )

    runner = CommandRunner(task.allowed_commands, timeout_seconds=task.timeout_seconds)
    if codex_result.returncode == 0:
        for command_spec in task.success_commands:
            events.write("command_started", run_id=run_id, side=side, command=command_spec.name)
            result = runner.run(command_spec.argv, cwd=workspace, name=command_spec.name)
            commands.append(result)
            events.write(
                "command_finished",
                run_id=run_id,
                side=side,
                command=result.name,
                returncode=result.returncode,
                duration_ms=result.duration_ms,
            )

    _write_solution_patch(workspace, patch_path)
    ok = bool(commands) and all(item.returncode == 0 for item in commands)
    completion_ms = (time.perf_counter() - start) * 1000
    events.write("run_finished", run_id=run_id, side=side, ok=ok, completion_ms=completion_ms)
    return LiveResult(
        ok=ok,
        completion_ms=completion_ms,
        commands=commands,
        workspace=workspace,
        events_path=events_path,
        codex_stdout_path=codex_stdout_path,
        codex_stderr_path=codex_stderr_path,
        patch_path=patch_path,
    )
