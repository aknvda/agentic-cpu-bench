# Agentic CPU Bench Design

**Date:** 2026-06-03
**Status:** Approved design, implementation in progress
**Primary audience:** AI labs, cloud infrastructure buyers, and enterprise agent platform teams
**Current runnable targets:** Grace and x86 on `your-k8s-cluster`
**Namespace:** `agentic-cpu-bench-demo`
**Future target:** NVIDIA Vera

## 1. Goal

Build a Race First demo that makes Vera's agentic-AI CPU value obvious:

1. A coding agent finishes the same Python+C++ bug-fix workload faster.
2. A fleet can run more coding agents concurrently before hitting latency limits.
3. Expensive model-serving GPUs spend less time waiting on CPU-side tool work.

The live demo compares Grace and x86 on `your-k8s-cluster` today. All Kubernetes resources live in `agentic-cpu-bench-demo`. The workload is designed so the same shape maps cleanly to Vera when available.

## 2. Source Rationale

The Vera deck positions Vera as the CPU for agentic AI. The strongest claims map to workloads with many short, sequential CPU-bound steps:

- sandbox execution;
- tool calls;
- code and test execution;
- Python scripting;
- compilation;
- code analysis;
- regex/log parsing;
- SQLite or data-query work;
- startup and in-memory load speed;
- loaded throughput across many concurrent sandboxes.

The selected use-case is an **Agentic CPU Bench** because it naturally exercises those paths and is legible to all three target audiences.

## 3. Selected Product Shape

The demo is a **guided-autonomous live coding race plus benchmark-grade trace replay**.

Live mode:
- Codex CLI-style coding agents run the same Python+C++ bug-fix tasks.
- The agent is autonomous within a constrained worker pod: inspect files, edit files, run allowed commands, and iterate until tests pass or timeout.
- Grace and x86 runs are shown side by side in a Race First dashboard.

Replay mode:
- The harness records the live agent's tool sequence.
- It replays deterministic CPU-relevant steps without LLM decision variance.
- Replay results are used for benchmark-grade Grace-vs-x86 measurement.

The live mode sells the story. The replay mode defends the numbers.

Default presets:

- **Short race:** one compact Python+C++ bug-fix task designed to complete in 2-3 minutes.
- **Technical race:** a larger task set designed to complete in 5-7 minutes.
- **Concurrency sweep:** replay-mode workers scale until P95 completion time exceeds 2x the single-worker baseline or any worker hits timeout.

## 4. Task Suite

The task suite is a hybrid Python+C++ repository with injected bug-fix tasks. Each task has:

- a broken starting state;
- deterministic setup and reset scripts;
- visible success commands;
- optional hidden validation commands;
- a timeout;
- metadata describing CPU-heavy paths exercised.

Initial task category:

- bug-fix tasks only.

Language/toolchain coverage:

- Python application logic and tests;
- C++ library code and tests;
- Python/C++ integration failures;
- lint/static analysis where useful;
- logs or text fixtures for regex parsing;
- optional SQLite fixtures where useful.

Each task must prove three states:

1. Broken tests fail before the fix.
2. The expected patch passes after the fix.
3. Reset returns the repo to the broken state.

## 5. Components

### Task Suite

Owns versioned task definitions, repo fixtures, setup/reset scripts, expected success criteria, and metadata tags.

### Agent Worker

Runs the guided autonomous Codex-style agent. It owns:

- repo checkout and reset;
- prompt and task injection;
- command allowlist enforcement;
- timeout enforcement;
- artifact capture;
- event emission;
- final pass/fail status.

### Race Orchestrator

Launches matched Grace and x86 runs in `your-k8s-cluster` under `agentic-cpu-bench-demo`. It owns:

- short and technical race presets;
- equal-vCPU profile;
- equal-physical-core estimate profile;
- simultaneous start;
- run metadata collection;
- dashboard event routing.

### Trace Recorder and Replayer

Records live agent actions and command timings, then replays deterministic CPU steps. Replay includes:

- repo reset;
- patch application;
- Python tests;
- C++ build and tests;
- lint/static analysis;
- regex/log parsing;
- SQLite/data fixture operations if present;
- result collection.

### Metrics Collector

Captures:

- completion time;
- CPU tool-step time;
- tests, compile, lint, and static-analysis durations;
- concurrency saturation;
- agents at SLA;
- cgroup CPU seconds where available;
- node and image metadata.

### Dashboard and Report Generator

The dashboard is the live artifact. The report is the buyer/lab follow-up artifact.

Outputs:

- Race First browser dashboard;
- CLI transcript;
- generated report with charts, metrics, and run provenance.

## 6. Data Flow

1. The operator selects a preset: short race or technical race.
2. The operator selects a normalization mode: equal-vCPU or equal-physical-core estimate.
3. The orchestrator schedules paired worker pods in `agentic-cpu-bench-demo` on Grace and x86.
4. Each worker checks out the same repo snapshot and applies the same broken-task fixture.
5. In live mode, the Codex-style agent inspects, edits, runs allowed commands, and iterates.
6. Workers stream events: command started, command finished, file changed, tests failed, tests passed, compile duration, lint duration, static-analysis duration, and final result.
7. The dashboard renders the Race First view.
8. The recorder saves action traces, artifacts, and transcripts.
9. In replay mode, the harness resets the repo and replays deterministic CPU steps from the trace.
10. The report generator aggregates live and replay results.

## 7. Dashboard Narrative

The dashboard opens with **Race First**:

- Grace and x86 side-by-side;
- task status and current step;
- elapsed time;
- tests/compile/lint status;
- final pass/fail;
- headline composite score.

Secondary panels show:

- agents at SLA under concurrency;
- CPU tool-step timing;
- expanded trace for one task;
- GPU-wait proxy;
- equal-vCPU and equal-physical-core views.

## 8. Metrics

The headline is a composite score, but the first number shown is always completion time.

Primary metric:

- **Completion time:** wall-clock time to solve the same bug-fix task suite.

Supporting metrics:

- **Agents at SLA:** maximum concurrent coding agents before P95 completion time exceeds 2x the single-worker baseline, P99 command-step latency becomes unstable, or any worker hits timeout.
- **CPU tool-step time:** time spent in pytest, C++ build/test, lint, static analysis, regex/log parsing, SQLite/data fixtures, repo reset, and sandbox startup.
- **GPU-wait proxy:** estimated model-serving stall caused by CPU-side tool results, computed from aggregate agent tool wait.

Normalization:

- **Equal-vCPU:** Kubernetes/cloud scheduling lens.
- **Equal-physical-core estimate:** technical CPU comparison lens. This is an estimate because x86 SMT can expose two vCPUs per physical core.

Composite ordering:

1. Completion time.
2. Agents at SLA.
3. CPU tool-step time.
4. GPU-wait proxy.

## 9. Error Handling and Demo Reliability

Every task has:

- timeout;
- command allowlist;
- setup script;
- reset script;
- deterministic pass/fail criteria.

If the live agent gets stuck, the dashboard marks the task as `timeout` and still reports the trace. Failures are classified as:

- agent reasoning failure;
- tool execution bottleneck;
- environment setup failure;
- task-definition failure.

Replay failures are classified separately:

- **Replay mismatch:** recorded trace cannot be reproduced.
- **Environment failure:** missing dependency, scheduling issue, or image pull failure.
- **Task failure:** tests do not pass after replayed edits.
- **Measurement failure:** metrics are missing or incomplete.

The dashboard must not hide failures. A failed run should still explain where time went and whether the issue was the agent, environment, or CPU tool path.

## 10. Fairness and Provenance

Grace and x86 runs use the same:

- repo snapshot;
- task fixture;
- model/config;
- tool policy;
- timeout;
- dashboard clock;
- worker image version;
- success commands.

Validated initial scheduling targets:

- **Grace proxy:** `arm64`, `a4x-highgpu-4g`, node pool `customer-gpu-w0e`, with toleration `kubernetes.io/arch=arm64:NoSchedule`.
- **x86 baseline:** `amd64`, `n2d-standard-8`, node pool `customer-cpu`.

Each run records:

- node type;
- CPU requests and limits;
- architecture;
- image digest;
- git commit;
- task ID;
- command versions;
- preset;
- normalization mode;
- timestamp.

## 11. Testing and Validation

### Task Validation

For each task:

- broken state fails;
- expected patch passes;
- reset restores broken state.

### Harness Validation

Local smoke tests cover:

- task setup/reset;
- command allowlist enforcement;
- event emission;
- trace recording;
- replay execution;
- report generation.

Replay must reproduce the same pass/fail outcome without invoking the LLM.

### Cluster Validation

Before a real demo, run a paired Grace/x86 smoke on `your-k8s-cluster` to verify:

- namespace `agentic-cpu-bench-demo`;
- scheduling;
- CPU limits;
- node labels;
- clocks;
- image pulls;
- dashboard streaming;
- metric capture.

Run order:

1. namespace and scheduler smoke;
2. short race preset;
3. technical race preset;
4. replay benchmark;
5. concurrency sweep for agents-at-SLA.

## 12. Acceptance Criteria

The design is successful when:

- the Race First dashboard shows Grace and x86 progressing live;
- at least one Python+C++ bug-fix task completes in the short preset;
- live guided-autonomous mode emits a complete CLI transcript;
- replay mode reruns the trace and produces the same result;
- the generated report includes completion time, agents at SLA, CPU tool-step time, GPU-wait proxy, and both normalization views;
- every result includes provenance sufficient for technical review.

## 13. Out of Scope

This design does not include:

- implementing the harness;
- selecting final x86 instance types;
- proving Vera final silicon numbers;
- building a full commercial product;
- broad agent-framework comparison;
- non-coding enterprise workflows.

Those decisions belong in the implementation plan or later extensions.
