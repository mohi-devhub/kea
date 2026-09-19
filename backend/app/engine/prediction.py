"""Pure counterfactual prediction and verification helpers (ENGINE_SPEC §13)."""

from app.models.engine import Incident, Prediction, PredictionVerification


def make_prediction(incident: Incident, made_ts: int) -> Prediction:
    """Freeze a prediction from the incident revision before recovery starts."""
    if not incident.candidates:
        raise ValueError("cannot predict without a root-cause candidate")
    candidate = incident.candidates[0]
    anomaly_services = {anomaly.anomaly_id: anomaly.service for anomaly in incident.anomalies}
    healed_set = {
        anomaly_services[anomaly_id]
        for anomaly_id in candidate.covered_anomaly_ids
        if anomaly_id in anomaly_services
    }
    healed = ([candidate.service] if candidate.service in healed_set else []) + sorted(
        healed_set - {candidate.service}
    )
    unhealthy = {
        service for service, health in incident.service_health.items() if health != "healthy"
    }
    unchanged = sorted(unhealthy - set(healed))
    return Prediction(
        prediction_id=f"P-{incident.incident_id}-{incident.revision}",
        incident_id=incident.incident_id,
        incident_revision=incident.revision,
        candidate_id=candidate.candidate_id,
        low_margin=incident.ambiguous,
        predicted_healed=healed,
        predicted_unchanged=unchanged,
        made_ts=made_ts,
    )


def verify_prediction(
    prediction: Prediction, service_health: dict[str, str], verified_ts: int
) -> PredictionVerification:
    """Compare the frozen prediction with the observed health at recovery."""
    outcomes: list[dict[str, str]] = []
    healed = set(prediction.predicted_healed)
    unchanged = set(prediction.predicted_unchanged)
    for service in sorted(healed | unchanged):
        healthy = service_health.get(service, "healthy") == "healthy"
        if service in healed:
            outcome = "healed_as_predicted" if healthy else "missed_heal"
        else:
            outcome = "unexpected_heal" if healthy else "unchanged_as_predicted"
        outcomes.append({"service": service, "outcome": outcome})

    mismatches = {
        item["outcome"]
        for item in outcomes
        if item["outcome"] in {"missed_heal", "unexpected_heal"}
    }
    top_service_unhealthy = any(
        service in set(prediction.predicted_healed)
        and service_health.get(service, "healthy") != "healthy"
        for service in prediction.predicted_healed[:1]
    )
    if not mismatches:
        verdict = "confirmed"
    elif top_service_unhealthy:
        verdict = "refuted"
    else:
        verdict = "partial"
    return PredictionVerification(
        prediction_id=prediction.prediction_id,
        verdict=verdict,
        outcomes=outcomes,
        verified_ts=verified_ts,
    )
