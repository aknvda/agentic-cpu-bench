from __future__ import annotations

import json
import os
import subprocess
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .metrics import race_headline, with_derived_metrics


SIDES = ("grace", "x86")
STEP_LANES = (
    ("setup", "Setup", ("run_started",)),
    ("patch", "Patch", ("apply-patch",)),
    ("python_tests", "Python tests", ("python-tests",)),
    ("cpp_build", "C++ build", ("cpp-build",)),
    ("cpp_tests", "C++ tests", ("cpp-tests",)),
    ("lint", "Lint", ("lint",)),
    ("static_analysis", "Static analysis", ("static-analysis",)),
)


def parse_streamed_events(log_text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in log_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and isinstance(event.get("type"), str):
            events.append(event)
    return events


def _compact_event_line(event: dict[str, Any]) -> str | None:
    event_type = str(event.get("type", ""))
    command = str(event.get("command", ""))
    if event_type == "run_started":
        return f"run started · {event.get('side', '')} · {event.get('mode', '')}"
    if event_type == "command_started":
        return f"started · {command}"
    if event_type == "command_finished":
        duration = event.get("duration_ms")
        duration_text = f" · {float(duration):.2f} ms" if isinstance(duration, (int, float)) else ""
        return f"finished · {command} · rc={event.get('returncode')}{duration_text}"
    if event_type == "run_finished":
        duration = event.get("completion_ms")
        duration_text = f" · {float(duration):.2f} ms" if isinstance(duration, (int, float)) else ""
        return f"run finished · ok={event.get('ok')}{duration_text}"
    return None


def transcript_tail(log_text: str, limit: int = 36) -> list[str]:
    lines: list[str] = []
    skipping_artifacts = False
    for line in log_text.splitlines():
        if line.startswith("__AGENTIC_GAUNTLET_ARTIFACTS_BEGIN_"):
            skipping_artifacts = True
            continue
        if line.startswith("__AGENTIC_GAUNTLET_ARTIFACTS_END_"):
            skipping_artifacts = False
            continue
        if skipping_artifacts:
            continue
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("{"):
            try:
                event = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                compact = _compact_event_line(event)
                if compact:
                    lines.append(compact)
            continue
        noisy_prefixes = (
            "tar: Ignoring unknown extended header keyword",
            "Processing /work/",
            "Installing build dependencies:",
            "Getting requirements to build wheel:",
            "Preparing metadata",
            "Building wheel",
            "Created wheel",
            "Stored in directory:",
            "Successfully built",
            "Installing collected packages:",
            "Successfully installed",
            "WARNING: Running pip as the 'root' user",
            "[notice]",
        )
        if stripped.startswith(noisy_prefixes):
            continue
        if any(marker in stripped for marker in ("waiting_for_synchronized_start", "synchronized_start", "run_exit_code", "ok=")):
            lines.append(stripped)
            continue
        if len(line) > 240:
            line = line[:237] + "..."
        if "error" in stripped.lower() or "failed" in stripped.lower():
            lines.append(line)
    return lines[-limit:]


def _command_status(events: list[dict[str, Any]], commands: tuple[str, ...]) -> dict[str, Any]:
    run_finished = any(event.get("type") == "run_finished" for event in events)
    if commands == ("run_started",):
        started = any(event.get("type") == "run_started" for event in events)
        return {"label": "Setup", "status": "pass" if started else "waiting", "duration_ms": 0.0 if run_finished else None}
    started = any(event.get("type") == "command_started" and event.get("command") in commands for event in events)
    finished_events = [
        event for event in events if event.get("type") == "command_finished" and event.get("command") in commands
    ]
    if finished_events:
        ok = all(int(event.get("returncode", 1)) == 0 for event in finished_events)
        return {
            "status": "pass" if ok else "fail",
            "duration_ms": sum(float(event.get("duration_ms", 0.0)) for event in finished_events),
        }
    if started:
        return {"status": "running", "duration_ms": None}
    if run_finished and commands[0] in {"lint", "static-analysis"}:
        return {"status": "not_configured", "duration_ms": None}
    return {"status": "waiting", "duration_ms": None}


def step_statuses(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lanes: list[dict[str, Any]] = []
    for key, label, commands in STEP_LANES:
        status = _command_status(events, commands)
        lanes.append(
            {
                "key": key,
                "label": label,
                "status": status["status"],
                "duration_ms": status.get("duration_ms"),
            }
        )
    return lanes


def side_state_from_events(
    side: str,
    *,
    events: list[dict[str, Any]],
    job_status: str = "waiting",
    pod_phase: str = "waiting",
    pod_name: str | None = None,
    node_name: str | None = None,
    transcript: list[str] | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    now = time.time() if now is None else now
    started = next((event for event in events if event.get("type") == "run_started"), None)
    finished = next((event for event in reversed(events) if event.get("type") == "run_finished"), None)
    command_events = [event for event in events if event.get("type") == "command_finished"]
    started_commands = [event for event in events if event.get("type") == "command_started"]
    last_started = started_commands[-1].get("command") if started_commands else None
    last_finished = command_events[-1].get("command") if command_events else None

    if finished:
        ok = bool(finished.get("ok"))
        status = "pass" if ok else "fail"
        result = "PASS" if ok else "FAIL"
        completion_ms = float(finished.get("completion_ms", 0.0))
        elapsed_ms = completion_ms
    elif started:
        status = "running"
        result = "RUNNING"
        elapsed_ms = max(0.0, (now - float(started.get("ts", now))) * 1000)
        completion_ms = 0.0
    elif job_status.lower() in {"failed", "fail"} or pod_phase.lower() == "failed":
        status = "fail"
        result = "FAIL"
        elapsed_ms = 0.0
        completion_ms = 0.0
    elif pod_phase.lower() in {"pending", "running", "containercreating"} or job_status.lower() == "running":
        status = "starting"
        result = "STARTING"
        elapsed_ms = 0.0
        completion_ms = 0.0
    else:
        status = "waiting"
        result = "WAITING"
        elapsed_ms = 0.0
        completion_ms = 0.0

    if finished:
        current_step = "complete"
    else:
        current_step = str(last_started or last_finished or ("pod-" + pod_phase.lower() if pod_phase else "waiting"))
    trace = [
        {
            "type": str(event.get("type", "")),
            "command": str(event.get("command", "")),
            "returncode": event.get("returncode"),
            "duration_ms": event.get("duration_ms"),
        }
        for event in events
        if event.get("type") in {"command_started", "command_finished", "run_finished"}
    ]
    return {
        "side": side,
        "label": "Grace" if side == "grace" else "x86",
        "status": status,
        "result": result,
        "job_status": job_status,
        "pod_phase": pod_phase,
        "pod_name": pod_name or "",
        "node_name": node_name or "",
        "current_step": current_step,
        "elapsed_ms": elapsed_ms,
        "completion_ms": completion_ms,
        "cpu_tool_step_ms": sum(float(event.get("duration_ms", 0.0)) for event in command_events),
        "command_count": len(command_events),
        "agents_at_sla": 1 if status == "pass" else 0,
        "task_id": str(started.get("task_id", "python_cpp_bugfix")) if started else "python_cpp_bugfix",
        "step_statuses": step_statuses(events),
        "trace": trace[-12:],
        "transcript": transcript or [],
        "provenance": {
            "namespace": "",
            "pod_name": pod_name or "",
            "node_name": node_name or "",
            "job_status": job_status,
            "pod_phase": pod_phase,
        },
    }


def initial_dashboard_state(namespace: str, mode: str) -> dict[str, Any]:
    return {
        "title": "Race First: Grace vs x86",
        "namespace": namespace,
        "mode": mode,
        "status": "waiting",
        "headline": "Race in progress",
        "updated_at": time.time(),
        "sides": [side_state_from_events(side, events=[]) for side in SIDES],
    }


def write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)


def read_state(path: Path, namespace: str = "unknown", mode: str = "unknown") -> dict[str, Any]:
    if not path.exists():
        return initial_dashboard_state(namespace, mode)
    return json.loads(path.read_text(encoding="utf-8"))


def _kubectl_json(args: list[str]) -> dict[str, Any] | None:
    completed = subprocess.run(args, text=True, capture_output=True)
    if completed.returncode != 0 or not completed.stdout.strip():
        return None
    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _kubectl_text(args: list[str]) -> str:
    completed = subprocess.run(args, text=True, capture_output=True)
    return completed.stdout if completed.returncode == 0 else ""


def _job_status(job: dict[str, Any] | None) -> str:
    if not job:
        return "waiting"
    status = job.get("status", {})
    if not isinstance(status, dict):
        return "unknown"
    if status.get("succeeded", 0):
        return "complete"
    if status.get("failed", 0):
        return "failed"
    if status.get("active", 0):
        return "running"
    return "created"


def _pod_for_job(namespace: str, job_name: str) -> dict[str, Any] | None:
    pods = _kubectl_json(
        ["kubectl", "get", "pods", "-n", namespace, "-l", f"job-name={job_name}", "-o", "json"]
    )
    if not pods:
        return None
    items = pods.get("items", [])
    if not isinstance(items, list) or not items:
        return None
    first = items[0]
    return first if isinstance(first, dict) else None


def collect_k8s_dashboard_state(namespace: str, mode: str) -> dict[str, Any]:
    sides: list[dict[str, Any]] = []
    seen_workers = False
    for side in SIDES:
        job_name = f"agentic-cpu-bench-worker-{side}"
        job = _kubectl_json(["kubectl", "get", "job", "-n", namespace, job_name, "-o", "json"])
        pod = _pod_for_job(namespace, job_name)
        if job or pod:
            seen_workers = True
        metadata = pod.get("metadata", {}) if pod else {}
        status = pod.get("status", {}) if pod else {}
        spec = pod.get("spec", {}) if pod else {}
        pod_name = metadata.get("name") if isinstance(metadata, dict) else None
        pod_phase = status.get("phase") if isinstance(status, dict) else None
        node_name = spec.get("nodeName") if isinstance(spec, dict) else None
        log_text = ""
        if isinstance(pod_name, str) and pod_name:
            log_text = _kubectl_text(["kubectl", "logs", "-n", namespace, pod_name, "--tail=4000"])
        sides.append(
            side_state_from_events(
                side,
                events=parse_streamed_events(log_text),
                job_status=_job_status(job),
                pod_phase=str(pod_phase or "waiting"),
                pod_name=pod_name if isinstance(pod_name, str) else None,
                node_name=node_name if isinstance(node_name, str) else None,
                transcript=transcript_tail(log_text),
            )
        )
        sides[-1]["provenance"]["namespace"] = namespace
    sides = with_derived_metrics(sides)
    complete = all(
        side["status"] in {"pass", "fail"} and side["job_status"] in {"complete", "failed"} for side in sides
    )
    any_running = any(side["status"] in {"starting", "running"} for side in sides)
    state_status = "complete" if complete else "running" if seen_workers or any_running else "waiting"
    return {
        "title": "Race First: Grace vs x86",
        "namespace": namespace,
        "mode": mode,
        "status": state_status,
        "headline": race_headline(sides),
        "updated_at": time.time(),
        "sides": sides,
    }


def watch_k8s_dashboard(
    *,
    namespace: str,
    mode: str,
    state_path: Path,
    interval_seconds: float,
    timeout_seconds: int,
) -> None:
    started = time.monotonic()
    observed_workers = False
    write_state(state_path, initial_dashboard_state(namespace, mode))
    while True:
        state = collect_k8s_dashboard_state(namespace, mode)
        observed_workers = observed_workers or state["status"] in {"running", "complete"}
        write_state(state_path, state)
        if observed_workers and state["status"] == "complete":
            return
        if time.monotonic() - started >= timeout_seconds:
            state["status"] = "timeout"
            write_state(state_path, state)
            return
        time.sleep(interval_seconds)


def dashboard_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Agentic CPU Bench</title>
  <style>
    :root { color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    body { margin: 0; background: #f7f8fa; color: #161b22; }
    main { max-width: 1180px; margin: 0 auto; padding: 28px; }
    header { display: flex; justify-content: space-between; align-items: flex-end; gap: 20px; margin-bottom: 24px; }
    h1 { font-size: 32px; margin: 0; letter-spacing: 0; }
    .meta { color: #59636e; font-size: 14px; text-align: right; }
    .grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
    .panel { background: white; border: 1px solid #d8dee4; border-radius: 8px; padding: 18px; }
    .panel h2 { margin: 0 0 12px; font-size: 20px; }
    .summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 16px; }
    .summary .panel strong { display: block; font-size: 22px; margin-top: 4px; }
    .status { display: inline-flex; align-items: center; padding: 4px 9px; border-radius: 999px; font-size: 12px; font-weight: 700; text-transform: uppercase; }
    .waiting { background: #eaeef2; color: #57606a; }
    .starting { background: #fff8c5; color: #7d5f00; }
    .running { background: #ddf4ff; color: #0969da; }
    .pass { background: #dafbe1; color: #1a7f37; }
    .fail, .timeout { background: #ffebe9; color: #cf222e; }
    .metrics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin: 14px 0; }
    .metric { border-top: 1px solid #d8dee4; padding-top: 10px; }
    .metric span { display: block; color: #59636e; font-size: 12px; }
    .metric strong { font-size: 18px; }
    .steps { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 6px; margin: 12px 0; }
    .step { border: 1px solid #d8dee4; border-radius: 6px; padding: 8px; min-height: 54px; }
    .step span { display: block; font-size: 11px; color: #59636e; }
    .secondary { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-top: 16px; }
    .trace { margin: 12px 0 0; padding: 0; list-style: none; font-size: 13px; color: #424a53; }
    .trace li { display: flex; justify-content: space-between; gap: 12px; padding: 7px 0; border-top: 1px solid #eef1f4; }
    pre { margin: 10px 0 0; max-height: 240px; overflow: auto; background: #f6f8fa; border: 1px solid #d8dee4; border-radius: 6px; padding: 10px; font-size: 12px; white-space: pre-wrap; }
    .node { color: #59636e; font-size: 13px; overflow-wrap: anywhere; min-height: 36px; }
    @media (max-width: 900px) { main { padding: 18px; } header { display: block; } .meta { text-align: left; margin-top: 8px; } .grid, .summary, .secondary { grid-template-columns: 1fr; } .metrics, .steps { grid-template-columns: 1fr 1fr; } }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Race First: Grace vs x86</h1>
        <div id="subtitle">Waiting for Kubernetes workers...</div>
      </div>
      <div class="meta"><div id="namespace"></div><div id="updated"></div></div>
    </header>
    <section class="summary" id="summary"></section>
    <section class="grid" id="sides"></section>
    <section class="secondary">
      <article class="panel">
        <h2>Normalization Views</h2>
        <div id="normalization"></div>
      </article>
      <article class="panel">
        <h2>Agents at SLA and GPU-Wait Proxy</h2>
        <div id="sla"></div>
      </article>
    </section>
    <section class="secondary">
      <article class="panel">
        <h2>Expanded Trace</h2>
        <div id="trace"></div>
      </article>
      <article class="panel">
        <h2>CLI Transcript</h2>
        <div id="transcript"></div>
      </article>
    </section>
  </main>
  <script>
    const fmtMs = (value) => value ? `${value.toFixed(2)} ms` : "0.00 ms";
    const fmtScore = (value) => value ? value.toFixed(1) : "0.0";
    const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;"
    })[char]);
    function render(state) {
      document.getElementById("subtitle").textContent = `${state.mode} mode · ${state.status} · ${state.headline || "Race in progress"}`;
      document.getElementById("namespace").textContent = `namespace: ${state.namespace}`;
      document.getElementById("updated").textContent = `updated: ${new Date(state.updated_at * 1000).toLocaleTimeString()}`;
      const completed = state.sides.filter((side) => side.completion_ms > 0);
      const fastest = completed.length ? completed.reduce((a, b) => a.completion_ms < b.completion_ms ? a : b) : null;
      const bestComposite = state.sides.reduce((a, b) => (a.composite_score || 0) > (b.composite_score || 0) ? a : b, state.sides[0] || {});
      document.getElementById("summary").innerHTML = `
        <article class="panel">Completion time first<strong>${fastest ? `${esc(fastest.label)} · ${fmtMs(fastest.completion_ms)}` : "Running"}</strong></article>
        <article class="panel">Composite score<strong>${esc(bestComposite.label || "")} · ${fmtScore(bestComposite.composite_score)}</strong></article>
        <article class="panel">Agents at SLA<strong>${state.sides.map((side) => `${esc(side.label)} ${esc(side.agents_at_sla)}`).join(" · ")}</strong></article>
        <article class="panel">GPU-wait proxy<strong>${state.sides.map((side) => `${esc(side.label)} ${fmtMs(side.gpu_wait_proxy_ms)}`).join(" · ")}</strong></article>
      `;
      document.getElementById("sides").innerHTML = state.sides.map((side) => `
        <article class="panel">
          <h2>${esc(side.label)} <span class="status ${esc(side.status)}">${esc(side.result)}</span></h2>
          <div class="node">${esc(side.pod_name || "pod pending")}<br>${esc(side.node_name || "node pending")}</div>
          <div class="metrics">
            <div class="metric"><span>Elapsed</span><strong>${fmtMs(side.elapsed_ms)}</strong></div>
            <div class="metric"><span>CPU tool-step</span><strong>${fmtMs(side.cpu_tool_step_ms)}</strong></div>
            <div class="metric"><span>Composite</span><strong>${fmtScore(side.composite_score)}</strong></div>
          </div>
          <div>Current step: <strong>${esc(side.current_step)}</strong></div>
          <div class="steps">${side.step_statuses.map((step) => `
            <div class="step ${esc(step.status)}"><strong>${esc(step.label)}</strong><span>${esc(step.status)} ${step.duration_ms ? fmtMs(step.duration_ms) : ""}</span></div>
          `).join("")}</div>
          <div class="node">Provenance: ${esc(side.provenance?.namespace || state.namespace)} · ${esc(side.provenance?.job_status || side.job_status)} · ${esc(side.provenance?.pod_phase || side.pod_phase)}</div>
        </article>
      `).join("");
      document.getElementById("normalization").innerHTML = state.sides.map((side) => `
        <div class="metric"><span>${esc(side.label)}</span>
          <strong>equal-vCPU ${fmtMs(side.equal_vcpu_completion_ms)}</strong>
          <div>equal-physical-core est. ${fmtMs(side.equal_physical_core_est_completion_ms)}</div>
        </div>
      `).join("") + `<p>${esc(state.sides[0]?.normalization_note || "")}</p>`;
      document.getElementById("sla").innerHTML = state.sides.map((side) => `
        <div class="metric"><span>${esc(side.label)}</span>
          <strong>${esc(side.agents_at_sla)} agent(s) at SLA</strong>
          <div>GPU-wait proxy ${fmtMs(side.gpu_wait_proxy_ms)}</div>
        </div>
      `).join("");
      document.getElementById("trace").innerHTML = state.sides.map((side) => `
        <h3>${esc(side.label)}</h3>
        <ul class="trace">${side.trace.map((event) => `
          <li><span>${esc(event.type)} ${esc(event.command || "")}</span><span>${event.duration_ms ? fmtMs(event.duration_ms) : ""}</span></li>
        `).join("")}</ul>
      `).join("");
      renderTranscript(state);
    }
    function renderTranscript(state) {
      const root = document.getElementById("transcript");
      const previous = new Map(Array.from(root.querySelectorAll("pre[data-side]")).map((pre) => [
        pre.dataset.side,
        {
          scrollTop: pre.scrollTop,
          atBottom: pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 8
        }
      ]));
      root.innerHTML = state.sides.map((side) => `
        <h3>${esc(side.label)}</h3>
        <pre class="transcript-log" data-side="${esc(side.side)}">${esc((side.transcript || []).join("\\n"))}</pre>
      `).join("");
      root.querySelectorAll("pre[data-side]").forEach((pre) => {
        const prior = previous.get(pre.dataset.side);
        if (!prior || prior.atBottom) {
          pre.scrollTop = pre.scrollHeight;
        } else {
          pre.scrollTop = Math.min(prior.scrollTop, pre.scrollHeight);
        }
      });
    }
    async function tick() {
      const response = await fetch("/state.json", { cache: "no-store" });
      render(await response.json());
    }
    tick();
    setInterval(tick, 1000);
  </script>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    state_path: Path

    def _write(self, body: bytes, content_type: str) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/", "/index.html"}:
            self._write(dashboard_html().encode("utf-8"), "text/html; charset=utf-8")
            return
        if self.path == "/state.json":
            state = read_state(self.state_path)
            self._write(json.dumps(state, sort_keys=True).encode("utf-8"), "application/json")
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return


def serve_dashboard(*, state_path: Path, host: str, port: int) -> None:
    if not state_path.exists():
        write_state(state_path, initial_dashboard_state("unknown", "unknown"))
    handler = type("BoundDashboardHandler", (DashboardHandler,), {"state_path": state_path})
    server = ThreadingHTTPServer((host, port), handler)
    server.serve_forever()
