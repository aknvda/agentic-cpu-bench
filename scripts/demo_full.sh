#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RUN_ROOT="${RUN_ROOT:-tmp/full-demo/replay}"
LIVE_RUN_DIR="${LIVE_RUN_DIR:-tmp/full-demo/live}"
OUTPUT_ROOT="${OUTPUT_ROOT:-tmp/agentic-cpu-bench}"
MODEL_ARGS=()

if [[ -n "${MODEL:-}" ]]; then
  MODEL_ARGS=(--model "$MODEL")
fi

case "$RUN_ROOT" in
  tmp/*) ;;
  *) echo "RUN_ROOT must be under tmp/: $RUN_ROOT" >&2; exit 2 ;;
esac

case "$LIVE_RUN_DIR" in
  tmp/*) ;;
  *) echo "LIVE_RUN_DIR must be under tmp/: $LIVE_RUN_DIR" >&2; exit 2 ;;
esac

uv run agentic-cpu-bench validate-task

if [[ "${RUN_LIVE:-0}" == "1" ]]; then
  uv run agentic-cpu-bench codex-run \
    --run-dir "$LIVE_RUN_DIR" \
    --run-id live-demo \
    --side live \
    "${MODEL_ARGS[@]}"
else
  LIVE_WORKSPACE="$LIVE_RUN_DIR/workspace" uv run python - <<'PY'
import os
from pathlib import Path

from agentic_cpu_bench.task_model import load_task
from agentic_cpu_bench.workspace import create_workspace

create_workspace(load_task(Path("tasks/python_cpp_bugfix/manifest.json")), Path(os.environ["LIVE_WORKSPACE"]))
PY
  uv run agentic-cpu-bench codex-live \
    --workspace "$LIVE_RUN_DIR/workspace" \
    "${MODEL_ARGS[@]}"
fi

uv run agentic-cpu-bench dashboard --run-root "$RUN_ROOT" --output "$OUTPUT_ROOT/dashboard.html"
uv run agentic-cpu-bench report --from-artifacts --run-root "$RUN_ROOT" --output "$OUTPUT_ROOT/report.md"

if [[ "${SKIP_K8S:-0}" != "1" ]]; then
  OUT="${CLUSTER_OUT:-tmp/full-demo/cluster}" \
  DASHBOARD="${OUTPUT_ROOT}/k8s-dashboard.html" \
  REPORT="${OUTPUT_ROOT}/k8s-report.md" \
  ./scripts/k8s_demo_replay.sh
fi

echo "local_dashboard=$OUTPUT_ROOT/dashboard.html"
echo "local_report=$OUTPUT_ROOT/report.md"
