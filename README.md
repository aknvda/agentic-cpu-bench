# Agentic CPU Bench

Agentic CPU Bench is a Kubernetes-native demo and benchmark harness for
showing how CPU platform choice affects agentic software engineering workloads.

The project currently compares NVIDIA Grace and x86 in the GCP cluster
`your-k8s-cluster`. NVIDIA Vera is the intended future target once Vera CPU is
available in the lab.

Kubernetes namespace:

```text
agentic-cpu-bench-demo
```

## Executive Summary

Modern coding agents do not only call an LLM. They repeatedly inspect files,
apply patches, run tests, compile code, parse failures, and iterate. Those
steps are CPU-heavy and latency-sensitive.

This benchmark demonstrates that workflow as a controlled Grace-vs-x86 race:

1. Two matched Kubernetes workers start together, one on Grace and one on x86.
2. Each worker receives the same broken Python+C++ repository.
3. The harness fixes the task and runs the same validation gates.
4. A live dashboard shows progress, node placement, step timing, and final
   winner.
5. Artifacts and reports are copied back for reproducible review.

Each run produces its own dashboard, report, and JSON artifacts for review.

## Live Mode vs Replay Mode

The project has two modes because a good demo and a defensible benchmark need
different controls.

| Mode | Purpose | What happens |
| --- | --- | --- |
| Live mode | Demonstrate agentic autonomy | Codex runs inside each K8s worker pod, reads the repo, edits files, and attempts to make the task pass. |
| Replay mode | Produce benchmark-grade numbers | The harness applies the known expected patch, then runs the same validation gates deterministically. |

Live mode answers: can the agent fix the bug?

Replay mode answers: once the fix path is known, how fast does each CPU
platform execute the agentic coding workload?

The intended story is simple:

```text
Live mode sells the agentic demo.
Replay mode defends the performance numbers.
```

## What The Worker Actually Does

Each worker runs inside Kubernetes and performs the same task on the same source
tree.

The task fixture is a small Python+C++ repository with intentional bugs:

- Python regex returns only `104` instead of full error codes like `ERR-104`.
- Python mean calculation uses integer division instead of floating-point
  division.
- C++ `scale` incorrectly adds instead of multiplying.

The validation sequence is:

```text
apply-patch
python-tests       uv run pytest -q
cpp-build          make build
cpp-tests          make test
lint               python -m compileall -q src tests
static-analysis    c++ -std=c++17 -Wall -Wextra -Werror -fsyntax-only cpp/calc.cpp
```

In replay mode, `apply-patch` applies `tasks/python_cpp_bugfix/expected.patch`.
In live mode, Codex generates the patch instead, then the same gates run.

## Fair-Start Kubernetes Design

The benchmark path is designed to avoid measuring image pull or scheduler
noise.

Before creating the real workers, the scripts:

1. Resolve the previous Grace and x86 nodes from dashboard state, or use
   explicit `GRACE_NODE` / `X86_NODE`.
2. Start warmup pods on those exact nodes to ensure the image is already
   present.
3. Pin real worker Jobs with `nodeName`.
4. Use `imagePullPolicy: IfNotPresent`.
5. Give both workers the same future `start_at_epoch`.

The selected nodes are printed by the run script and captured in the dashboard
state for auditability.

## Dashboard

The live dashboard is served locally while the K8s demo runs:

```text
http://127.0.0.1:8765/
```

It shows:

- Grace and x86 side-by-side race status.
- Kubernetes pod and node placement.
- Current step and per-step pass/fail status.
- CPU tool-step time.
- Normalized comparison views.
- A filtered CLI transcript with high-signal command events.
- Final report/dashboard artifacts under `tmp/agentic-cpu-bench/`.

## Run The K8s Replay Demo

This is the recommended benchmark-grade path.

```bash
IMAGE=nvcr.io/your-org/your-team/agentic-cpu-bench-codex-worker:<tag> \
IMAGE_PULL_SECRET=registry-pull-secret \
SYNC_START_DELAY_SECONDS=60 \
./scripts/k8s_demo_replay.sh
```

Outputs:

```text
tmp/agentic-cpu-bench/k8s-dashboard.html
tmp/agentic-cpu-bench/k8s-report.md
tmp/agentic-cpu-bench/results.json
tmp/k8s-demo/replay/
```

## Run The K8s Live Demo

Live mode requires a Kubernetes Secret with Codex auth and an image containing
the Codex CLI.

```bash
CODEX_SECRET=codex-auth \
IMAGE=nvcr.io/your-org/your-team/agentic-cpu-bench-codex-worker:<tag> \
IMAGE_PULL_SECRET=registry-pull-secret \
./scripts/k8s_demo_live.sh
```

Secrets are handled explicitly. The helper uploads only the required Codex auth
file by default, not local history, logs, memory databases, or unrelated local
state.

## Build And Push The Worker Image

The worker image is multi-arch and is intended to live under:

```text
nvcr.io/your-org/your-team/*
```

Build/push with Podman:

```bash
IMAGE=nvcr.io/your-org/your-team/agentic-cpu-bench-codex-worker:<tag> \
./scripts/build_live_worker_image.sh
```

## Local Development

Run tests:

```bash
uv run pytest -q
```

CLI help:

```bash
uv run agentic-cpu-bench --help
```

Local replay smoke:

```bash
uv run agentic-cpu-bench replay \
  --run-dir tmp/local-replay \
  --run-id local \
  --side local
```

## Design Docs

- `docs/superpowers/specs/2026-06-03-agentic-cpu-bench-design.md`
- `docs/superpowers/plans/2026-06-03-agentic-cpu-bench-implementation.md`
