"""Small, deterministic logistic reranker for offline evaluation.

The model is intentionally independent of the engine.  It consumes serialized engine candidates,
so the engine remains useful when the optional weights file is absent.
"""

import json
from collections.abc import Iterable
from dataclasses import dataclass
from math import exp
from pathlib import Path
from typing import Any

from app.models.engine import Candidate, Incident

FEATURE_NAMES = (
    "factor_temporal",
    "factor_dependency_consistency",
    "factor_anomaly_strength",
    "factor_downstream_impact",
    "anomaly_strength",
    "onset_delta",
    "hop_distance",
    "metric_latency_p95_ms",
    "metric_error_rate",
    "metric_request_rate",
    "metric_active_connections",
    "metric_memory_used_pct",
    "metric_cpu_pct",
    "metric_network_delay_ms",
    "metric_packet_loss_pct",
)
METRIC_FEATURES = {
    name.removeprefix("metric_"): index
    for index, name in enumerate(FEATURE_NAMES)
    if name.startswith("metric_")
}
WEIGHTS_VERSION = "learned-reranker-v1"


@dataclass(frozen=True)
class LearnedWeights:
    version: str
    feature_names: tuple[str, ...]
    coefficients: tuple[float, ...]
    intercept: float
    l2: float

    def model_dump(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "feature_names": list(self.feature_names),
            "coefficients": list(self.coefficients),
            "intercept": self.intercept,
            "l2": self.l2,
        }


def candidate_features(incident: Incident, candidate: Candidate) -> tuple[float, ...]:
    """Return the bounded feature vector used for training and inference."""
    factors = [
        candidate.factors[name].value
        for name in (
            "temporal",
            "dependency_consistency",
            "anomaly_strength",
            "downstream_impact",
        )
    ]
    by_id = {anomaly.anomaly_id: anomaly for anomaly in incident.anomalies}
    attached = [
        by_id[anomaly_id] for anomaly_id in candidate.covered_anomaly_ids if anomaly_id in by_id
    ]
    strongest_ratio = max((anomaly.ratio for anomaly in attached), default=1.0)
    anomaly_strength = _clip((strongest_ratio - 1.0) / 10.0, 0.0, 1.0)
    candidate_ts = candidate.chain[0].ts if candidate.chain else incident.first_anomaly_ts
    onset_delta = _clip(
        (candidate_ts - incident.first_anomaly_ts) / (5 * 60 * 1000),
        -1.0,
        1.0,
    )
    hop_distance = _clip((len(candidate.chain) - 1) / 8.0, 0.0, 1.0)
    metrics = {anomaly.metric for anomaly in attached}
    metric_hits = [1.0 if metric in metrics else 0.0 for metric in METRIC_FEATURES]
    return tuple([*factors, anomaly_strength, onset_delta, hop_distance, *metric_hits])


def _clip(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + exp(-value))
    positive = exp(value)
    return positive / (1.0 + positive)


def fit(
    cases: Iterable[tuple[Incident, str, str | None]],
    *,
    l2: float = 0.5,
    learning_rate: float = 0.2,
    epochs: int = 1200,
) -> LearnedWeights:
    """Fit one-vs-rest candidate logistic regression with deterministic full-batch descent."""
    rows: list[tuple[tuple[float, ...], float]] = []
    for incident, root_service, root_deployment in cases:
        for candidate in incident.candidates:
            target = float(
                candidate.service == root_service
                and candidate.kind == ("deployment" if root_deployment else "service_fault")
                and (root_deployment is None or candidate.deployment_id == root_deployment)
            )
            rows.append((candidate_features(incident, candidate), target))
    if not rows:
        return LearnedWeights(WEIGHTS_VERSION, FEATURE_NAMES, (0.0,) * len(FEATURE_NAMES), 0.0, l2)
    weights = [0.0] * len(FEATURE_NAMES)
    intercept = 0.0
    for _ in range(epochs):
        gradients = [0.0] * len(weights)
        intercept_gradient = 0.0
        for features, target in rows:
            probability = _sigmoid(
                intercept
                + sum(weight * value for weight, value in zip(weights, features, strict=True))
            )
            error = probability - target
            intercept_gradient += error
            for index, value in enumerate(features):
                gradients[index] += error * value
        scale = 1.0 / len(rows)
        intercept -= learning_rate * intercept_gradient * scale
        for index, gradient in enumerate(gradients):
            gradients[index] = gradient * scale + l2 * weights[index]
            weights[index] -= learning_rate * gradients[index]
    return LearnedWeights(
        WEIGHTS_VERSION,
        FEATURE_NAMES,
        tuple(round(value, 8) for value in weights),
        round(intercept, 8),
        l2,
    )


def score(incident: Incident, candidate: Candidate, weights: LearnedWeights) -> float:
    features = candidate_features(incident, candidate)
    return _sigmoid(
        weights.intercept
        + sum(weight * value for weight, value in zip(weights.coefficients, features, strict=True))
    )


def rerank_ids(incident: Incident, weights: LearnedWeights | None) -> list[str]:
    """Return candidate IDs in learned order, or preserve engine order without weights."""
    candidates = incident.candidates[:3]
    if weights is None:
        return [candidate.candidate_id for candidate in candidates]
    ranked = sorted(
        candidates,
        key=lambda candidate: (
            -score(incident, candidate, weights),
            candidate.rank,
            candidate.candidate_id,
        ),
    )
    return [candidate.candidate_id for candidate in ranked]


def save(weights: LearnedWeights, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(weights.model_dump(), indent=2) + "\n", encoding="utf-8")


def load(path: Path) -> LearnedWeights | None:
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        value.get("version") != WEIGHTS_VERSION
        or tuple(value.get("feature_names", ())) != FEATURE_NAMES
    ):
        raise ValueError(f"unsupported learned reranker weights in {path}")
    coefficients = tuple(float(item) for item in value["coefficients"])
    if len(coefficients) != len(FEATURE_NAMES):
        raise ValueError(f"invalid learned reranker coefficient count in {path}")
    return LearnedWeights(
        version=value["version"],
        feature_names=FEATURE_NAMES,
        coefficients=coefficients,
        intercept=float(value["intercept"]),
        l2=float(value.get("l2", 0.5)),
    )


def top1_accuracy(
    cases: Iterable[tuple[Incident, str, str | None]], weights: LearnedWeights
) -> float:
    values = list(cases)
    if not values:
        return 0.0
    correct = 0
    for incident, root_service, root_deployment in values:
        ordered = rerank_ids(incident, weights)
        top = next((item for item in incident.candidates if item.candidate_id == ordered[0]), None)
        if (
            top
            and top.service == root_service
            and (root_deployment is None or top.deployment_id == root_deployment)
        ):
            correct += 1
    return correct / len(values)
