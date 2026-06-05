from __future__ import annotations

from typing import Any

from .command_runner import CommandResult


def summarize_commands(commands: list[CommandResult], completion_ms: float) -> dict[str, float | int]:
    return {
        "completion_ms": completion_ms,
        "cpu_tool_step_ms": sum(command.duration_ms for command in commands),
        "command_count": len(commands),
    }


def _positive_float(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if number > 0 else 0.0


def _score_from_lower_is_better(best: float, value: float) -> float:
    if best <= 0 or value <= 0:
        return 0.0
    return min(200.0, (best / value) * 100.0)


def _physical_core_estimate_factor(side: object) -> float:
    # The x86 baseline exposes SMT vCPUs. Estimate equal physical cores by
    # halving the equal-vCPU completion time for x86; Grace is treated as 1:1.
    return 0.5 if str(side).lower() == "x86" else 1.0


def with_derived_metrics(summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched = [dict(summary) for summary in summaries]
    for summary in enriched:
        completion_ms = _positive_float(summary.get("completion_ms"))
        cpu_tool_step_ms = _positive_float(summary.get("cpu_tool_step_ms"))
        gpu_wait_proxy_ms = _positive_float(summary.get("gpu_wait_proxy_ms")) or cpu_tool_step_ms
        summary["gpu_wait_proxy_ms"] = gpu_wait_proxy_ms
        summary["equal_vcpu_completion_ms"] = completion_ms
        summary["equal_physical_core_est_completion_ms"] = completion_ms * _physical_core_estimate_factor(
            summary.get("side")
        )
        summary["normalization_note"] = (
            "equal-vCPU uses Kubernetes CPU limits; equal-physical-core is an SMT-adjusted estimate"
        )

    completion_values = [_positive_float(summary.get("completion_ms")) for summary in enriched]
    cpu_values = [_positive_float(summary.get("cpu_tool_step_ms")) for summary in enriched]
    gpu_values = [_positive_float(summary.get("gpu_wait_proxy_ms")) for summary in enriched]
    agents_values = [_positive_float(summary.get("agents_at_sla", 1)) for summary in enriched]

    best_completion = min((value for value in completion_values if value > 0), default=0.0)
    best_cpu = min((value for value in cpu_values if value > 0), default=0.0)
    best_gpu = min((value for value in gpu_values if value > 0), default=0.0)
    best_agents = max(agents_values, default=1.0) or 1.0

    for summary in enriched:
        completion_score = _score_from_lower_is_better(best_completion, _positive_float(summary.get("completion_ms")))
        cpu_score = _score_from_lower_is_better(best_cpu, _positive_float(summary.get("cpu_tool_step_ms")))
        gpu_score = _score_from_lower_is_better(best_gpu, _positive_float(summary.get("gpu_wait_proxy_ms")))
        agents_score = min(200.0, (_positive_float(summary.get("agents_at_sla", 1)) / best_agents) * 100.0)
        summary["composite_score"] = (
            completion_score * 0.55 + agents_score * 0.20 + cpu_score * 0.15 + gpu_score * 0.10
        )
        summary["composite_components"] = {
            "completion": completion_score,
            "agents_at_sla": agents_score,
            "cpu_tool_step": cpu_score,
            "gpu_wait_proxy": gpu_score,
        }
    return enriched


def race_headline(summaries: list[dict[str, Any]]) -> str:
    complete = [summary for summary in summaries if _positive_float(summary.get("completion_ms")) > 0]
    if len(complete) < 2:
        return "Race in progress"
    sorted_summaries = sorted(complete, key=lambda summary: _positive_float(summary.get("completion_ms")))
    winner = sorted_summaries[0]
    runner_up = sorted_summaries[1]
    winner_ms = _positive_float(winner.get("completion_ms"))
    runner_up_ms = _positive_float(runner_up.get("completion_ms"))
    if winner_ms <= 0:
        return "Race complete"
    speedup = runner_up_ms / winner_ms
    return f"{winner.get('label', winner.get('side', 'winner'))} leads at {speedup:.2f}x completion speed"
