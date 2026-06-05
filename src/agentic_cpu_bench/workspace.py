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
