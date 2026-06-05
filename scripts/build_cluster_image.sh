#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${IMAGE:-}" ]]; then
  echo "Set IMAGE to the registry tag to build and push, for example: IMAGE=us-docker.pkg.dev/PROJECT/REPO/agentic-cpu-bench:dev" >&2
  exit 2
fi

PLATFORMS="${PLATFORMS:-linux/amd64,linux/arm64}"

docker buildx build \
  --platform "$PLATFORMS" \
  --tag "$IMAGE" \
  --push \
  .
