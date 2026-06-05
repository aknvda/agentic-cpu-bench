from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


_RESERVED_EVENT_KEYS = frozenset({"type", "ts"})


class EventWriter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event_type: str, **payload: Any) -> None:
        reserved_keys = _RESERVED_EVENT_KEYS.intersection(payload)
        if reserved_keys:
            reserved = ", ".join(sorted(reserved_keys))
            raise ValueError(f"reserved event payload keys: {reserved}")
        event = {"type": event_type, "ts": time.time(), **payload}
        line = json.dumps(event, sort_keys=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        if os.environ.get("AGENTIC_GAUNTLET_STREAM_EVENTS") == "1":
            print(line, flush=True)
