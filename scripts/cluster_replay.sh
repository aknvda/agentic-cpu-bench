#!/usr/bin/env bash
set -euo pipefail

NS="${NS:-agentic-cpu-bench-demo}"
OUT="${OUT:-tmp/cluster-replay}"
DASHBOARD="${DASHBOARD:-tmp/agentic-cpu-bench/cluster-dashboard.html}"
REPORT="${REPORT:-tmp/agentic-cpu-bench/cluster-report.md}"
TIMEOUT="${TIMEOUT:-600s}"

if [[ -z "${IMAGE:-}" ]]; then
  echo "Set IMAGE to a multi-arch agentic-cpu-bench image before running cluster replay." >&2
  exit 2
fi

case "$OUT" in
  tmp/*) ;;
  *) echo "OUT must be under tmp/: $OUT" >&2; exit 2 ;;
esac

cleanup_jobs() {
  kubectl delete jobs -n "$NS" -l app=agentic-cpu-bench-replay --ignore-not-found --wait=true
}

copy_side() {
  local side="$1"
  local job="agentic-cpu-bench-replay-$side"
  local pod
  pod="$(kubectl get pods -n "$NS" -l "job-name=$job" -o jsonpath='{.items[0].metadata.name}')"
  mkdir -p "$OUT/$side"
  kubectl cp "$NS/$pod:/app/tmp/cluster/$side/artifacts" "$OUT/$side/artifacts"
}

kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f -
cleanup_jobs

uv run agentic-cpu-bench k8s-replay-jobs --image "$IMAGE" | kubectl apply -f -

kubectl wait -n "$NS" --for=condition=Complete job/agentic-cpu-bench-replay-x86 --timeout="$TIMEOUT"
kubectl wait -n "$NS" --for=condition=Complete job/agentic-cpu-bench-replay-grace --timeout="$TIMEOUT"
kubectl get pods -n "$NS" -l app=agentic-cpu-bench-replay -o wide

rm -rf "$OUT"
mkdir -p "$OUT"
copy_side x86
copy_side grace

uv run agentic-cpu-bench dashboard --from-artifacts --run-root "$OUT" --output "$DASHBOARD"
uv run agentic-cpu-bench report --from-artifacts --run-root "$OUT" --output "$REPORT"

if [[ "${KEEP_JOBS:-0}" != "1" ]]; then
  cleanup_jobs
fi

echo "cluster_artifacts=$OUT"
echo "cluster_dashboard=$DASHBOARD"
echo "cluster_report=$REPORT"
