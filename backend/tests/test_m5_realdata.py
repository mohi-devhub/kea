from app.engine import InMemoryTopology, run_batch
from app.engine.config import EngineConfig
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


def test_step2_robust_mad_rejects_noisy_spikes_and_detects_step() -> None:
    noisy = [70.0, 130.0] * 8 + [300.0] * 3
    old = run_batch(
        _series("cpu_pct", noisy),
        InMemoryTopology(online_boutique()),
        EngineConfig(use_robust_baseline=False, cpu_delta_pts=0.0, cpu_ratio=1.5),
    )
    robust = run_batch(
        _series("cpu_pct", noisy + [1000.0] * 3),
        InMemoryTopology(online_boutique()),
        EngineConfig(cpu_delta_pts=0.0, cpu_ratio=1.5, cpu_mad_sensitivity=8.0),
    )

    assert any(anomaly.metric == "cpu_pct" for anomaly in old.anomalies)
    assert len(robust.anomalies) == 1
    assert robust.anomalies[0].peak_value == 1000.0
