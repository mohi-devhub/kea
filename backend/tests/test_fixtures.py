"""Fixtures must follow the WebSocket contract (CONTRACTS.md section 4) so the UI never drifts."""

from typing import get_args

from app.config import get_settings
from app.graph.client import load_topology
from app.models.api import WsEnvelope, WsType
from app.models.engine import Anomaly, Incident, Prediction
from app.simulator.loader import load_scenarios
from scripts.gen_fixtures import SEED, build_messages


def _messages(scenario_id: str) -> list[dict]:  # type: ignore[type-arg]
    settings = get_settings()
    topology = load_topology(settings.topology_path)
    scenario = next(
        s for s in load_scenarios(settings.topology_path.parent, topology) if s.id == scenario_id
    )
    return build_messages(scenario, topology, SEED)


def test_fixture_messages_match_contract() -> None:
    messages = _messages("s1_bad_deploy_payment")
    assert messages[0]["type"] == "run.started"
    assert [m["seq"] for m in messages] == list(range(len(messages)))
    for message in messages:
        WsEnvelope.model_validate(message)
        assert message["type"] in get_args(WsType)
        if message["type"].startswith("anomaly."):
            Anomaly.model_validate(message["payload"])
        if message["type"].startswith("incident."):
            Incident.model_validate(message["payload"])
        if message["type"] == "prediction.made":
            Prediction.model_validate(message["payload"])
    kinds = {m["type"] for m in messages}
    assert {"metrics.batch", "sim.clock", "deployment.observed", "service.health"} <= kinds
    assert {"anomaly.opened", "incident.opened", "incident.updated"} <= kinds
    assert {"prediction.made", "prediction.verified", "incident.resolved", "run.stopped"} <= kinds
    order = [m["type"] for m in messages]
    assert order.index("prediction.made") < order.index("incident.resolved")
    verified = next(m for m in messages if m["type"] == "prediction.verified")
    assert verified["payload"]["verdict"] == "confirmed"
    rollback = [
        m
        for m in messages
        if m["type"] == "deployment.observed" and m["payload"]["kind"] == "rollback"
    ]
    assert [m["payload"]["payload"]["deployment_id"] for m in rollback] == ["dep-182"]


def test_fixtures_are_deterministic() -> None:
    assert _messages("s3_red_herring_deploy") == _messages("s3_red_herring_deploy")
