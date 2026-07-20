from __future__ import annotations

import math
import threading
from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass
class _MetricState:
    samples: deque[float]
    count: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0
    last_outcome: str | None = None


class MetricsService:
    def __init__(self, *, max_samples_per_metric: int = 512) -> None:
        self.max_samples_per_metric = max(1, max_samples_per_metric)
        self._lock = threading.RLock()
        self._metrics: dict[str, _MetricState] = {}

    def record(self, name: str, *, duration_ms: float, outcome: str) -> None:
        normalized_name = str(name).strip()
        if not normalized_name:
            return
        duration = max(0.0, float(duration_ms))
        normalized_outcome = str(outcome or "unknown").strip().lower()
        with self._lock:
            state = self._metrics.get(normalized_name)
            if state is None:
                state = _MetricState(samples=deque(maxlen=self.max_samples_per_metric))
                self._metrics[normalized_name] = state
            state.samples.append(duration)
            state.count += 1
            state.total_ms += duration
            state.max_ms = max(state.max_ms, duration)
            state.last_outcome = normalized_outcome
            if normalized_outcome in {"success", "passed", "ok"}:
                state.success_count += 1
            else:
                state.failure_count += 1

    def snapshot(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {name: self._snapshot_state(state) for name, state in sorted(self._metrics.items())}

    @classmethod
    def _snapshot_state(cls, state: _MetricState) -> dict[str, Any]:
        ordered = sorted(state.samples)
        return {
            "count": state.count,
            "success_count": state.success_count,
            "failure_count": state.failure_count,
            "avg_ms": round(state.total_ms / state.count, 3) if state.count else 0.0,
            "p50_ms": cls._percentile(ordered, 50),
            "p95_ms": cls._percentile(ordered, 95),
            "max_ms": round(state.max_ms, 3),
            "last_outcome": state.last_outcome,
            "sample_count": len(ordered),
        }

    @staticmethod
    def _percentile(ordered: list[float], percentile: int) -> float:
        if not ordered:
            return 0.0
        index = max(0, min(len(ordered) - 1, math.ceil((percentile / 100) * len(ordered)) - 1))
        return round(float(ordered[index]), 3)
