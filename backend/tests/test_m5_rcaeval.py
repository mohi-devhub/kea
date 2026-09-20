import pytest

from app.eval.rcaeval import case_names, load_case, online_boutique

pa = pytest.importorskip("pyarrow")


def test_case_names_cover_five_services_and_faults() -> None:
    names = case_names()
    assert len(names) == 25 and "re1ob_adservice_delay_1" in names


def test_load_case_maps_metrics_and_subsamples(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import pyarrow.parquet as pq

    times = list(range(1000, 1060))
    table = pa.table(
        {
            "time": times,
            "adservice_latency-90": [0.004] * 30 + [0.2] * 30,
            "adservice_cpu": [0.3] * 30 + [75.0] * 30,
            "adservice_latency-50": [0.002] * 30 + [0.05] * 30,
            "adservice_mem": [4e7] * 60,
            "unknown_workload": [1.0] * 60,  # service not in topology
        }
    )
    pq.write_table(table, tmp_path / "metrics.parquet")
    (tmp_path / "inject_time.txt").write_text("1030")
    events, scenario = load_case("re1ob_adservice_delay_1", tmp_path, online_boutique())
    metrics = {e.payload.metric for e in events}  # type: ignore[union-attr]
    assert metrics == {"latency_p95_ms", "memory_used_pct", "cpu_pct", "network_delay_ms"}
    assert len(events) == 4 * 12  # every 5th second of 60
    assert max(e.payload.value for e in events if e.payload.metric == "latency_p95_ms") == 200  # type: ignore[union-attr]
    assert scenario.warmup_s == 30 and scenario.ground_truth.root_cause.service == "adservice"  # type: ignore[union-attr]
