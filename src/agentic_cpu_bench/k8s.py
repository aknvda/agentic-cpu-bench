from __future__ import annotations

import shlex


NAMESPACE = "agentic-cpu-bench-demo"


def x86_pod_spec(name: str, image: str) -> str:
    return _pod_spec(
        name=name,
        image=image,
        arch="amd64",
        instance_type="n2d-standard-8",
        node_pool="customer-cpu",
    )


def grace_pod_spec(name: str, image: str) -> str:
    return _pod_spec(
        name=name,
        image=image,
        arch="arm64",
        instance_type="a4x-highgpu-4g",
        node_pool="customer-gpu-w0e",
        include_arch_toleration=True,
    )


def x86_replay_job_spec(name: str, image: str) -> str:
    return _replay_job_spec(
        name=name,
        image=image,
        side="x86",
        arch="amd64",
        instance_type="n2d-standard-8",
        node_pool="customer-cpu",
    )


def grace_replay_job_spec(name: str, image: str) -> str:
    return _replay_job_spec(
        name=name,
        image=image,
        side="grace",
        arch="arm64",
        instance_type="a4x-highgpu-4g",
        node_pool="customer-gpu-w0e",
        include_arch_toleration=True,
    )


def x86_worker_job_spec(
    name: str,
    image: str,
    *,
    mode: str,
    source_config_map: str,
    codex_secret: str | None = None,
    model: str | None = None,
    codex_version: str = "0.136.0",
    image_pull_secret: str | None = None,
    node_name: str | None = None,
    start_at_epoch: float | None = None,
) -> str:
    return _worker_job_spec(
        name=name,
        image=image,
        side="x86",
        arch="amd64",
        instance_type="n2d-standard-8",
        node_pool="customer-cpu",
        mode=mode,
        source_config_map=source_config_map,
        codex_secret=codex_secret,
        model=model,
        codex_version=codex_version,
        image_pull_secret=image_pull_secret,
        node_name=node_name,
        start_at_epoch=start_at_epoch,
    )


def grace_worker_job_spec(
    name: str,
    image: str,
    *,
    mode: str,
    source_config_map: str,
    codex_secret: str | None = None,
    model: str | None = None,
    codex_version: str = "0.136.0",
    image_pull_secret: str | None = None,
    node_name: str | None = None,
    start_at_epoch: float | None = None,
) -> str:
    return _worker_job_spec(
        name=name,
        image=image,
        side="grace",
        arch="arm64",
        instance_type="a4x-highgpu-4g",
        node_pool="customer-gpu-w0e",
        include_arch_toleration=True,
        mode=mode,
        source_config_map=source_config_map,
        codex_secret=codex_secret,
        model=model,
        codex_version=codex_version,
        image_pull_secret=image_pull_secret,
        node_name=node_name,
        start_at_epoch=start_at_epoch,
    )


def _pod_spec(
    *,
    name: str,
    image: str,
    arch: str,
    instance_type: str,
    node_pool: str,
    include_arch_toleration: bool = False,
) -> str:
    lines = [
        "apiVersion: v1",
        "kind: Pod",
        "metadata:",
        f"  name: {name}",
        f"  namespace: {NAMESPACE}",
        "  labels:",
        "    app: agentic-cpu-bench-smoke",
        "spec:",
        "  restartPolicy: Never",
        "  nodeSelector:",
        f"    kubernetes.io/arch: {arch}",
        f"    node.kubernetes.io/instance-type: {instance_type}",
        f"    cloud.google.com/gke-nodepool: {node_pool}",
    ]
    if include_arch_toleration:
        lines.extend(
            [
                "  tolerations:",
                "    - key: kubernetes.io/arch",
                "      operator: Equal",
                f"      value: {arch}",
                "      effect: NoSchedule",
            ]
        )
    lines.extend(
        [
            "  containers:",
            "    - name: smoke",
            f"      image: {image}",
            "      resources:",
            "        requests:",
            "          cpu: 100m",
            "          memory: 64Mi",
            "        limits:",
            "          cpu: 100m",
            "          memory: 64Mi",
        ]
    )
    return "\n".join(lines) + "\n"


def _selector_lines(arch: str, instance_type: str, node_pool: str, indent: str) -> list[str]:
    return [
        f"{indent}nodeSelector:",
        f"{indent}  kubernetes.io/arch: {arch}",
        f"{indent}  node.kubernetes.io/instance-type: {instance_type}",
        f"{indent}  cloud.google.com/gke-nodepool: {node_pool}",
    ]


def _toleration_lines(arch: str, indent: str) -> list[str]:
    return [
        f"{indent}tolerations:",
        f"{indent}  - key: kubernetes.io/arch",
        f"{indent}    operator: Equal",
        f"{indent}    value: {arch}",
        f"{indent}    effect: NoSchedule",
    ]


def _replay_job_spec(
    *,
    name: str,
    image: str,
    side: str,
    arch: str,
    instance_type: str,
    node_pool: str,
    include_arch_toleration: bool = False,
) -> str:
    run_dir = f"tmp/cluster/{side}"
    command = (
        "set -euo pipefail\n"
        f"agentic-cpu-bench replay --run-dir {run_dir} --run-id cluster-{side} --side {side}\n"
        f"cat {run_dir}/artifacts/events.jsonl\n"
    )
    lines = [
        "apiVersion: batch/v1",
        "kind: Job",
        "metadata:",
        f"  name: {name}",
        f"  namespace: {NAMESPACE}",
        "  labels:",
        "    app: agentic-cpu-bench-replay",
        f"    side: {side}",
        "spec:",
        "  backoffLimit: 0",
        "  ttlSecondsAfterFinished: 3600",
        "  template:",
        "    metadata:",
        "      labels:",
        "        app: agentic-cpu-bench-replay",
        f"        side: {side}",
        "    spec:",
        "      restartPolicy: Never",
    ]
    lines.extend(_selector_lines(arch, instance_type, node_pool, "      "))
    if include_arch_toleration:
        lines.extend(_toleration_lines(arch, "      "))
    lines.extend(
        [
            "      containers:",
            "        - name: replay",
            f"          image: {image}",
            "          imagePullPolicy: IfNotPresent",
            "          command:",
            "            - /bin/sh",
            "            - -lc",
            "          args:",
            "            - |",
        ]
    )
    lines.extend(f"              {line}" for line in command.rstrip().splitlines())
    lines.extend(
        [
            "          resources:",
            "            requests:",
            "              cpu: \"2\"",
            "              memory: 2Gi",
            "            limits:",
            "              cpu: \"4\"",
            "              memory: 4Gi",
        ]
    )
    return "\n".join(lines) + "\n"


def _codex_bootstrap_script(codex_version: str) -> str:
    version = shlex.quote(codex_version)
    return (
        "install_codex_cli() {\n"
        "  if command -v codex >/dev/null 2>&1; then codex --version; return; fi\n"
        "  arch=\"$(uname -m)\"\n"
        "  case \"$arch\" in\n"
        "    x86_64) codex_target=\"codex-x86_64-unknown-linux-musl\" ;;\n"
        "    aarch64|arm64) codex_target=\"codex-aarch64-unknown-linux-musl\" ;;\n"
        "    *) echo \"unsupported architecture for Codex: $arch\" >&2; return 2 ;;\n"
        "  esac\n"
        "  tmp_dir=\"$(mktemp -d)\"\n"
        f"  curl -fsSL \"https://github.com/openai/codex/releases/download/rust-v{version}/${{codex_target}}.tar.gz\" -o \"$tmp_dir/codex.tar.gz\"\n"
        "  tar -xzf \"$tmp_dir/codex.tar.gz\" -C \"$tmp_dir\"\n"
        "  install -m 0755 \"$tmp_dir/$codex_target\" /usr/local/bin/codex\n"
        "  rm -rf \"$tmp_dir\"\n"
        "  codex --version\n"
        "}\n"
        "install_codex_cli\n"
    )


def _start_gate_script(start_at_epoch: float | None) -> str:
    if start_at_epoch is None:
        return ""
    return (
        "python - <<'PY'\n"
        "import time\n"
        f"target = {float(start_at_epoch)!r}\n"
        "now = time.time()\n"
        "if now < target:\n"
        "    print(f'waiting_for_synchronized_start target={target:.3f} delay={target - now:.3f}s', flush=True)\n"
        "while time.time() < target:\n"
        "    time.sleep(0.05)\n"
        "print(f'synchronized_start ts={time.time():.3f}', flush=True)\n"
        "PY\n"
    )


def _worker_script(
    side: str,
    mode: str,
    model: str | None,
    codex_version: str,
    start_at_epoch: float | None,
) -> str:
    run_dir = f"tmp/k8s-demo/{side}"
    emit_artifacts = (
        f"echo __AGENTIC_GAUNTLET_ARTIFACTS_BEGIN_{side}__\n"
        f"tar -C {run_dir}/artifacts -czf - . | base64 | tr -d '\\n'\n"
        "echo\n"
        f"echo __AGENTIC_GAUNTLET_ARTIFACTS_END_{side}__\n"
    )
    common = (
        "set -euo pipefail\n"
        "export DEBIAN_FRONTEND=noninteractive\n"
        "export AGENTIC_GAUNTLET_STREAM_EVENTS=1\n"
        "apt-get update\n"
        "apt-get install -y --no-install-recommends build-essential ca-certificates curl git make ripgrep tar\n"
        "python -m pip install --no-cache-dir pytest uv\n"
        "mkdir -p /work\n"
        "tar -xzf /input/source.tgz -C /work\n"
        "cd /work/agentic-cpu-bench\n"
        "python -m pip install --no-cache-dir .\n"
    )
    if mode == "replay":
        replay_command = f"agentic-cpu-bench replay --run-dir {run_dir} --run-id k8s-replay-{side} --side {side}\n"
        return (
            common
            + _start_gate_script(start_at_epoch)
            + "set +e\n"
            + replay_command
            + "run_status=$?\n"
            + "set -e\n"
            + "echo replay_run_exit_code=$run_status\n"
            + emit_artifacts
            + "exit 0\n"
        )
    if mode == "live":
        model_args = f" --model {shlex.quote(model)}" if model else ""
        live_command = (
            f"agentic-cpu-bench codex-run --run-dir {run_dir} "
            f"--run-id k8s-live-{side} --side {side}{model_args}\n"
        )
        return (
            common
            + "mkdir -p /codex-home\n"
            + "cp /codex-seed/auth.json /codex-home/auth.json\n"
            + "if [ -f /codex-seed/config.toml ]; then cp /codex-seed/config.toml /codex-home/config.toml; fi\n"
            + "chmod 700 /codex-home\n"
            + "chmod 600 /codex-home/*\n"
            + _codex_bootstrap_script(codex_version)
            + _start_gate_script(start_at_epoch)
            + "set +e\n"
            + live_command
            + "run_status=$?\n"
            + "set -e\n"
            + f"if [ -f {run_dir}/artifacts/codex.stderr.log ]; then\n"
            + f"  echo __AGENTIC_GAUNTLET_CODEX_STDERR_BEGIN_{side}__\n"
            + f"  tail -200 {run_dir}/artifacts/codex.stderr.log\n"
            + f"  echo __AGENTIC_GAUNTLET_CODEX_STDERR_END_{side}__\n"
            + "fi\n"
            + "echo live_run_exit_code=$run_status\n"
            + emit_artifacts
            + "exit 0\n"
        )
    raise ValueError(f"unsupported worker mode: {mode}")


def _worker_job_spec(
    *,
    name: str,
    image: str,
    side: str,
    arch: str,
    instance_type: str,
    node_pool: str,
    mode: str,
    source_config_map: str,
    codex_secret: str | None = None,
    model: str | None = None,
    codex_version: str = "0.136.0",
    image_pull_secret: str | None = None,
    node_name: str | None = None,
    start_at_epoch: float | None = None,
    include_arch_toleration: bool = False,
) -> str:
    if mode not in {"replay", "live"}:
        raise ValueError(f"unsupported worker mode: {mode}")
    if mode == "live" and not codex_secret:
        raise ValueError("live worker jobs require codex_secret")

    lines = [
        "apiVersion: batch/v1",
        "kind: Job",
        "metadata:",
        f"  name: {name}",
        f"  namespace: {NAMESPACE}",
        "  labels:",
        "    app: agentic-cpu-bench-worker",
        f"    mode: {mode}",
        f"    side: {side}",
        "spec:",
        "  backoffLimit: 0",
        "  ttlSecondsAfterFinished: 3600",
        "  template:",
        "    metadata:",
        "      labels:",
        "        app: agentic-cpu-bench-worker",
        f"        mode: {mode}",
        f"        side: {side}",
        "    spec:",
        "      restartPolicy: Never",
    ]
    if image_pull_secret:
        lines.extend(
            [
                "      imagePullSecrets:",
                f"        - name: {image_pull_secret}",
            ]
        )
    if node_name:
        lines.append(f"      nodeName: {node_name}")
    lines.extend(_selector_lines(arch, instance_type, node_pool, "      "))
    if include_arch_toleration:
        lines.extend(_toleration_lines(arch, "      "))
    lines.extend(
        [
            "      containers:",
            "        - name: worker",
            f"          image: {image}",
            "          imagePullPolicy: IfNotPresent",
            "          command:",
            "            - /bin/sh",
            "            - -lc",
            "          args:",
            "            - |",
        ]
    )
    lines.extend(
        f"              {line}"
        for line in _worker_script(side, mode, model, codex_version, start_at_epoch).rstrip().splitlines()
    )
    if mode == "live":
        lines.extend(
            [
                "          env:",
                "            - name: CODEX_HOME",
                "              value: /codex-home",
            ]
        )
    lines.extend(
        [
            "          volumeMounts:",
            "            - name: source",
            "              mountPath: /input",
            "              readOnly: true",
        ]
    )
    if mode == "live":
        lines.extend(
            [
                "            - name: codex-seed",
                "              mountPath: /codex-seed",
                "              readOnly: true",
            ]
        )
    lines.extend(
        [
            "          resources:",
            "            requests:",
            "              cpu: \"2\"",
            "              memory: 2Gi",
            "            limits:",
            "              cpu: \"4\"",
            "              memory: 4Gi",
            "      volumes:",
            "        - name: source",
            "          configMap:",
            f"            name: {source_config_map}",
        ]
    )
    if mode == "live":
        lines.extend(
            [
                "        - name: codex-seed",
                "          secret:",
                f"            secretName: {codex_secret}",
                "            defaultMode: 0400",
            ]
        )
    return "\n".join(lines) + "\n"
