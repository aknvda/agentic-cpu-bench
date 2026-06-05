#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -eq 0 ]; then
  RUN_ROOT="tmp/local-short"
else
  RUN_ROOT="$1"
fi

case "$RUN_ROOT" in
  tmp/*) ;;
  *)
    echo "run root must be a repo-local tmp/... path: $RUN_ROOT" >&2
    exit 2
    ;;
esac

case "$RUN_ROOT" in
  *..*|tmp|tmp/|*//*|*/.|*/./*)
    echo "unsafe run root: $RUN_ROOT" >&2
    exit 2
    ;;
esac

if [ -L tmp ]; then
  echo "unsafe run root: tmp is a symlink" >&2
  exit 2
fi

current="tmp"
remaining="${RUN_ROOT#tmp/}"
while [ -n "$remaining" ]; do
  case "$remaining" in
    */*)
      component="${remaining%%/*}"
      remaining="${remaining#*/}"
      ;;
    *)
      component="$remaining"
      remaining=""
      ;;
  esac

  current="$current/$component"
  if [ -L "$current" ]; then
    echo "unsafe run root contains symlink component: $current" >&2
    exit 2
  fi

  if [ ! -e "$current" ]; then
    break
  fi
done

rm -rf "$RUN_ROOT"
mkdir -p "$RUN_ROOT"

uv run agentic-cpu-bench replay --run-dir "$RUN_ROOT/grace" --run-id local-grace --side grace
uv run agentic-cpu-bench replay --run-dir "$RUN_ROOT/x86" --run-id local-x86 --side x86
