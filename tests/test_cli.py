from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import agentic_cpu_bench.cli as cli
from agentic_cpu_bench.command_runner import CommandResult


def _successful_command(name: str = "ok") -> CommandResult:
    return CommandResult(
        name=name,
        argv=("true",),
        returncode=0,
        stdout="",
        stderr="",
        duration_ms=12.5,
    )


def _write_minimal_task_manifest(tmp_path: Path) -> Path:
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    fixture_repo = tmp_path / "fixture"
    fixture_repo.mkdir()
    (task_dir / "prompt.md").write_text("Fix the fixture.\n", encoding="utf-8")
    (task_dir / "expected.patch").write_text("", encoding="utf-8")
    manifest = {
        "task_id": "cli_symlink_guard",
        "fixture_repo": str(fixture_repo),
        "prompt": "prompt.md",
        "expected_patch": "expected.patch",
        "timeout_seconds": 180,
        "tags": ["cli"],
        "success_commands": [{"name": "ok", "argv": ["true"]}],
        "allowed_commands": ["true"],
    }
    manifest_path = task_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def test_validate_task_prints_observable_summary(capsys):
    assert cli.main(["validate-task"]) == 0

    out = capsys.readouterr().out
    assert "python_cpp_bugfix" in out
    assert "success_commands=5" in out


def test_replay_prints_observable_summary_without_real_replay(monkeypatch, capsys):
    calls = []

    def fake_replay_expected_patch(task, run_dir: Path, run_id: str, side: str):
        calls.append((str(run_dir), run_id, side))
        return SimpleNamespace(
            ok=True,
            completion_ms=12.5,
            events_path=Path("tmp/replay/artifacts/events.jsonl"),
        )

    monkeypatch.setattr(cli, "replay_expected_patch", fake_replay_expected_patch)

    assert cli.main(["replay", "--run-dir", "tmp/replay", "--run-id", "r1", "--side", "grace"]) == 0

    assert calls == [("tmp/replay", "r1", "grace")]
    out = capsys.readouterr().out
    assert "ok=True" in out
    assert "tmp/replay/artifacts/events.jsonl" in out


def test_codex_live_prints_command_without_running_codex(capsys):
    assert cli.main(["codex-live", "--workspace", "/tmp/work", "--model", "gpt-5"]) == 0

    out = capsys.readouterr().out
    assert "codex --ask-for-approval never exec --model gpt-5" in out
    assert "--cd /tmp/work" in out


def test_codex_run_invokes_live_runner(monkeypatch, capsys):
    calls = []

    def fake_run_codex_live(task, run_dir: Path, run_id: str, side: str, model, codex_binary, sandbox, timeout_seconds):
        calls.append((str(run_dir), run_id, side, model, codex_binary, sandbox, timeout_seconds))
        return SimpleNamespace(
            ok=True,
            completion_ms=88.0,
            events_path=Path("tmp/live/artifacts/events.jsonl"),
            workspace=Path("tmp/live/workspace"),
            codex_stdout_path=Path("tmp/live/artifacts/codex.stdout.jsonl"),
            patch_path=Path("tmp/live/artifacts/solution.patch"),
        )

    monkeypatch.setattr(cli, "run_codex_live", fake_run_codex_live)

    assert (
        cli.main(
            [
                "codex-run",
                "--run-dir",
                "tmp/live",
                "--run-id",
                "r1",
                "--side",
                "grace",
                "--model",
                "gpt-5",
                "--codex-bin",
                "/tmp/fake-codex",
                "--timeout-seconds",
                "10",
            ]
        )
        == 0
    )

    assert calls == [("tmp/live", "r1", "grace", "gpt-5", "/tmp/fake-codex", "workspace-write", 10)]
    out = capsys.readouterr().out
    assert "ok=True" in out
    assert "codex_stdout=tmp/live/artifacts/codex.stdout.jsonl" in out


def test_k8s_smoke_prints_x86_and_grace_specs(capsys):
    assert cli.main(["k8s-smoke"]) == 0

    out = capsys.readouterr().out
    assert "name: smoke-x86" in out
    assert "name: smoke-grace" in out
    assert "namespace: agentic-cpu-bench-demo" in out
    assert "cloud.google.com/gke-nodepool: customer-cpu" in out
    assert "cloud.google.com/gke-nodepool: customer-gpu-w0e" in out
    assert "\n---\n" in out


def test_k8s_replay_jobs_prints_x86_and_grace_jobs(capsys):
    assert cli.main(["k8s-replay-jobs", "--image", "repo/cpu-bench:dev"]) == 0

    out = capsys.readouterr().out
    assert "kind: Job" in out
    assert "name: agentic-cpu-bench-replay-x86" in out
    assert "name: agentic-cpu-bench-replay-grace" in out
    assert "agentic-cpu-bench replay --run-dir tmp/cluster/x86" in out
    assert "agentic-cpu-bench replay --run-dir tmp/cluster/grace" in out


def test_k8s_worker_jobs_prints_namespace_worker_jobs(capsys):
    assert cli.main(["k8s-worker-jobs", "--mode", "replay", "--image", "python:3.12-slim"]) == 0

    out = capsys.readouterr().out
    assert "name: agentic-cpu-bench-worker-x86" in out
    assert "name: agentic-cpu-bench-worker-grace" in out
    assert "namespace: agentic-cpu-bench-demo" in out
    assert "agentic-cpu-bench replay --run-dir tmp/k8s-demo/x86" in out
    assert "agentic-cpu-bench replay --run-dir tmp/k8s-demo/grace" in out


def test_k8s_live_worker_jobs_require_codex_secret():
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["k8s-worker-jobs", "--mode", "live", "--image", "codex-worker:dev"])

    assert exc_info.value.code != 0


def test_k8s_live_worker_jobs_accept_model(capsys):
    assert (
        cli.main(
            [
                "k8s-worker-jobs",
                "--mode",
                "live",
                "--image",
                "codex-worker:dev",
                "--codex-secret",
                "codex-home",
                "--model",
                "gpt-5",
                "--image-pull-secret",
                "registry-pull-secret",
            ]
        )
        == 0
    )

    out = capsys.readouterr().out
    assert "--model gpt-5" in out
    assert "mountPath: /codex-seed" in out
    assert "imagePullSecrets:" in out
    assert "name: registry-pull-secret" in out


def test_watch_k8s_dashboard_cli_invokes_watcher(monkeypatch):
    calls = []

    def fake_watch(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(cli, "watch_k8s_dashboard", fake_watch)

    assert (
        cli.main(
            [
                "watch-k8s-dashboard",
                "--state",
                "tmp/live/state.json",
                "--namespace",
                "agentic-cpu-bench-demo",
                "--mode",
                "replay",
                "--interval-seconds",
                "0.5",
                "--timeout-seconds",
                "10",
            ]
        )
        == 0
    )

    assert calls == [
        {
            "namespace": "agentic-cpu-bench-demo",
            "mode": "replay",
            "state_path": Path("tmp/live/state.json"),
            "interval_seconds": 0.5,
            "timeout_seconds": 10,
        }
    ]


def test_serve_dashboard_cli_invokes_server(monkeypatch):
    calls = []

    def fake_serve(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(cli, "serve_dashboard", fake_serve)

    assert cli.main(["serve-dashboard", "--state", "tmp/live/state.json", "--host", "0.0.0.0", "--port", "9000"]) == 0

    assert calls == [{"state_path": Path("tmp/live/state.json"), "host": "0.0.0.0", "port": 9000}]


def test_dashboard_runs_replay_pair_and_writes_output(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    task_path = _write_minimal_task_manifest(tmp_path)
    calls: list[tuple[str, str]] = []

    def fake_replay_expected_patch(task, run_dir: Path, run_id: str, side: str):
        calls.append((str(run_dir), side))
        return SimpleNamespace(
            ok=True,
            completion_ms=42.0,
            commands=[_successful_command(side)],
        )

    monkeypatch.setattr(cli, "replay_expected_patch", fake_replay_expected_patch)
    output = Path("tmp/test-cli-output/dashboard.html")

    assert (
        cli.main(
            [
                "dashboard",
                "--task",
                str(task_path),
                "--run-root",
                "tmp/test-cli-dashboard",
                "--output",
                str(output),
            ]
        )
        == 0
    )

    assert calls == [
        ("tmp/test-cli-dashboard/grace", "grace"),
        ("tmp/test-cli-dashboard/x86", "x86"),
    ]
    assert output.exists()
    assert "Race First" in output.read_text(encoding="utf-8")
    assert str(output) in capsys.readouterr().out


def test_report_runs_replay_pair_and_writes_output(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    task_path = _write_minimal_task_manifest(tmp_path)
    calls: list[tuple[str, str]] = []

    def fake_replay_expected_patch(task, run_dir: Path, run_id: str, side: str):
        calls.append((str(run_dir), side))
        return SimpleNamespace(
            ok=True,
            completion_ms=42.0,
            commands=[_successful_command(side)],
        )

    monkeypatch.setattr(cli, "replay_expected_patch", fake_replay_expected_patch)
    output = Path("tmp/test-cli-output/report.md")

    assert (
        cli.main(
            [
                "report",
                "--task",
                str(task_path),
                "--run-root",
                "tmp/test-cli-report",
                "--output",
                str(output),
            ]
        )
        == 0
    )

    assert calls == [
        ("tmp/test-cli-report/grace", "grace"),
        ("tmp/test-cli-report/x86", "x86"),
    ]
    assert output.exists()
    assert "results.json" in capsys.readouterr().out
    assert Path("tmp/test-cli-output/results.json").exists()


@pytest.mark.parametrize("command", ["dashboard", "report"])
def test_artifact_mode_uses_existing_events_without_replay(monkeypatch, tmp_path, command):
    monkeypatch.chdir(tmp_path)
    task_path = _write_minimal_task_manifest(tmp_path)
    calls = []

    def fake_replay_expected_patch(task, run_dir: Path, run_id: str, side: str):
        calls.append((run_dir, run_id, side))
        return SimpleNamespace(ok=True, completion_ms=42.0, commands=[_successful_command(side)])

    def fake_summarize_run_root(run_root: Path):
        assert run_root == Path(f"tmp/test-cli-{command}")
        return [
            {
                "side": "grace",
                "task_id": "cli_symlink_guard",
                "ok": True,
                "completion_ms": 10.0,
                "cpu_tool_step_ms": 9.0,
                "command_count": 1,
                "agents_at_sla": 1,
            },
            {
                "side": "x86",
                "task_id": "cli_symlink_guard",
                "ok": True,
                "completion_ms": 11.0,
                "cpu_tool_step_ms": 10.0,
                "command_count": 1,
                "agents_at_sla": 1,
            },
        ]

    run_root = Path(f"tmp/test-cli-{command}")
    for side in ("grace", "x86"):
        (run_root / side / "artifacts").mkdir(parents=True)

    monkeypatch.setattr(cli, "replay_expected_patch", fake_replay_expected_patch)
    monkeypatch.setattr(cli, "summarize_run_root", fake_summarize_run_root)
    output = Path(f"tmp/test-cli-output/{command}.out")

    assert (
        cli.main(
            [
                command,
                "--task",
                str(task_path),
                "--run-root",
                str(run_root),
                "--output",
                str(output),
                "--from-artifacts",
            ]
        )
        == 0
    )

    assert calls == []
    assert output.exists()


@pytest.mark.parametrize("command", ["dashboard", "report"])
@pytest.mark.parametrize("side", ["grace", "x86"])
def test_symlinked_side_run_dir_exits_before_replay(monkeypatch, tmp_path, command, side):
    monkeypatch.chdir(tmp_path)
    task_path = _write_minimal_task_manifest(tmp_path)
    external_dir = tmp_path / "external"
    external_dir.mkdir()
    marker = external_dir / "marker.txt"
    marker.write_text("keep me\n", encoding="utf-8")

    run_root = f"tmp/test-cli-{command}"
    side_link = tmp_path / run_root / side
    side_link.parent.mkdir(parents=True)
    side_link.symlink_to(external_dir, target_is_directory=True)

    calls = []

    def fake_replay_expected_patch(task, run_dir: Path, run_id: str, side: str):
        calls.append((run_dir, run_id, side))
        return SimpleNamespace(ok=True, completion_ms=42.0, commands=[_successful_command()])

    monkeypatch.setattr(cli, "replay_expected_patch", fake_replay_expected_patch)

    with pytest.raises(SystemExit) as exc_info:
        cli.main(
            [
                command,
                "--task",
                str(task_path),
                "--run-root",
                run_root,
                "--output",
                "tmp/test-cli-output/out.html",
            ]
        )

    assert exc_info.value.code != 0
    assert calls == []
    assert marker.read_text(encoding="utf-8") == "keep me\n"


@pytest.mark.parametrize("command", ["dashboard", "report"])
@pytest.mark.parametrize("side", ["grace", "x86"])
def test_regular_file_side_run_dir_exits_before_replay(monkeypatch, tmp_path, command, side):
    monkeypatch.chdir(tmp_path)
    task_path = _write_minimal_task_manifest(tmp_path)

    run_root = f"tmp/test-cli-{command}"
    side_path = tmp_path / run_root / side
    side_path.parent.mkdir(parents=True)
    side_path.write_text("not a directory\n", encoding="utf-8")

    calls = []

    def fake_replay_expected_patch(task, run_dir: Path, run_id: str, side: str):
        calls.append((run_dir, run_id, side))
        return SimpleNamespace(ok=True, completion_ms=42.0, commands=[_successful_command()])

    monkeypatch.setattr(cli, "replay_expected_patch", fake_replay_expected_patch)

    with pytest.raises(SystemExit) as exc_info:
        cli.main(
            [
                command,
                "--task",
                str(task_path),
                "--run-root",
                run_root,
                "--output",
                "tmp/test-cli-output/out.html",
            ]
        )

    assert exc_info.value.code != 0
    assert calls == []
    assert side_path.read_text(encoding="utf-8") == "not a directory\n"


@pytest.mark.parametrize("command", ["dashboard", "report"])
def test_regular_file_run_root_exits_before_replay(monkeypatch, tmp_path, command):
    monkeypatch.chdir(tmp_path)
    task_path = _write_minimal_task_manifest(tmp_path)
    run_root = Path(f"tmp/test-cli-{command}")
    run_root.parent.mkdir(parents=True)
    run_root.write_text("not a directory\n", encoding="utf-8")
    calls = []

    def fake_replay_expected_patch(task, run_dir: Path, run_id: str, side: str):
        calls.append((run_dir, run_id, side))
        return SimpleNamespace(ok=True, completion_ms=42.0, commands=[_successful_command()])

    monkeypatch.setattr(cli, "replay_expected_patch", fake_replay_expected_patch)

    with pytest.raises(SystemExit) as exc_info:
        cli.main(
            [
                command,
                "--task",
                str(task_path),
                "--run-root",
                str(run_root),
                "--output",
                "tmp/test-cli-output/out.html",
            ]
        )

    assert exc_info.value.code != 0
    assert calls == []
    assert run_root.read_text(encoding="utf-8") == "not a directory\n"


@pytest.mark.parametrize("command", ["dashboard", "report"])
@pytest.mark.parametrize("side", ["grace", "x86"])
def test_symlinked_workspace_under_side_exits_before_replay(monkeypatch, tmp_path, command, side):
    monkeypatch.chdir(tmp_path)
    task_path = _write_minimal_task_manifest(tmp_path)
    external_dir = tmp_path / "external-workspace"
    external_dir.mkdir()
    marker = external_dir / "marker.txt"
    marker.write_text("keep workspace\n", encoding="utf-8")

    run_root = f"tmp/test-cli-{command}"
    workspace_link = tmp_path / run_root / side / "workspace"
    workspace_link.parent.mkdir(parents=True)
    workspace_link.symlink_to(external_dir, target_is_directory=True)

    calls = []

    def fake_replay_expected_patch(task, run_dir: Path, run_id: str, side: str):
        calls.append((run_dir, run_id, side))
        return SimpleNamespace(ok=True, completion_ms=42.0, commands=[_successful_command()])

    monkeypatch.setattr(cli, "replay_expected_patch", fake_replay_expected_patch)

    with pytest.raises(SystemExit) as exc_info:
        cli.main(
            [
                command,
                "--task",
                str(task_path),
                "--run-root",
                run_root,
                "--output",
                "tmp/test-cli-output/out.html",
            ]
        )

    assert exc_info.value.code != 0
    assert calls == []
    assert marker.read_text(encoding="utf-8") == "keep workspace\n"


@pytest.mark.parametrize("command", ["dashboard", "report"])
@pytest.mark.parametrize("side", ["grace", "x86"])
def test_regular_file_workspace_under_side_exits_before_replay(monkeypatch, tmp_path, command, side):
    monkeypatch.chdir(tmp_path)
    task_path = _write_minimal_task_manifest(tmp_path)

    run_root = f"tmp/test-cli-{command}"
    workspace_path = tmp_path / run_root / side / "workspace"
    workspace_path.parent.mkdir(parents=True)
    workspace_path.write_text("not a directory\n", encoding="utf-8")

    calls = []

    def fake_replay_expected_patch(task, run_dir: Path, run_id: str, side: str):
        calls.append((run_dir, run_id, side))
        return SimpleNamespace(ok=True, completion_ms=42.0, commands=[_successful_command()])

    monkeypatch.setattr(cli, "replay_expected_patch", fake_replay_expected_patch)

    with pytest.raises(SystemExit) as exc_info:
        cli.main(
            [
                command,
                "--task",
                str(task_path),
                "--run-root",
                run_root,
                "--output",
                "tmp/test-cli-output/out.html",
            ]
        )

    assert exc_info.value.code != 0
    assert calls == []
    assert workspace_path.read_text(encoding="utf-8") == "not a directory\n"


@pytest.mark.parametrize("command", ["dashboard", "report"])
@pytest.mark.parametrize("side", ["grace", "x86"])
def test_symlinked_artifacts_under_side_exits_before_replay(monkeypatch, tmp_path, command, side):
    monkeypatch.chdir(tmp_path)
    task_path = _write_minimal_task_manifest(tmp_path)
    external_dir = tmp_path / "external-artifacts"
    external_dir.mkdir()
    marker = external_dir / "marker.txt"
    events = external_dir / "events.jsonl"
    marker.write_text("keep artifacts\n", encoding="utf-8")
    events.write_text("external events\n", encoding="utf-8")

    run_root = f"tmp/test-cli-{command}"
    artifacts_link = tmp_path / run_root / side / "artifacts"
    artifacts_link.parent.mkdir(parents=True)
    artifacts_link.symlink_to(external_dir, target_is_directory=True)

    calls = []

    def fake_replay_expected_patch(task, run_dir: Path, run_id: str, side: str):
        calls.append((run_dir, run_id, side))
        return SimpleNamespace(ok=True, completion_ms=42.0, commands=[_successful_command()])

    monkeypatch.setattr(cli, "replay_expected_patch", fake_replay_expected_patch)

    with pytest.raises(SystemExit) as exc_info:
        cli.main(
            [
                command,
                "--task",
                str(task_path),
                "--run-root",
                run_root,
                "--output",
                "tmp/test-cli-output/out.html",
            ]
        )

    assert exc_info.value.code != 0
    assert calls == []
    assert marker.read_text(encoding="utf-8") == "keep artifacts\n"
    assert events.read_text(encoding="utf-8") == "external events\n"


@pytest.mark.parametrize("command", ["dashboard", "report"])
@pytest.mark.parametrize("side", ["grace", "x86"])
def test_regular_file_artifacts_under_side_exits_before_replay(monkeypatch, tmp_path, command, side):
    monkeypatch.chdir(tmp_path)
    task_path = _write_minimal_task_manifest(tmp_path)

    run_root = f"tmp/test-cli-{command}"
    artifacts_path = tmp_path / run_root / side / "artifacts"
    artifacts_path.parent.mkdir(parents=True)
    artifacts_path.write_text("not a directory\n", encoding="utf-8")

    calls = []

    def fake_replay_expected_patch(task, run_dir: Path, run_id: str, side: str):
        calls.append((run_dir, run_id, side))
        return SimpleNamespace(ok=True, completion_ms=42.0, commands=[_successful_command()])

    monkeypatch.setattr(cli, "replay_expected_patch", fake_replay_expected_patch)

    with pytest.raises(SystemExit) as exc_info:
        cli.main(
            [
                command,
                "--task",
                str(task_path),
                "--run-root",
                run_root,
                "--output",
                "tmp/test-cli-output/out.html",
            ]
        )

    assert exc_info.value.code != 0
    assert calls == []
    assert artifacts_path.read_text(encoding="utf-8") == "not a directory\n"


@pytest.mark.parametrize("command", ["dashboard", "report"])
@pytest.mark.parametrize("side", ["grace", "x86"])
def test_broken_events_symlink_under_artifacts_exits_before_replay(monkeypatch, tmp_path, command, side):
    monkeypatch.chdir(tmp_path)
    task_path = _write_minimal_task_manifest(tmp_path)
    external_target = tmp_path / "external-events.jsonl"

    run_root = f"tmp/test-cli-{command}"
    events_link = tmp_path / run_root / side / "artifacts" / "events.jsonl"
    events_link.parent.mkdir(parents=True)
    events_link.symlink_to(external_target)

    calls = []

    def fake_replay_expected_patch(task, run_dir: Path, run_id: str, side: str):
        calls.append((run_dir, run_id, side))
        return SimpleNamespace(ok=True, completion_ms=42.0, commands=[_successful_command()])

    monkeypatch.setattr(cli, "replay_expected_patch", fake_replay_expected_patch)

    with pytest.raises(SystemExit) as exc_info:
        cli.main(
            [
                command,
                "--task",
                str(task_path),
                "--run-root",
                run_root,
                "--output",
                "tmp/test-cli-output/out.html",
            ]
        )

    assert exc_info.value.code != 0
    assert calls == []
    assert not external_target.exists()


@pytest.mark.parametrize("command", ["dashboard", "report"])
def test_grace_mutated_x86_events_path_exits_before_x86_replay(monkeypatch, tmp_path, command):
    monkeypatch.chdir(tmp_path)
    task_path = _write_minimal_task_manifest(tmp_path)
    run_root = f"tmp/test-cli-{command}"
    external_target = tmp_path / "external-events.jsonl"
    calls = []

    def fake_replay_expected_patch(task, run_dir: Path, run_id: str, side: str):
        calls.append((str(run_dir), side))
        if side == "grace":
            events_link = Path(run_root) / "x86" / "artifacts" / "events.jsonl"
            events_link.parent.mkdir(parents=True)
            events_link.symlink_to(external_target)
        return SimpleNamespace(ok=True, completion_ms=42.0, commands=[_successful_command(side)])

    monkeypatch.setattr(cli, "replay_expected_patch", fake_replay_expected_patch)

    with pytest.raises(SystemExit) as exc_info:
        cli.main(
            [
                command,
                "--task",
                str(task_path),
                "--run-root",
                run_root,
                "--output",
                "tmp/test-cli-output/out.html",
            ]
        )

    assert exc_info.value.code != 0
    assert calls == [(f"{run_root}/grace", "grace")]
    assert not external_target.exists()


@pytest.mark.parametrize("command", ["dashboard", "report"])
@pytest.mark.parametrize(
    "run_root",
    ["/tmp/bad", "build/out", ".", "..", "tmp", "tmp/", "tmp/../run", "tmp/run//x", "tmp/run/./x"],
)
def test_unsafe_run_root_exits_before_replay(monkeypatch, tmp_path, command, run_root):
    calls = []

    def fake_replay_expected_patch(task, run_dir: Path, run_id: str, side: str):
        calls.append((run_dir, run_id, side))
        return SimpleNamespace(ok=True, completion_ms=42.0, commands=[_successful_command()])

    monkeypatch.setattr(cli, "replay_expected_patch", fake_replay_expected_patch)

    with pytest.raises(SystemExit) as exc_info:
        cli.main([command, "--run-root", run_root, "--output", "tmp/test-cli-output/out.html"])

    assert exc_info.value.code != 0
    assert calls == []


@pytest.mark.parametrize(
    ("command", "output"),
    [
        ("dashboard", "tmp/test-cli-output/dashboard.html"),
        ("report", "tmp/test-cli-output/report.md"),
    ],
)
def test_output_directory_exits_before_replay(monkeypatch, tmp_path, command, output):
    monkeypatch.chdir(tmp_path)
    task_path = _write_minimal_task_manifest(tmp_path)
    Path(output).mkdir(parents=True)
    calls = []

    def fake_replay_expected_patch(task, run_dir: Path, run_id: str, side: str):
        calls.append((run_dir, run_id, side))
        return SimpleNamespace(ok=True, completion_ms=42.0, commands=[_successful_command()])

    monkeypatch.setattr(cli, "replay_expected_patch", fake_replay_expected_patch)
    monkeypatch.setattr(cli, "write_dashboard", lambda path, summaries: Path(path))
    monkeypatch.setattr(cli, "write_report", lambda path, summaries: Path(path))

    with pytest.raises(SystemExit) as exc_info:
        cli.main(
            [
                command,
                "--task",
                str(task_path),
                "--run-root",
                f"tmp/test-cli-{command}",
                "--output",
                output,
            ]
        )

    assert exc_info.value.code != 0
    assert calls == []


def test_report_results_sidecar_directory_exits_before_replay(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    task_path = _write_minimal_task_manifest(tmp_path)
    output = Path("tmp/test-cli-output/report.md")
    (output.parent / "results.json").mkdir(parents=True)
    calls = []

    def fake_replay_expected_patch(task, run_dir: Path, run_id: str, side: str):
        calls.append((run_dir, run_id, side))
        return SimpleNamespace(ok=True, completion_ms=42.0, commands=[_successful_command()])

    monkeypatch.setattr(cli, "replay_expected_patch", fake_replay_expected_patch)
    monkeypatch.setattr(cli, "write_report", lambda path, summaries: Path(path))

    with pytest.raises(SystemExit) as exc_info:
        cli.main(
            [
                "report",
                "--task",
                str(task_path),
                "--run-root",
                "tmp/test-cli-report",
                "--output",
                str(output),
            ]
        )

    assert exc_info.value.code != 0
    assert calls == []


def test_existing_regular_dashboard_output_is_overwritten(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    task_path = _write_minimal_task_manifest(tmp_path)
    output = Path("tmp/test-cli-output/dashboard.html")
    output.parent.mkdir(parents=True)
    output.write_text("old dashboard\n", encoding="utf-8")
    calls = []

    def fake_replay_expected_patch(task, run_dir: Path, run_id: str, side: str):
        calls.append((str(run_dir), side))
        return SimpleNamespace(ok=True, completion_ms=42.0, commands=[_successful_command(side)])

    monkeypatch.setattr(cli, "replay_expected_patch", fake_replay_expected_patch)

    assert (
        cli.main(
            [
                "dashboard",
                "--task",
                str(task_path),
                "--run-root",
                "tmp/test-cli-dashboard",
                "--output",
                str(output),
            ]
        )
        == 0
    )

    assert calls == [
        ("tmp/test-cli-dashboard/grace", "grace"),
        ("tmp/test-cli-dashboard/x86", "x86"),
    ]
    assert "Race First" in output.read_text(encoding="utf-8")


def test_existing_regular_report_output_and_results_are_overwritten(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    task_path = _write_minimal_task_manifest(tmp_path)
    output = Path("tmp/test-cli-output/report.md")
    results = output.parent / "results.json"
    output.parent.mkdir(parents=True)
    output.write_text("old report\n", encoding="utf-8")
    results.write_text("old results\n", encoding="utf-8")
    calls = []

    def fake_replay_expected_patch(task, run_dir: Path, run_id: str, side: str):
        calls.append((str(run_dir), side))
        return SimpleNamespace(ok=True, completion_ms=42.0, commands=[_successful_command(side)])

    monkeypatch.setattr(cli, "replay_expected_patch", fake_replay_expected_patch)

    assert (
        cli.main(
            [
                "report",
                "--task",
                str(task_path),
                "--run-root",
                "tmp/test-cli-report",
                "--output",
                str(output),
            ]
        )
        == 0
    )

    assert calls == [
        ("tmp/test-cli-report/grace", "grace"),
        ("tmp/test-cli-report/x86", "x86"),
    ]
    assert "Agentic CPU Bench Report" in output.read_text(encoding="utf-8")
    assert "old results" not in results.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("command", "output"),
    [
        ("dashboard", "tmp/run/grace/workspace/link/out.html"),
        ("report", "tmp/run/grace/workspace/link/out.md"),
    ],
)
def test_output_under_run_root_exits_before_replay(monkeypatch, tmp_path, command, output):
    monkeypatch.chdir(tmp_path)
    task_path = _write_minimal_task_manifest(tmp_path)
    calls = []

    def fake_replay_expected_patch(task, run_dir: Path, run_id: str, side: str):
        calls.append((run_dir, run_id, side))
        return SimpleNamespace(ok=True, completion_ms=42.0, commands=[_successful_command()])

    monkeypatch.setattr(cli, "replay_expected_patch", fake_replay_expected_patch)
    monkeypatch.setattr(cli, "write_dashboard", lambda path, summaries: Path(path))
    monkeypatch.setattr(cli, "write_report", lambda path, summaries: Path(path))

    with pytest.raises(SystemExit) as exc_info:
        cli.main(
            [
                command,
                "--task",
                str(task_path),
                "--run-root",
                "tmp/run",
                "--output",
                output,
            ]
        )

    assert exc_info.value.code != 0
    assert calls == []


@pytest.mark.parametrize(
    ("command", "output"),
    [
        ("dashboard", "tmp/test-cli-output/dashboard.html"),
        ("report", "tmp/test-cli-output/report.md"),
    ],
)
def test_output_parent_mutated_after_replay_exits_before_write(monkeypatch, tmp_path, command, output):
    monkeypatch.chdir(tmp_path)
    task_path = _write_minimal_task_manifest(tmp_path)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True)
    external_dir = tmp_path / "external-output-dir"
    external_dir.mkdir()
    calls = []
    writes = []

    def fake_replay_expected_patch(task, run_dir: Path, run_id: str, side: str):
        calls.append((str(run_dir), side))
        if side == "x86":
            output_path.parent.rmdir()
            output_path.parent.symlink_to(external_dir, target_is_directory=True)
        return SimpleNamespace(ok=True, completion_ms=42.0, commands=[_successful_command(side)])

    def fake_write(path, summaries):
        writes.append(Path(path))
        return Path(path)

    monkeypatch.setattr(cli, "replay_expected_patch", fake_replay_expected_patch)
    monkeypatch.setattr(cli, "write_dashboard", fake_write)
    monkeypatch.setattr(cli, "write_report", fake_write)

    with pytest.raises(SystemExit) as exc_info:
        cli.main(
            [
                command,
                "--task",
                str(task_path),
                "--run-root",
                f"tmp/test-cli-{command}",
                "--output",
                output,
            ]
        )

    assert exc_info.value.code != 0
    assert calls == [
        (f"tmp/test-cli-{command}/grace", "grace"),
        (f"tmp/test-cli-{command}/x86", "x86"),
    ]
    assert writes == []
    assert list(external_dir.iterdir()) == []


@pytest.mark.parametrize(
    ("command", "output"),
    [
        ("dashboard", "tmp/test-cli-output/dashboard.html"),
        ("report", "tmp/test-cli-output/report.md"),
    ],
)
def test_regular_file_output_parent_exits_before_replay(monkeypatch, tmp_path, command, output):
    monkeypatch.chdir(tmp_path)
    task_path = _write_minimal_task_manifest(tmp_path)
    output_path = Path(output)
    output_path.parent.parent.mkdir(parents=True)
    output_path.parent.write_text("not a directory\n", encoding="utf-8")
    calls = []

    def fake_replay_expected_patch(task, run_dir: Path, run_id: str, side: str):
        calls.append((run_dir, run_id, side))
        return SimpleNamespace(ok=True, completion_ms=42.0, commands=[_successful_command()])

    monkeypatch.setattr(cli, "replay_expected_patch", fake_replay_expected_patch)
    monkeypatch.setattr(cli, "write_dashboard", lambda path, summaries: Path(path))
    monkeypatch.setattr(cli, "write_report", lambda path, summaries: Path(path))

    with pytest.raises(SystemExit) as exc_info:
        cli.main(
            [
                command,
                "--task",
                str(task_path),
                "--run-root",
                f"tmp/test-cli-{command}",
                "--output",
                output,
            ]
        )

    assert exc_info.value.code != 0
    assert calls == []
    assert output_path.parent.read_text(encoding="utf-8") == "not a directory\n"


@pytest.mark.parametrize(
    ("command", "output"),
    [
        ("dashboard", "tmp/test-cli-output/dashboard.html"),
        ("report", "tmp/test-cli-output/report.md"),
    ],
)
def test_symlinked_output_file_exits_before_replay(monkeypatch, tmp_path, command, output):
    monkeypatch.chdir(tmp_path)
    task_path = _write_minimal_task_manifest(tmp_path)
    external_target = tmp_path / "external-output"
    external_target.write_text("keep output\n", encoding="utf-8")
    output_path = Path(output)
    output_path.parent.mkdir(parents=True)
    output_path.symlink_to(external_target)
    calls = []

    def fake_replay_expected_patch(task, run_dir: Path, run_id: str, side: str):
        calls.append((run_dir, run_id, side))
        return SimpleNamespace(ok=True, completion_ms=42.0, commands=[_successful_command()])

    monkeypatch.setattr(cli, "replay_expected_patch", fake_replay_expected_patch)
    monkeypatch.setattr(cli, "write_dashboard", lambda path, summaries: Path(path))
    monkeypatch.setattr(cli, "write_report", lambda path, summaries: Path(path))

    with pytest.raises(SystemExit) as exc_info:
        cli.main(
            [
                command,
                "--task",
                str(task_path),
                "--run-root",
                f"tmp/test-cli-{command}",
                "--output",
                output,
            ]
        )

    assert exc_info.value.code != 0
    assert calls == []
    assert external_target.read_text(encoding="utf-8") == "keep output\n"


@pytest.mark.parametrize("command", ["dashboard", "report"])
@pytest.mark.parametrize("output", ["/tmp/bad.html", "build/out.html"])
def test_unsafe_output_exits_before_replay(monkeypatch, tmp_path, command, output):
    calls = []

    def fake_replay_expected_patch(task, run_dir: Path, run_id: str, side: str):
        calls.append((run_dir, run_id, side))
        return SimpleNamespace(ok=True, completion_ms=42.0, commands=[_successful_command()])

    monkeypatch.setattr(cli, "replay_expected_patch", fake_replay_expected_patch)
    monkeypatch.setattr(cli, "write_dashboard", lambda path, summaries: Path(path))
    monkeypatch.setattr(cli, "write_report", lambda path, summaries: Path(path))

    with pytest.raises(SystemExit) as exc_info:
        cli.main([command, "--run-root", "tmp/test-cli-output", "--output", output])

    assert exc_info.value.code != 0
    assert calls == []


def test_report_results_sidecar_symlink_exits_before_replay(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    task_path = _write_minimal_task_manifest(tmp_path)
    external_results = tmp_path / "external-results.json"
    external_results.write_text("keep results\n", encoding="utf-8")
    output = Path("tmp/test-cli-output/report.md")
    output.parent.mkdir(parents=True)
    (output.parent / "results.json").symlink_to(external_results)
    calls = []

    def fake_replay_expected_patch(task, run_dir: Path, run_id: str, side: str):
        calls.append((run_dir, run_id, side))
        return SimpleNamespace(ok=True, completion_ms=42.0, commands=[_successful_command()])

    monkeypatch.setattr(cli, "replay_expected_patch", fake_replay_expected_patch)
    monkeypatch.setattr(cli, "write_report", lambda path, summaries: Path(path))

    with pytest.raises(SystemExit) as exc_info:
        cli.main(
            [
                "report",
                "--task",
                str(task_path),
                "--run-root",
                "tmp/test-cli-report",
                "--output",
                str(output),
            ]
        )

    assert exc_info.value.code != 0
    assert calls == []
    assert external_results.read_text(encoding="utf-8") == "keep results\n"


@pytest.mark.parametrize("command", ["dashboard", "report"])
@pytest.mark.parametrize(
    ("run_root", "symlink_path"),
    [
        ("tmp/run", "tmp"),
        ("tmp/run/nested", "tmp/run"),
    ],
)
def test_symlinked_tmp_or_run_root_component_exits_before_replay(
    monkeypatch, tmp_path, command, run_root, symlink_path
):
    monkeypatch.chdir(tmp_path)
    task_path = _write_minimal_task_manifest(tmp_path)
    external_dir = tmp_path / "external-root"
    external_dir.mkdir()
    marker = external_dir / "marker.txt"
    marker.write_text("keep root\n", encoding="utf-8")

    link = tmp_path / symlink_path
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(external_dir, target_is_directory=True)

    calls = []

    def fake_replay_expected_patch(task, run_dir: Path, run_id: str, side: str):
        calls.append((run_dir, run_id, side))
        return SimpleNamespace(ok=True, completion_ms=42.0, commands=[_successful_command()])

    monkeypatch.setattr(cli, "replay_expected_patch", fake_replay_expected_patch)

    with pytest.raises(SystemExit) as exc_info:
        cli.main(
            [
                command,
                "--task",
                str(task_path),
                "--run-root",
                run_root,
                "--output",
                "tmp/test-cli-output/out.html",
            ]
        )

    assert exc_info.value.code != 0
    assert calls == []
    assert marker.read_text(encoding="utf-8") == "keep root\n"
