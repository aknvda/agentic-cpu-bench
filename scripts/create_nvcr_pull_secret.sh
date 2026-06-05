#!/usr/bin/env bash
set -euo pipefail

NS="${NS:-agentic-cpu-bench-demo}"
IMAGE_PULL_SECRET="${IMAGE_PULL_SECRET:-registry-pull-secret}"
AUTH_CONFIG="${AUTH_CONFIG:-$HOME/.docker/config.json}"

tmp_dir="$(mktemp -d)"
cleanup() {
  rm -rf "$tmp_dir"
}
trap cleanup EXIT
chmod 700 "$tmp_dir"

python3 - "$AUTH_CONFIG" "$tmp_dir/config.json" <<'PY'
import json
import sys

source, target = sys.argv[1], sys.argv[2]
with open(source, encoding="utf-8") as handle:
    data = json.load(handle)
auth = data.get("auths", {}).get("nvcr.io", {}).get("auth")
if not auth:
    raise SystemExit("missing nvcr.io auth in Docker config; run 'docker login nvcr.io' first")
with open(target, "w", encoding="utf-8") as handle:
    json.dump({"auths": {"nvcr.io": {"auth": auth}}}, handle)
PY
chmod 600 "$tmp_dir/config.json"

kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic "$IMAGE_PULL_SECRET" \
  -n "$NS" \
  --type=kubernetes.io/dockerconfigjson \
  --from-file=.dockerconfigjson="$tmp_dir/config.json" \
  --dry-run=client \
  -o yaml \
  | kubectl apply -f -

kubectl label secret "$IMAGE_PULL_SECRET" \
  -n "$NS" \
  app.kubernetes.io/part-of=agentic-cpu-bench \
  app.kubernetes.io/component=registry-pull \
  --overwrite >/dev/null

echo "IMAGE_PULL_SECRET=$IMAGE_PULL_SECRET"
echo "namespace=$NS"
echo "registry=nvcr.io"
