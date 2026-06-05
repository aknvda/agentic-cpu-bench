#!/usr/bin/env bash

cleanup_warmup() {
  kubectl delete pods -n "$NS" -l app=agentic-cpu-bench-warmup --ignore-not-found --wait=true
}

resolve_node_from_state() {
  local side="$1"
  "$PYTHON_BIN" - "$LIVE_DASHBOARD_STATE" "$side" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
side = sys.argv[2]
if not path.exists():
    raise SystemExit(1)
state = json.loads(path.read_text(encoding="utf-8"))
for item in state.get("sides", []):
    if item.get("side") == side and item.get("node_name"):
        print(item["node_name"])
        raise SystemExit(0)
raise SystemExit(1)
PY
}

first_ready_node() {
  local arch="$1"
  local instance_type="$2"
  local node_pool="$3"
  kubectl get nodes \
    -l "kubernetes.io/arch=$arch,node.kubernetes.io/instance-type=$instance_type,cloud.google.com/gke-nodepool=$node_pool" \
    -o jsonpath='{.items[?(@.status.conditions[?(@.type=="Ready")].status=="True")].metadata.name}' \
    | awk '{print $1}'
}

resolve_fair_nodes() {
  if [[ -z "${X86_NODE:-}" ]]; then
    X86_NODE="$(resolve_node_from_state x86 2>/dev/null || true)"
  fi
  if [[ -z "${GRACE_NODE:-}" ]]; then
    GRACE_NODE="$(resolve_node_from_state grace 2>/dev/null || true)"
  fi
  if [[ -z "${X86_NODE:-}" ]]; then
    X86_NODE="$(first_ready_node amd64 n2d-standard-8 customer-cpu)"
  fi
  if [[ -z "${GRACE_NODE:-}" ]]; then
    GRACE_NODE="$(first_ready_node arm64 a4x-highgpu-4g customer-gpu-w0e)"
  fi
  if [[ -z "${X86_NODE:-}" || -z "${GRACE_NODE:-}" ]]; then
    echo "Could not resolve fair-start nodes: X86_NODE=${X86_NODE:-} GRACE_NODE=${GRACE_NODE:-}" >&2
    exit 2
  fi
}

warm_image_on_node() {
  local side="$1"
  local node="$2"
  local arch="$3"
  local pod="agentic-cpu-bench-warmup-$side"
  kubectl delete pod "$pod" -n "$NS" --ignore-not-found --wait=true
  "$PYTHON_BIN" - "$NS" "$pod" "$side" "$node" "$arch" "$IMAGE" "${IMAGE_PULL_SECRET:-}" <<'PY' | kubectl apply -f -
import json
import sys

namespace, pod, side, node, arch, image, pull_secret = sys.argv[1:]
spec = {
    "apiVersion": "v1",
    "kind": "Pod",
    "metadata": {
        "name": pod,
        "namespace": namespace,
        "labels": {"app": "agentic-cpu-bench-warmup", "side": side},
    },
    "spec": {
        "restartPolicy": "Never",
        "nodeName": node,
        "nodeSelector": {"kubernetes.io/arch": arch},
        "containers": [
            {
                "name": "warmup",
                "image": image,
                "imagePullPolicy": "IfNotPresent",
                "command": ["/bin/sh", "-lc", "echo image-warmed; sleep 30"],
                "resources": {
                    "requests": {"cpu": "50m", "memory": "64Mi"},
                    "limits": {"cpu": "100m", "memory": "128Mi"},
                },
            }
        ],
    },
}
if pull_secret:
    spec["spec"]["imagePullSecrets"] = [{"name": pull_secret}]
if side == "grace":
    spec["spec"]["tolerations"] = [
        {
            "key": "kubernetes.io/arch",
            "operator": "Equal",
            "value": "arm64",
            "effect": "NoSchedule",
        }
    ]
print(json.dumps(spec))
PY
  kubectl wait -n "$NS" --for=condition=Ready "pod/$pod" --timeout=300s
}

start_epoch() {
  "$PYTHON_BIN" - "$SYNC_START_DELAY_SECONDS" <<'PY'
import sys
import time
print(f"{time.time() + float(sys.argv[1]):.3f}")
PY
}

prepare_fair_start() {
  START_AT_EPOCH=""
  if [[ "${FAIR_START:-1}" != "1" ]]; then
    return
  fi
  resolve_fair_nodes
  echo "fair_start_x86_node=$X86_NODE"
  echo "fair_start_grace_node=$GRACE_NODE"
  warm_image_on_node x86 "$X86_NODE" amd64
  warm_image_on_node grace "$GRACE_NODE" arm64
  START_AT_EPOCH="$(start_epoch)"
  echo "fair_start_epoch=$START_AT_EPOCH"
}
