from agentic_cpu_bench.command_runner import CommandRunner


def test_command_runner_allows_listed_command(tmp_path):
    runner = CommandRunner(allowed_commands=["python"])
    result = runner.run(["python", "-c", "print('ok')"], cwd=tmp_path, name="hello")
    assert result.name == "hello"
    assert result.returncode == 0
    assert result.stdout.strip() == "ok"
    assert result.duration_ms >= 0


def test_command_runner_result_argv_is_immutable_tuple(tmp_path):
    runner = CommandRunner(allowed_commands=["python"])
    result = runner.run(["python", "-c", "print('ok')"], cwd=tmp_path, name="hello")
    assert result.argv == ("python", "-c", "print('ok')")
    assert not hasattr(result.argv, "append")


def test_command_runner_blocks_unlisted_command(tmp_path):
    runner = CommandRunner(allowed_commands=["python"])
    result = runner.run(["bash", "-lc", "echo bad"], cwd=tmp_path, name="blocked")
    assert result.returncode == 126
    assert "not allowed" in result.stderr


def test_command_runner_timeout_output_is_text(tmp_path):
    runner = CommandRunner(allowed_commands=["python"], timeout_seconds=0.2)
    result = runner.run(
        ["python", "-c", "import time; print('before timeout', flush=True); time.sleep(1)"],
        cwd=tmp_path,
        name="timeout",
    )
    assert result.returncode == 124
    assert isinstance(result.stdout, str)
    assert "before timeout" in result.stdout
    assert isinstance(result.stderr, str)
