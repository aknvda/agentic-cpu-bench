#!/usr/bin/env bash
set -euo pipefail

NS="${NS:-agentic-cpu-bench-demo}"
CODEX_HOME_SRC="${CODEX_HOME:-$HOME/.codex}"
CODEX_SECRET="${CODEX_SECRET:-codex-auth}"
INCLUDE_CODEX_CONFIG="${INCLUDE_CODEX_CONFIG:-0}"

if [[ ! -f "$CODEX_HOME_SRC/auth.json" ]]; then
  echo "Missing $CODEX_HOME_SRC/auth.json. Run 'codex login' locally first." >&2
  exit 2
fi

tmp_dir="$(mktemp -d)"
cleanup() {
  rm -rf "$tmp_dir"
}
trap cleanup EXIT
chmod 700 "$tmp_dir"

install -m 600 "$CODEX_HOME_SRC/auth.json" "$tmp_dir/auth.json"
if [[ "$INCLUDE_CODEX_CONFIG" == "1" && -f "$CODEX_HOME_SRC/config.toml" ]]; then
  install -m 600 "$CODEX_HOME_SRC/config.toml" "$tmp_dir/config.toml"
fi

kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f -
secret_args=(
  kubectl create secret generic "$CODEX_SECRET"
  -n "$NS"
  --from-file=auth.json="$tmp_dir/auth.json"
)
if [[ "$INCLUDE_CODEX_CONFIG" == "1" && -f "$tmp_dir/config.toml" ]]; then
  secret_args+=(--from-file=config.toml="$tmp_dir/config.toml")
fi

"${secret_args[@]}" --dry-run=client -o yaml \
  | kubectl apply -f -

kubectl label secret "$CODEX_SECRET" \
  -n "$NS" \
  app.kubernetes.io/part-of=agentic-cpu-bench \
  app.kubernetes.io/component=codex-auth \
  --overwrite >/dev/null

echo "CODEX_SECRET=$CODEX_SECRET"
echo "namespace=$NS"
echo "included_files=auth.json$([[ "$INCLUDE_CODEX_CONFIG" == "1" && -f "$CODEX_HOME_SRC/config.toml" ]] && echo ',config.toml' || true)"
