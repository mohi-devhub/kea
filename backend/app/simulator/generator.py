"""Pure seeded telemetry generator."""
# ruff: noqa: E501

import hashlib
import random

from app.models.events import DeploymentEvent, Event, MetricEvent, make_event_id
from app.models.topology import Topology
from app.simulator.models import EffectSpec, Scenario

EPOCH_MS = 1_758_192_000_000


def _rng(seed: int, service: str, metric: str) -> random.Random:
    digest = hashlib.sha256(f"{seed}:{service}:{metric}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def _effect_value(effect: EffectSpec, base: float, elapsed: int, jitter: int) -> float:
    age = elapsed - (effect.start_s + jitter)
    if age < 0 or (effect.duration_s is not None and age >= effect.duration_s):
        return base
    progress = 1.0 if effect.ramp_s == 0 else min(1.0, age / effect.ramp_s)
    if effect.target_value is not None:
        target = effect.target_value
    else:
        assert effect.target_multiplier is not None
        target = base * effect.target_multiplier
    return base + (target - base) * progress


def generate(
    scenario: Scenario, topology: Topology, seed: int, run_id: str | None = None
) -> list[Event]:
    """Generate ordered events entirely from scenario data and a seed."""
    actual_run_id = run_id or f"{scenario.id}-{seed}"
    events: list[Event] = []
    jitter_rng = random.Random(
        int.from_bytes(hashlib.sha256(f"{seed}:{scenario.id}".encode()).digest()[:8], "big")
    )
    jitter = {id(effect): jitter_rng.randint(-4, 4) for effect in scenario.effects}
    for deployment in scenario.deployments:
        ts = EPOCH_MS + (scenario.warmup_s + deployment.offset_s) * 1000
        events.append(
            DeploymentEvent(
                event_id="",
                run_id=actual_run_id,
                seq=0,
                ts=ts,
                service=deployment.service,
                kind="deployment",
                payload={
                    "deployment_id": deployment.deployment_id,
                    "version": deployment.version,
                    "commit_ref": deployment.commit_ref,
                    "summary": deployment.summary,
                    "author": "ci-bot",
                },
            )
        )
    end_s = scenario.warmup_s + scenario.duration_s
    effects_by_series: dict[tuple[str, str], list[EffectSpec]] = {}
    for effect in scenario.effects:
        effects_by_series.setdefault((effect.service, effect.metric), []).append(effect)
    series_rng = {
        (service, metric): _rng(seed, service, metric)
        for service in topology.metrics
        for metric in topology.metrics[service]
    }
    for elapsed in range(0, end_s + 1, topology.sample_interval_s):
        for service in sorted(topology.metrics):
            for metric, (base, noise_sd) in sorted(topology.metrics[service].items()):
                value = base * (1 + series_rng[(service, metric)].gauss(0, noise_sd))
                for effect in effects_by_series.get((service, metric), []):
                    value = _effect_value(
                        effect, base, elapsed - scenario.warmup_s, jitter[id(effect)]
                    )
                events.append(
                    MetricEvent(
                        event_id="",
                        run_id=actual_run_id,
                        seq=0,
                        ts=EPOCH_MS + elapsed * 1000,
                        service=service,
                        kind="metric",
                        payload={"metric": metric, "value": round(value, 4)},
                    )
                )
    events.sort(
        key=lambda event: (
            event.ts,
            0 if event.kind == "deployment" else 1,
            event.service,
            str(event.kind),
        )
    )
    return [
        event.model_copy(update={"seq": index, "event_id": make_event_id(actual_run_id, index)})
        for index, event in enumerate(events)
    ]
