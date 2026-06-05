from pathlib import Path

import pytest

from agentic_cpu_bench.k8s import (
    grace_pod_spec,
    grace_replay_job_spec,
    grace_worker_job_spec,
    x86_pod_spec,
    x86_replay_job_spec,
    x86_worker_job_spec,
)


def test_grace_pod_spec_targets_validated_pool_and_toleration():
    spec = grace_pod_spec("smoke-grace", image="registry.k8s.io/pause:3.10")
    assert "namespace: agentic-cpu-bench-demo" in spec
    assert "kubernetes.io/arch: arm64" in spec
    assert "node.kubernetes.io/instance-type: a4x-highgpu-4g" in spec
    assert "cloud.google.com/gke-nodepool: customer-gpu-w0e" in spec
    assert "value: arm64" in spec


def test_x86_pod_spec_targets_customer_cpu_without_toleration():
    spec = x86_pod_spec("smoke-x86", image="registry.k8s.io/pause:3.10")
    assert "namespace: agentic-cpu-bench-demo" in spec
    assert "kubernetes.io/arch: amd64" in spec
    assert "node.kubernetes.io/instance-type: n2d-standard-8" in spec
    assert "cloud.google.com/gke-nodepool: customer-cpu" in spec
    assert "tolerations:" not in spec


def test_cluster_smoke_script_cleans_up_before_and_after_run():
    script = Path("scripts/cluster_smoke.sh").read_text()
    cleanup_delete = 'kubectl delete pods -n "$NS" -l app=agentic-cpu-bench-smoke --ignore-not-found --wait=true'
    namespace_apply = 'kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f -'
    manifest_apply = "uv run python - <<'PY' | kubectl apply -f -"

    assert "cleanup() {" in script
    assert cleanup_delete in script
    assert "--wait=false" not in script

    namespace_pos = script.index(namespace_apply)
    trap_pos = script.index("trap cleanup EXIT")
    pre_cleanup_pos = script.index("\ncleanup\n", trap_pos)
    manifest_apply_pos = script.index(manifest_apply)

    assert namespace_pos < trap_pos < pre_cleanup_pos < manifest_apply_pos


def test_replay_jobs_run_cpu_bench_workload_on_validated_pools():
    x86 = x86_replay_job_spec("agentic-cpu-bench-replay-x86", image="repo/cpu-bench:dev")
    grace = grace_replay_job_spec("agentic-cpu-bench-replay-grace", image="repo/cpu-bench:dev")

    assert "kind: Job" in x86
    assert "agentic-cpu-bench replay --run-dir tmp/cluster/x86 --run-id cluster-x86 --side x86" in x86
    assert "kubernetes.io/arch: amd64" in x86
    assert "cloud.google.com/gke-nodepool: customer-cpu" in x86

    assert "kind: Job" in grace
    assert "agentic-cpu-bench replay --run-dir tmp/cluster/grace --run-id cluster-grace --side grace" in grace
    assert "kubernetes.io/arch: arm64" in grace
    assert "cloud.google.com/gke-nodepool: customer-gpu-w0e" in grace
    assert "value: arm64" in grace


def test_cluster_replay_script_requires_image_and_collects_artifacts():
    script = Path("scripts/cluster_replay.sh").read_text()
    assert 'Set IMAGE to a multi-arch agentic-cpu-bench image' in script
    assert "uv run agentic-cpu-bench k8s-replay-jobs --namespace \"$NS\" --image" in script
    assert "kubectl wait -n \"$NS\" --for=condition=Complete job/agentic-cpu-bench-replay-x86" in script
    assert "kubectl cp \"$NS/$pod:/app/tmp/cluster/$side/artifacts\" \"$OUT/$side/artifacts\"" in script
    assert "uv run agentic-cpu-bench dashboard --from-artifacts" in script


def test_worker_jobs_ship_source_configmap_and_run_inside_namespace():
    x86 = x86_worker_job_spec(
        "agentic-cpu-bench-worker-x86",
        image="python:3.12-slim",
        mode="replay",
        source_config_map="agentic-cpu-bench-source",
    )
    grace = grace_worker_job_spec(
        "agentic-cpu-bench-worker-grace",
        image="python:3.12-slim",
        mode="replay",
        source_config_map="agentic-cpu-bench-source",
    )

    assert "namespace: agentic-cpu-bench-demo" in x86
    assert "app: agentic-cpu-bench-worker" in x86
    assert "automountServiceAccountToken: false" in x86
    assert "name: agentic-cpu-bench-source" in x86
    assert "tar -xzf /input/source.tgz -C /work" in x86
    assert "bubblewrap" in x86
    assert "export AGENTIC_GAUNTLET_STREAM_EVENTS=1" in x86
    assert "agentic-cpu-bench replay --run-dir tmp/k8s-demo/x86 --run-id k8s-replay-x86 --side x86" in x86
    assert "replay_run_exit_code=$run_status" in x86
    assert "__AGENTIC_GAUNTLET_ARTIFACTS_BEGIN_x86__" in x86
    assert "cloud.google.com/gke-nodepool: customer-cpu" in x86

    assert "agentic-cpu-bench replay --run-dir tmp/k8s-demo/grace --run-id k8s-replay-grace --side grace" in grace
    assert "cloud.google.com/gke-nodepool: customer-gpu-w0e" in grace


def test_worker_jobs_accept_explicit_namespace():
    x86 = x86_worker_job_spec(
        "agentic-cpu-bench-worker-x86",
        image="python:3.12-slim",
        mode="replay",
        source_config_map="agentic-cpu-bench-source",
        namespace="anikkulkarni-agentic-demo",
    )
    grace = grace_worker_job_spec(
        "agentic-cpu-bench-worker-grace",
        image="python:3.12-slim",
        mode="replay",
        source_config_map="agentic-cpu-bench-source",
        namespace="anikkulkarni-agentic-demo",
    )

    assert "namespace: anikkulkarni-agentic-demo" in x86
    assert "namespace: anikkulkarni-agentic-demo" in grace


def test_worker_jobs_use_configurable_cpu_request_with_fixed_limit():
    spec = x86_worker_job_spec(
        "agentic-cpu-bench-worker-x86",
        image="python:3.12-slim",
        mode="replay",
        source_config_map="agentic-cpu-bench-source",
        cpu_request="1500m",
    )

    assert 'cpu: "1500m"' in spec
    assert 'cpu: "4"' in spec


def test_live_worker_jobs_require_codex_secret_and_mount_codex_home():
    with pytest.raises(ValueError, match="codex_secret"):
        x86_worker_job_spec(
            "agentic-cpu-bench-worker-x86",
            image="codex-worker:dev",
            mode="live",
            source_config_map="agentic-cpu-bench-source",
        )

    spec = x86_worker_job_spec(
        "agentic-cpu-bench-worker-x86",
        image="codex-worker:dev",
        mode="live",
        source_config_map="agentic-cpu-bench-source",
        codex_secret="codex-home",
        model="gpt-5",
        image_pull_secret="registry-pull-secret",
    )

    assert "agentic-cpu-bench codex-run --run-dir tmp/k8s-demo/x86 --run-id k8s-live-x86 --side x86 --model gpt-5" in spec
    assert "--sandbox danger-full-access" in spec
    assert "imagePullSecrets:" in spec
    assert "name: registry-pull-secret" in spec
    assert "name: CODEX_HOME" in spec
    assert "mountPath: /codex-seed" in spec
    assert "cp /codex-seed/auth.json /codex-home/auth.json" in spec
    assert "install_codex_cli" in spec
    assert "codex-x86_64-unknown-linux-musl" in spec
    assert "run_status=$?" in spec
    assert "live_run_exit_code=$run_status" in spec
    assert "__AGENTIC_GAUNTLET_CODEX_STDERR_BEGIN_x86__" in spec
    assert "secretName: codex-home" in spec
    assert "defaultMode: 0400" in spec


def test_k8s_demo_replay_script_runs_worker_jobs_and_collects_artifacts():
    script = Path("scripts/k8s_demo_replay.sh").read_text()
    assert 'NS="${NS:-agentic-cpu-bench-demo}"' in script
    assert "kubectl create configmap \"$SOURCE_CM\"" in script
    assert 'PYTHON_BIN="${PYTHON_BIN:-python3}"' in script
    assert 'KEEP_DASHBOARD="${KEEP_DASHBOARD:-1}"' in script
    assert 'WORKER_CPU_REQUEST="${WORKER_CPU_REQUEST:-1500m}"' in script
    assert "dashboard_port_open" in script
    assert "start_dashboard" in script
    assert "live_dashboard=http://$LIVE_DASHBOARD_HOST:$LIVE_DASHBOARD_PORT/" in script
    assert "uv run agentic-cpu-bench watch-k8s-dashboard" in script
    assert "uv run agentic-cpu-bench serve-dashboard" in script
    assert "uv run agentic-cpu-bench k8s-worker-jobs" in script
    assert "--namespace \"$NS\"" in script
    assert "--cpu-request \"$WORKER_CPU_REQUEST\"" in script
    assert script.index("start_dashboard") < script.index("uv run agentic-cpu-bench k8s-worker-jobs")
    assert "kubectl wait -n \"$NS\" --for=condition=Complete job/agentic-cpu-bench-worker-x86" in script
    assert "wait \"$WATCH_PID\"" in script
    assert "kubectl logs -n \"$NS\" \"$pod\"" in script
    assert "__AGENTIC_GAUNTLET_ARTIFACTS_BEGIN_{side}__" in script
    assert "COPYFILE_DISABLE=1 tar" in script
    assert "--exclude='._*'" in script
    assert "--exclude='.DS_Store'" in script
    assert "uv run agentic-cpu-bench dashboard --from-artifacts" in script
    assert "kubectl delete configmap \"$SOURCE_CM\" -n \"$NS\" --ignore-not-found" in script
    assert "rm -rf tmp/k8s-demo/source" in script


def test_k8s_demo_live_script_uses_model_and_codex_secret():
    script = Path("scripts/k8s_demo_live.sh").read_text()
    assert "nvcr.io/your-org/your-team/agentic-cpu-bench-codex-worker:latest" in script
    assert 'MODEL="${MODEL:-}"' in script
    assert 'CODEX_SANDBOX="${CODEX_SANDBOX:-danger-full-access}"' in script
    assert 'IMAGE_PULL_SECRET="${IMAGE_PULL_SECRET:-registry-pull-secret}"' in script
    assert 'WORKER_CPU_REQUEST="${WORKER_CPU_REQUEST:-1500m}"' in script
    assert "--codex-secret \"$CODEX_SECRET\"" in script
    assert "--codex-sandbox \"$CODEX_SANDBOX\"" in script
    assert "--namespace \"$NS\"" in script
    assert "--cpu-request \"$WORKER_CPU_REQUEST\"" in script
    assert "worker_args+=(--model \"$MODEL\")" in script
    assert "--image-pull-secret \"$IMAGE_PULL_SECRET\"" in script
    assert "uv run agentic-cpu-bench watch-k8s-dashboard" in script
    assert "uv run agentic-cpu-bench k8s-worker-jobs" in script
    assert "COPYFILE_DISABLE=1 tar" in script
    assert "--exclude='._*'" in script
    assert "--exclude='.DS_Store'" in script


def test_secure_codex_secret_helper_limits_uploaded_files():
    script = Path("scripts/create_codex_secret.sh").read_text()
    assert "--from-file=auth.json=" in script
    assert "INCLUDE_CODEX_CONFIG" in script
    assert "history.jsonl" not in script
    assert "logs_2.sqlite" not in script
    assert "memories_1.sqlite" not in script


def test_live_worker_image_build_script_uses_temporary_authfile():
    script = Path("scripts/build_live_worker_image.sh").read_text()
    assert "authfile=\"$(mktemp)\"" in script
    assert "--authfile \"$authfile\"" in script
    assert "podman manifest push" in script
    assert "nvcr.io/your-org/your-team" in script
    assert "dynamoci.azurecr.io" not in script


def test_nvcr_pull_secret_helper_limits_registry_auth():
    script = Path("scripts/create_nvcr_pull_secret.sh").read_text()
    assert "nvcr.io" in script
    assert "kubernetes.io/dockerconfigjson" in script
    assert "config.json" in script
