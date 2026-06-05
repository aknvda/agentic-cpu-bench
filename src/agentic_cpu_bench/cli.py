from __future__ import annotations

import argparse
import shlex
from pathlib import Path
from typing import Any

from .artifacts import summarize_run_root
from .codex_agent import build_codex_command, build_live_prompt
from .dashboard import write_dashboard
from .k8s import NAMESPACE, grace_pod_spec, grace_replay_job_spec, x86_pod_spec, x86_replay_job_spec
from .k8s import grace_worker_job_spec, x86_worker_job_spec
from .live import run_codex_live
from .live_dashboard import serve_dashboard, watch_k8s_dashboard
from .metrics import summarize_commands
from .report import write_report
from .replay import replay_expected_patch
from .task_model import TaskSpec, load_task


COMMANDS = (
    "validate-task",
    "replay",
    "codex-live",
    "codex-run",
    "dashboard",
    "report",
    "k8s-smoke",
    "k8s-replay-jobs",
    "k8s-worker-jobs",
    "serve-dashboard",
    "watch-k8s-dashboard",
)
DEFAULT_TASK = "tasks/python_cpp_bugfix/manifest.json"


def _add_task_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--task", default=DEFAULT_TASK)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentic-cpu-bench")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in COMMANDS:
        command_parser = subparsers.add_parser(command)
        if command in {"validate-task", "replay", "codex-live", "codex-run", "dashboard", "report"}:
            _add_task_argument(command_parser)
        if command == "replay":
            command_parser.add_argument("--run-dir", required=True)
            command_parser.add_argument("--run-id", default="local-replay")
            command_parser.add_argument("--side", default="local")
        elif command == "codex-live":
            command_parser.add_argument("--workspace", required=True)
            command_parser.add_argument("--model")
            command_parser.add_argument("--codex-bin", default="codex")
        elif command == "codex-run":
            command_parser.add_argument("--run-dir", required=True)
            command_parser.add_argument("--run-id", default="live-local")
            command_parser.add_argument("--side", default="live")
            command_parser.add_argument("--model")
            command_parser.add_argument("--codex-bin", default="codex")
            command_parser.add_argument("--sandbox", default="workspace-write")
            command_parser.add_argument("--timeout-seconds", type=int)
        elif command == "dashboard":
            command_parser.add_argument("--run-root", default="tmp/cli-dashboard")
            command_parser.add_argument("--output", default="tmp/agentic-cpu-bench/dashboard.html")
            command_parser.add_argument("--from-artifacts", action="store_true")
        elif command == "report":
            command_parser.add_argument("--run-root", default="tmp/cli-report")
            command_parser.add_argument("--output", default="tmp/agentic-cpu-bench/report.md")
            command_parser.add_argument("--from-artifacts", action="store_true")
        elif command == "k8s-smoke":
            command_parser.add_argument("--image", default="registry.k8s.io/pause:3.10")
            command_parser.add_argument("--namespace", default=NAMESPACE)
        elif command == "k8s-replay-jobs":
            command_parser.add_argument("--image", required=True)
            command_parser.add_argument("--namespace", default=NAMESPACE)
        elif command == "k8s-worker-jobs":
            command_parser.add_argument("--image", default="python:3.12-slim")
            command_parser.add_argument("--namespace", default=NAMESPACE)
            command_parser.add_argument("--cpu-request", default="1500m")
            command_parser.add_argument("--mode", choices=("replay", "live"), default="replay")
            command_parser.add_argument("--source-config-map", default="agentic-cpu-bench-source")
            command_parser.add_argument("--codex-secret")
            command_parser.add_argument("--model")
            command_parser.add_argument("--codex-sandbox", default="danger-full-access")
            command_parser.add_argument("--codex-version", default="0.136.0")
            command_parser.add_argument("--image-pull-secret")
            command_parser.add_argument("--x86-node")
            command_parser.add_argument("--grace-node")
            command_parser.add_argument("--start-at-epoch", type=float)
        elif command == "serve-dashboard":
            command_parser.add_argument("--state", default="tmp/agentic-cpu-bench/live-state.json")
            command_parser.add_argument("--host", default="127.0.0.1")
            command_parser.add_argument("--port", type=int, default=8765)
        elif command == "watch-k8s-dashboard":
            command_parser.add_argument("--state", default="tmp/agentic-cpu-bench/live-state.json")
            command_parser.add_argument("--namespace", default="agentic-cpu-bench-demo")
            command_parser.add_argument("--mode", choices=("replay", "live"), default="replay")
            command_parser.add_argument("--interval-seconds", type=float, default=1.0)
            command_parser.add_argument("--timeout-seconds", type=int, default=1200)
    return parser


def _ensure_task_files_exist(task: TaskSpec) -> None:
    required_paths = {
        "prompt": task.prompt,
        "expected_patch": task.expected_patch,
        "fixture_repo": task.fixture_repo,
    }
    missing = [f"{name}={path}" for name, path in required_paths.items() if not path.exists()]
    if missing:
        raise FileNotFoundError("missing task path(s): " + ", ".join(missing))


def _load_valid_task(task_path: str, parser: argparse.ArgumentParser) -> TaskSpec:
    task = load_task(Path(task_path))
    try:
        _ensure_task_files_exist(task)
    except FileNotFoundError as exc:
        parser.error(str(exc))
    return task


def _safe_tmp_path(raw_path: str, parser: argparse.ArgumentParser) -> Path:
    path = Path(raw_path)
    parts = raw_path.split("/")
    unsafe = (
        path.is_absolute()
        or raw_path in {".", "..", "tmp", "tmp/"}
        or ".." in raw_path
        or not raw_path.startswith("tmp/")
        or "//" in raw_path
        or any(part in {"", "."} for part in parts)
    )
    if unsafe:
        parser.error(f"unsafe tmp path: {raw_path}")

    current = Path(parts[0])
    if current.is_symlink():
        parser.error("unsafe tmp path: tmp is a symlink")

    for component in parts[1:]:
        current = current / component
        if current.is_symlink():
            parser.error(f"unsafe tmp path contains symlink component: {current}")
        if not current.exists():
            break
    return path


def _safe_tmp_dir_path(raw_path: str, parser: argparse.ArgumentParser) -> Path:
    path = _safe_tmp_path(raw_path, parser)
    current = Path("tmp")
    if current.exists() and not current.is_dir():
        parser.error("unsafe tmp path component is not a directory: tmp")

    for component in raw_path.split("/")[1:]:
        if not current.exists():
            break
        current = current / component
        if current.exists() and not current.is_dir():
            parser.error(f"unsafe tmp path component is not a directory: {current}")
    return path


def _safe_tmp_write_target(raw_path: str, parser: argparse.ArgumentParser) -> Path:
    path = _safe_tmp_path(raw_path, parser)
    parts = raw_path.split("/")
    current = Path(parts[0])
    if current.exists() and not current.is_dir():
        parser.error(f"unsafe tmp path parent is not a directory: {current}")
    for component in parts[1:-1]:
        if not current.exists():
            break
        current = current / component
        if current.exists() and not current.is_dir():
            parser.error(f"unsafe tmp path parent is not a directory: {current}")
    if path.is_symlink():
        parser.error(f"unsafe tmp path contains symlink component: {raw_path}")
    if path.is_dir():
        parser.error(f"unsafe tmp path is a directory: {raw_path}")
    if path.exists() and not path.is_file():
        parser.error(f"unsafe tmp path is not a regular file: {raw_path}")
    return path


def _reject_path_under_root(path: Path, root: Path, parser: argparse.ArgumentParser) -> None:
    path_parts = path.parts
    root_parts = root.parts
    if path_parts[: len(root_parts)] == root_parts:
        parser.error(f"artifact output must not be under replay run root: {path}")


def _summary_from_replay(task: TaskSpec, result: Any, side: str) -> dict[str, Any]:
    summary = summarize_commands(result.commands, result.completion_ms)
    summary.update(
        {
            "side": side,
            "task_id": task.task_id,
            "ok": result.ok,
            "agents_at_sla": 1 if result.ok else 0,
        }
    )
    return summary


def _safe_replay_dir(side: str, run_dir: Path, parser: argparse.ArgumentParser) -> tuple[str, Path]:
    safe_run_dir = _safe_tmp_dir_path(str(run_dir), parser)
    _safe_tmp_dir_path(str(safe_run_dir / "workspace"), parser)
    _safe_tmp_dir_path(str(safe_run_dir / "artifacts"), parser)
    _safe_tmp_write_target(str(safe_run_dir / "artifacts" / "events.jsonl"), parser)
    return side, safe_run_dir


def _safe_replay_dirs(run_root: Path, parser: argparse.ArgumentParser) -> list[tuple[str, Path]]:
    replay_dirs = [(side, run_root / side) for side in ("grace", "x86")]
    safe_dirs: list[tuple[str, Path]] = []
    for side, run_dir in replay_dirs:
        safe_dirs.append(_safe_replay_dir(side, run_dir, parser))
    return safe_dirs


def _run_replay_pair(task: TaskSpec, run_root: Path, parser: argparse.ArgumentParser) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for side, run_dir in _safe_replay_dirs(run_root, parser):
        side, run_dir = _safe_replay_dir(side, run_dir, parser)
        result = replay_expected_patch(task, run_dir, run_id=f"local-{side}", side=side)
        summaries.append(_summary_from_replay(task, result, side))
    return summaries


def _artifact_summaries(run_root: Path, parser: argparse.ArgumentParser) -> list[dict[str, Any]]:
    _safe_replay_dirs(run_root, parser)
    try:
        return summarize_run_root(run_root)
    except (FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))
    raise AssertionError("unreachable")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "validate-task":
        task = _load_valid_task(args.task, parser)
        print(
            f"task_id={task.task_id} "
            f"success_commands={len(task.success_commands)} "
            f"prompt={task.prompt} "
            f"expected_patch={task.expected_patch} "
            f"fixture_repo={task.fixture_repo}"
        )
        return 0
    if args.command == "replay":
        task = load_task(Path(args.task))
        result = replay_expected_patch(task, Path(args.run_dir), run_id=args.run_id, side=args.side)
        print(f"ok={result.ok} completion_ms={result.completion_ms:.2f} events={result.events_path}")
        return 0 if result.ok else 1
    if args.command == "codex-live":
        task = _load_valid_task(args.task, parser)
        prompt = build_live_prompt(task)
        command = build_codex_command(Path(args.workspace), prompt, model=args.model, codex_binary=args.codex_bin)
        print(shlex.join(command))
        return 0
    if args.command == "codex-run":
        task = _load_valid_task(args.task, parser)
        side, run_dir = _safe_replay_dir(args.side, Path(args.run_dir), parser)
        result = run_codex_live(
            task,
            run_dir,
            run_id=args.run_id,
            side=side,
            model=args.model,
            codex_binary=args.codex_bin,
            sandbox=args.sandbox,
            timeout_seconds=args.timeout_seconds,
        )
        print(
            f"ok={result.ok} "
            f"completion_ms={result.completion_ms:.2f} "
            f"events={result.events_path} "
            f"workspace={result.workspace} "
            f"codex_stdout={result.codex_stdout_path} "
            f"solution_patch={result.patch_path}"
        )
        return 0 if result.ok else 1
    if args.command == "dashboard":
        task = _load_valid_task(args.task, parser)
        run_root = _safe_tmp_dir_path(args.run_root, parser)
        output_path = _safe_tmp_write_target(args.output, parser)
        _reject_path_under_root(output_path, run_root, parser)
        summaries = _artifact_summaries(run_root, parser) if args.from_artifacts else _run_replay_pair(task, run_root, parser)
        output_path = _safe_tmp_write_target(str(output_path), parser)
        output = write_dashboard(output_path, summaries)
        print(output)
        return 0
    if args.command == "report":
        task = _load_valid_task(args.task, parser)
        run_root = _safe_tmp_dir_path(args.run_root, parser)
        output_path = _safe_tmp_write_target(args.output, parser)
        results_path = _safe_tmp_write_target(str(output_path.parent / "results.json"), parser)
        _reject_path_under_root(output_path, run_root, parser)
        _reject_path_under_root(results_path, run_root, parser)
        summaries = _artifact_summaries(run_root, parser) if args.from_artifacts else _run_replay_pair(task, run_root, parser)
        output_path = _safe_tmp_write_target(str(output_path), parser)
        _safe_tmp_write_target(str(results_path), parser)
        output = write_report(output_path, summaries)
        print(output)
        print(output.parent / "results.json")
        return 0
    if args.command == "k8s-smoke":
        print(x86_pod_spec("smoke-x86", args.image, namespace=args.namespace), end="")
        print("---")
        print(grace_pod_spec("smoke-grace", args.image, namespace=args.namespace), end="")
        return 0
    if args.command == "k8s-replay-jobs":
        print(x86_replay_job_spec("agentic-cpu-bench-replay-x86", args.image, namespace=args.namespace), end="")
        print("---")
        print(grace_replay_job_spec("agentic-cpu-bench-replay-grace", args.image, namespace=args.namespace), end="")
        return 0
    if args.command == "k8s-worker-jobs":
        try:
            print(
                x86_worker_job_spec(
                    "agentic-cpu-bench-worker-x86",
                    args.image,
                    mode=args.mode,
                    source_config_map=args.source_config_map,
                    codex_secret=args.codex_secret,
                    model=args.model,
                    codex_sandbox=args.codex_sandbox,
                    codex_version=args.codex_version,
                    image_pull_secret=args.image_pull_secret,
                    namespace=args.namespace,
                    cpu_request=args.cpu_request,
                    node_name=args.x86_node,
                    start_at_epoch=args.start_at_epoch,
                ),
                end="",
            )
            print("---")
            print(
                grace_worker_job_spec(
                    "agentic-cpu-bench-worker-grace",
                    args.image,
                    mode=args.mode,
                    source_config_map=args.source_config_map,
                    codex_secret=args.codex_secret,
                    model=args.model,
                    codex_sandbox=args.codex_sandbox,
                    codex_version=args.codex_version,
                    image_pull_secret=args.image_pull_secret,
                    namespace=args.namespace,
                    cpu_request=args.cpu_request,
                    node_name=args.grace_node,
                    start_at_epoch=args.start_at_epoch,
                ),
                end="",
            )
        except ValueError as exc:
            parser.error(str(exc))
        return 0
    if args.command == "serve-dashboard":
        serve_dashboard(state_path=_safe_tmp_write_target(args.state, parser), host=args.host, port=args.port)
        return 0
    if args.command == "watch-k8s-dashboard":
        watch_k8s_dashboard(
            namespace=args.namespace,
            mode=args.mode,
            state_path=_safe_tmp_write_target(args.state, parser),
            interval_seconds=args.interval_seconds,
            timeout_seconds=args.timeout_seconds,
        )
        return 0
    return 0
