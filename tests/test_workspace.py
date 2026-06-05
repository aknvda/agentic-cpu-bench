import subprocess
import sys
from pathlib import Path

from agentic_cpu_bench.task_model import load_task
from agentic_cpu_bench.workspace import create_workspace, run_success_commands


def test_fixture_starts_broken_then_expected_patch_passes(tmp_path):
    task = load_task(Path("tasks/python_cpp_bugfix/manifest.json"))
    workspace = create_workspace(task, tmp_path / "run")

    subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "sys.path.insert(0, 'src'); "
                "from cpu_bench_demo import extract_error_codes; "
                "assert extract_error_codes('ok ERR-104 retry ERR-205 done') == ['104', '205']"
            ),
        ],
        cwd=workspace,
        check=True,
    )

    broken = run_success_commands(task, workspace)
    assert broken.ok is False
    assert "python-tests" in broken.failed_command_names or "cpp-tests" in broken.failed_command_names

    subprocess.run(["git", "apply", str(task.expected_patch.resolve())], cwd=workspace, check=True)
    fixed = run_success_commands(task, workspace)
    assert fixed.ok is True
    assert fixed.failed_command_names == []
