from app.engine import InMemoryTopology, run_batch
from app.eval.rcaeval import online_boutique
from app.models.events import MetricEvent
from app.simulator.generator import EPOCH_MS


def _series(metric: str, values: list[float]) -> list[MetricEvent]:
    return [
        MetricEvent(
            kind="metric",
            event_id=f"realdata:{metric}:{index}",
            run_id="realdata",
            seq=index,
            ts=EPOCH_MS + index * 5_000,
            service="frontend",
            payload={"metric": metric, "value": value},
        )
        for index, value in enumerate(values)
    ]


def test_step1_cpu_network_and_packet_loss_metrics_detect() -> None:
    values = [20.0] * 15 + [80.0] * 3
    events = _series("cpu_pct", values)
    events += _series("network_delay_ms", [5.0] * 15 + [40.0] * 3)
    events += _series("packet_loss_pct", [0.0] * 15 + [5.0] * 3)
    events.sort(key=lambda event: (event.ts, event.payload.metric))

    result = run_batch(events, InMemoryTopology(online_boutique()))

    assert {anomaly.metric for anomaly in result.anomalies} == {
        "cpu_pct",
        "network_delay_ms",
        "packet_loss_pct",
    }
