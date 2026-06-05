#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

NS="${NS:-agentic-cpu-bench-demo}"
IMAGE="${IMAGE:-python:3.12-slim}"
IMAGE_PULL_SECRET="${IMAGE_PULL_SECRET:-}"
FAIR_START="${FAIR_START:-1}"
SYNC_START_DELAY_SECONDS="${SYNC_START_DELAY_SECONDS:-90}"
X86_NODE="${X86_NODE:-}"
GRACE_NODE="${GRACE_NODE:-}"
START_AT_EPOCH=""
SOURCE_CM="${SOURCE_CM:-agentic-cpu-bench-source}"
OUT="${OUT:-tmp/k8s-demo/replay}"
DASHBOARD="${DASHBOARD:-tmp/agentic-cpu-bench/k8s-dashboard.html}"
REPORT="${REPORT:-tmp/agentic-cpu-bench/k8s-report.md}"
TIMEOUT="${TIMEOUT:-900s}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
WORKER_CPU_REQUEST="${WORKER_CPU_REQUEST:-1500m}"
LIVE_DASHBOARD_STATE="${LIVE_DASHBOARD_STATE:-tmp/agentic-cpu-bench/k8s-live-state.json}"
LIVE_DASHBOARD_HOST="${LIVE_DASHBOARD_HOST:-127.0.0.1}"
LIVE_DASHBOARD_PORT="${LIVE_DASHBOARD_PORT:-8765}"
LIVE_DASHBOARD_TIMEOUT="${LIVE_DASHBOARD_TIMEOUT:-1200}"
KEEP_DASHBOARD="${KEEP_DASHBOARD:-1}"
SERVER_PID=""
WATCH_PID=""

source "$ROOT/scripts/k8s_fair_start_lib.sh"

case "$OUT" in
  tmp/*) ;;
  *) echo "OUT must be under tmp/: $OUT" >&2; exit 2 ;;
esac

cleanup_jobs() {
  kubectl delete jobs -n "$NS" -l app=agentic-cpu-bench-worker --ignore-not-found --wait=true
}

cleanup_dashboard() {
  if [[ -n "${WATCH_PID:-}" ]]; then
    kill "$WATCH_PID" 2>/dev/null || true
    wait "$WATCH_PID" 2>/dev/null || true
  fi
  if [[ "${KEEP_DASHBOARD:-0}" != "1" && -n "${SERVER_PID:-}" ]]; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}

trap 'cleanup_dashboard; cleanup_warmup' EXIT

dashboard_port_open() {
  "$PYTHON_BIN" - "$LIVE_DASHBOARD_HOST" "$LIVE_DASHBOARD_PORT" <<'PY'
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])
with socket.socket() as sock:
    sock.settimeout(0.5)
    raise SystemExit(0 if sock.connect_ex((host, port)) == 0 else 1)
PY
}

start_dashboard() {
  mkdir -p "$(dirname "$LIVE_DASHBOARD_STATE")"
  rm -f "$LIVE_DASHBOARD_STATE"
  uv run agentic-cpu-bench watch-k8s-dashboard \
    --state "$LIVE_DASHBOARD_STATE" \
    --namespace "$NS" \
    --mode replay \
    --interval-seconds 1 \
    --timeout-seconds "$LIVE_DASHBOARD_TIMEOUT" &
  WATCH_PID="$!"
  if dashboard_port_open; then
    echo "live_dashboard=http://$LIVE_DASHBOARD_HOST:$LIVE_DASHBOARD_PORT/"
    return
  fi
  uv run agentic-cpu-bench serve-dashboard \
    --state "$LIVE_DASHBOARD_STATE" \
    --host "$LIVE_DASHBOARD_HOST" \
    --port "$LIVE_DASHBOARD_PORT" &
  SERVER_PID="$!"
  sleep 1
  echo "live_dashboard=http://$LIVE_DASHBOARD_HOST:$LIVE_DASHBOARD_PORT/"
}

extract_side() {
  local side="$1"
  local job="agentic-cpu-bench-worker-$side"
  local pod
  pod="$(kubectl get pods -n "$NS" -l "job-name=$job" -o jsonpath='{.items[0].metadata.name}')"
  mkdir -p "$OUT/$side/artifacts"
  kubectl logs -n "$NS" "$pod" > "$OUT/$side/pod.log"
  "$PYTHON_BIN" - "$OUT/$side/pod.log" "$OUT/$side/artifacts.tgz" "$side" <<'PY'
import base64
import sys
from pathlib import Path

log_path = Path(sys.argv[1])
tar_path = Path(sys.argv[2])
side = sys.argv[3]
start = f"__AGENTIC_GAUNTLET_ARTIFACTS_BEGIN_{side}__"
end = f"__AGENTIC_GAUNTLET_ARTIFACTS_END_{side}__"
lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
try:
    start_index = lines.index(start)
    end_index = lines.index(end)
except ValueError as exc:
    raise SystemExit(f"artifact markers missing in {log_path}") from exc
payload = "".join(lines[start_index + 1 : end_index]).strip()
tar_path.write_bytes(base64.b64decode(payload))
PY
  tar -xzf "$OUT/$side/artifacts.tgz" -C "$OUT/$side/artifacts"
}

kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f -

mkdir -p tmp/k8s-demo/source
COPYFILE_DISABLE=1 tar \
  --exclude=.git \
  --exclude=.venv \
  --exclude=tmp \
  --exclude=.pytest_cache \
  --exclude='__pycache__' \
  --exclude='._*' \
  --exclude='.DS_Store' \
  -czf tmp/k8s-demo/source/source.tgz \
  -C "$ROOT/.." \
  "$(basename "$ROOT")"

kubectl delete configmap "$SOURCE_CM" -n "$NS" --ignore-not-found
kubectl create configmap "$SOURCE_CM" -n "$NS" --from-file=source.tgz=tmp/k8s-demo/source/source.tgz

cleanup_jobs
prepare_fair_start
start_dashboard

worker_args=(
  uv run agentic-cpu-bench k8s-worker-jobs
  --namespace "$NS" \
  --cpu-request "$WORKER_CPU_REQUEST" \
  --mode replay \
  --image "$IMAGE" \
  --source-config-map "$SOURCE_CM"
)
if [[ -n "$IMAGE_PULL_SECRET" ]]; then
  worker_args+=(--image-pull-secret "$IMAGE_PULL_SECRET")
fi
if [[ "$FAIR_START" == "1" ]]; then
  worker_args+=(--x86-node "$X86_NODE" --grace-node "$GRACE_NODE" --start-at-epoch "$START_AT_EPOCH")
fi
"${worker_args[@]}" | kubectl apply -f -

kubectl wait -n "$NS" --for=condition=Complete job/agentic-cpu-bench-worker-x86 --timeout="$TIMEOUT"
kubectl wait -n "$NS" --for=condition=Complete job/agentic-cpu-bench-worker-grace --timeout="$TIMEOUT"
kubectl get pods -n "$NS" -l app=agentic-cpu-bench-worker -o wide
wait "$WATCH_PID" || true
WATCH_PID=""

rm -rf "$OUT"
mkdir -p "$OUT"
extract_side x86
extract_side grace

uv run agentic-cpu-bench dashboard --from-artifacts --run-root "$OUT" --output "$DASHBOARD"
uv run agentic-cpu-bench report --from-artifacts --run-root "$OUT" --output "$REPORT"

if [[ "${KEEP_JOBS:-0}" != "1" ]]; then
  cleanup_jobs
fi
if [[ "${KEEP_SOURCE:-0}" != "1" ]]; then
  kubectl delete configmap "$SOURCE_CM" -n "$NS" --ignore-not-found
  rm -rf tmp/k8s-demo/source
fi

echo "namespace=$NS"
echo "live_dashboard_state=$LIVE_DASHBOARD_STATE"
echo "k8s_artifacts=$OUT"
echo "k8s_dashboard=$DASHBOARD"
echo "k8s_report=$REPORT"
echo "fair_start=$FAIR_START"
if [[ "$FAIR_START" == "1" ]]; then
  echo "x86_node=$X86_NODE"
  echo "grace_node=$GRACE_NODE"
  echo "start_at_epoch=$START_AT_EPOCH"
fi
