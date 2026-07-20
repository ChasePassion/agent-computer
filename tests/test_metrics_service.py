from __future__ import annotations

from agent_computer.services.metrics_service import MetricsService


def test_metrics_snapshot_reports_latency_percentiles_and_outcomes() -> None:
    metrics = MetricsService(max_samples_per_metric=10)
    metrics.record("desktop.act", duration_ms=10, outcome="success")
    metrics.record("desktop.act", duration_ms=30, outcome="failed")
    metrics.record("desktop.act", duration_ms=20, outcome="success")

    snapshot = metrics.snapshot()["desktop.act"]

    assert snapshot["count"] == 3
    assert snapshot["success_count"] == 2
    assert snapshot["failure_count"] == 1
    assert snapshot["p50_ms"] == 20.0
    assert snapshot["p95_ms"] == 30.0
    assert snapshot["max_ms"] == 30.0
