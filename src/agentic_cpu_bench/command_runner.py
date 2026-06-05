from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


def _output_to_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


@dataclass(frozen=True)
class CommandResult:
    name: str
    argv: tuple[str, ...]
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
        result_argv = tuple(argv)
        if not result_argv or result_argv[0] not in self.allowed_commands:
            return CommandResult(
                name=name,
                argv=result_argv,
                returncode=126,
                stdout="",
                stderr=f"command not allowed: {result_argv[0] if result_argv else '<empty>'}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        try:
            completed = subprocess.run(
                result_argv,
                cwd=cwd,
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
            )
            return CommandResult(
                name=name,
                argv=result_argv,
                returncode=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                name=name,
                argv=result_argv,
                returncode=124,
                stdout=_output_to_text(exc.stdout),
                stderr=_output_to_text(exc.stderr) or "command timed out",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
