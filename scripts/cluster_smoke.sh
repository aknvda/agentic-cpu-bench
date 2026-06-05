#!/usr/bin/env bash
set -euo pipefail

NS="agentic-cpu-bench-demo"
IMAGE="registry.k8s.io/pause:3.10"

cleanup() {
  kubectl delete pods -n "$NS" -l app=agentic-cpu-bench-smoke --ignore-not-found --wait=true
}

kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f -

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

cleanup

uv run python - <<'PY' | kubectl apply -f -
from agentic_cpu_bench.k8s import grace_pod_spec, x86_pod_spec
print(x86_pod_spec("agentic-cpu-bench-smoke-x86", "registry.k8s.io/pause:3.10"))
print("---")
print(grace_pod_spec("agentic-cpu-bench-smoke-grace", "registry.k8s.io/pause:3.10"))
PY

kubectl wait -n "$NS" --for=condition=Ready pod/agentic-cpu-bench-smoke-x86 --timeout=60s
kubectl wait -n "$NS" --for=condition=Ready pod/agentic-cpu-bench-smoke-grace --timeout=60s
kubectl get pods -n "$NS" -l app=agentic-cpu-bench-smoke -o wide
