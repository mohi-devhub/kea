"""Render the fair, chronological input given to LLM-only baselines."""

from collections import defaultdict
from datetime import UTC, datetime
from statistics import median

from app.models.events import DeploymentEvent, Event, LogEvent, MetricEvent, RollbackEvent
from app.models.topology import Topology


def _clock(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=UTC).strftime("%H:%M:%S")


def render_baseline_input(
    events: list[Event],
    *,
    topology: Topology | None = None,
    include_topology: bool = False,
    max_logs: int = 400,
    metric_window_start: int | None = None,
) -> str:
    """Render events without simulator metadata, engine output, or ground truth.

    The runner owns event generation; this renderer only sees the resulting event stream.
    `metric_window_start` (epoch ms) is where the metric window begins; the spec puts it 120 s
    before the fault (EVAL_SPEC section 3) so the healthy baseline and the onset order are
    visible. It is only a timestamp: it says nothing about which service failed.
    """

    if not events:
        return "ANALYSIS TIME: unknown\nNo telemetry was observed."
    analysis_ts = max(event.ts for event in events)
    lines = [f"ANALYSIS TIME: {_clock(analysis_ts)}", "DEPLOYMENTS AND ROLLBACKS"]
    lines.append("  time      service         id       version  summary")
    for event in events:
        if isinstance(event, DeploymentEvent):
            deployment = event.payload
            lines.append(
                f"  {_clock(event.ts)}  {event.service:<15} {deployment.deployment_id:<8} "
                f"{deployment.version:<8} {deployment.summary}"
            )
        elif isinstance(event, RollbackEvent):
            rollback = event.payload
            lines.append(
                f"  {_clock(event.ts)}  {event.service:<15} {rollback.deployment_id:<8} "
                f"restored  rollback to {rollback.restored_version}"
            )
    lines.append("LOGS (all WARN/ERROR; INFO sampled; max 400 lines)")
    logs = [event for event in events if isinstance(event, LogEvent)]
    info_seen = 0
    selected_logs: list[LogEvent] = []
    for event in logs:
        if event.payload.level == "INFO":
            info_seen += 1
            if info_seen % 4 != 1:
                continue
        selected_logs.append(event)
    for event in selected_logs[-max_logs:]:
        log_payload = event.payload
        fields = " ".join(f"{key}={value}" for key, value in sorted(log_payload.fields.items()))
        lines.append(
            f"  {_clock(event.ts)}  {event.service:<15} {log_payload.level:<5} "
            f"{log_payload.message} {fields}".rstrip()
        )

    window_start = metric_window_start if metric_window_start is not None else analysis_ts - 120_000
    lines.append(
        f"METRICS (median per 15s bucket; window: {_clock(window_start)} .. analysis time)"
    )
    metrics: dict[tuple[str, str, int], list[float]] = defaultdict(list)
    for event in events:
        if not isinstance(event, MetricEvent) or event.ts < window_start:
            continue
        bucket = (event.ts - window_start) // 15_000
        metrics[(event.service, event.payload.metric, int(bucket))].append(event.payload.value)
    for service, metric in sorted({(service, metric) for service, metric, _ in metrics}):
        values = []
        for (item_service, item_metric, bucket), points in sorted(metrics.items()):
            if item_service == service and item_metric == metric:
                ts = window_start + bucket * 15_000
                values.append(f"{_clock(ts)} {median(points):.4g}")
        lines.append(f"  service: {service} | metric: {metric}")
        lines.append("    " + " | ".join(values))

    if include_topology and topology is not None:
        lines.append("TOPOLOGY (caller -> callee, blocking?, tiers)")
        for edge in topology.edges:
            caller = topology.services[edge.from_]
            callee = topology.services[edge.to]
            blocking = "blocking" if edge.blocking else "non-blocking"
            lines.append(
                f"  {edge.from_} -> {edge.to} ({blocking}; {caller.tier} -> {callee.tier})"
            )
    return "\n".join(lines)
