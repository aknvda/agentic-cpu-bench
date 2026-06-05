from __future__ import annotations

import re


def extract_error_codes(log_text: str) -> list[str]:
    return re.findall(r"ERR-(\d+)", log_text)


def summarize_counts(values: list[int]) -> dict[str, float]:
    if not values:
        return {"count": 0, "mean": 0.0}
    return {"count": len(values), "mean": float(sum(values) // len(values))}
