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
