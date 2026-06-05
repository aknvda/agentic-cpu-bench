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
    events_path = artifacts / "events.jsonl"
    if events_path.exists():
        events_path.unlink()
    events = EventWriter(events_path)
    events.write("run_started", run_id=run_id, side=side, task_id=task.task_id, mode="replay")
    start = time.perf_counter()
    commands: list[CommandResult] = []

    patch_start = time.perf_counter()
    events.write("command_started", run_id=run_id, side=side, command="apply-patch")
    patch = subprocess.run(
        ["git", "apply", str(task.expected_patch.resolve())],
        cwd=workspace,
        text=True,
        capture_output=True,
    )
    patch_result = CommandResult(
        name="apply-patch",
        argv=("git", "apply", str(task.expected_patch.resolve())),
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
            events.write("command_started", run_id=run_id, side=side, command=command.name)
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
    return ReplayResult(
        ok=ok,
        completion_ms=completion_ms,
        commands=commands,
        workspace=workspace,
        events_path=events_path,
    )
