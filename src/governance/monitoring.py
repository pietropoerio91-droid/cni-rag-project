import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class RAGMonitor:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.traces: list[dict[str, Any]] = []

    def start_trace(self, session_id: str | None = None) -> str:
        if not self.enabled:
            return ""
        trace_id = session_id or str(uuid.uuid4())
        self.traces.append({
            "trace_id": trace_id,
            "start_time": datetime.now(timezone.utc).isoformat(),
            "events": [],
        })
        return trace_id

    def log_event(self, trace_id: str, event: str, data: dict[str, Any] | None = None) -> None:
        if not self.enabled:
            return
        for trace in self.traces:
            if trace["trace_id"] == trace_id:
                trace["events"].append({
                    "event": event,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "data": data or {},
                })
                break

    def end_trace(self, trace_id: str, result: dict[str, Any] | None = None) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        for trace in self.traces:
            if trace["trace_id"] == trace_id:
                trace["end_time"] = datetime.now(timezone.utc).isoformat()
                trace["result"] = result or {}
                start = datetime.fromisoformat(trace["start_time"])
                end = datetime.fromisoformat(trace["end_time"])
                trace["duration_ms"] = (end - start).total_seconds() * 1000
                logger.info(f"Trace {trace_id} completed in {trace['duration_ms']:.0f}ms")
                return trace
        return None

    def get_traces(self) -> list[dict[str, Any]]:
        return self.traces
