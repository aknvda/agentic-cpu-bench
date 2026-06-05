#!/usr/bin/env bash
set -euo pipefail

CODEX_VERSION="${CODEX_VERSION:-0.136.0}"
TAG="${TAG:-$(git rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M%S)}"
AUTH_CONFIG="${AUTH_CONFIG:-$HOME/.docker/config.json}"
REGISTRY_PATH="${REGISTRY_PATH:-nvcr.io/your-org/your-team}"

authfile="$(mktemp)"
cleanup() {
  rm -f "$authfile"
}
trap cleanup EXIT
chmod 600 "$authfile"

python3 - "$AUTH_CONFIG" "$authfile" <<'PY'
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

podman machine start podman-machine-default >/dev/null 2>&1 || true

IMAGE="${IMAGE:-$REGISTRY_PATH/agentic-cpu-bench-codex-worker:$TAG}"
manifest="agentic-cpu-bench-codex-worker:$TAG"

podman manifest rm "$manifest" >/dev/null 2>&1 || true
podman manifest create "$manifest" >/dev/null

for platform in linux/amd64 linux/arm64; do
  podman build \
    --authfile "$authfile" \
    --platform "$platform" \
    --manifest "$manifest" \
    --build-arg "CODEX_VERSION=$CODEX_VERSION" \
    -f Dockerfile.live \
    .
done

podman manifest push \
  --authfile "$authfile" \
  "$manifest" \
  "docker://$IMAGE"

echo "IMAGE=$IMAGE"
echo "CODEX_VERSION=$CODEX_VERSION"
