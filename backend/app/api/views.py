"""Response builders shared by the API routes and the fixture generator."""

from typing import cast

from app.models.api import ScenarioInfo, ServiceNode, TopologyEdge, TopologyResponse
from app.models.engine import Health
from app.models.topology import Topology
from app.simulator.models import Scenario


def topology_response(topology: Topology, health: dict[str, str] | None = None) -> TopologyResponse:
    health = health or {}
    return TopologyResponse(
        services=[
            ServiceNode(
                name=name,
                kind=definition.kind,
                tier=definition.tier,
                layout=definition.layout,
                customer_facing=definition.tier == "customer_facing",
                health=cast(Health, health.get(name, "healthy")),
            )
            for name, definition in topology.services.items()
        ],
        edges=[
            TopologyEdge(source=e.from_, target=e.to, blocking=e.blocking) for e in topology.edges
        ],
    )


def scenario_info(scenario: Scenario) -> ScenarioInfo:
    """Never includes ground truth."""
    return ScenarioInfo(
        id=scenario.id,
        title=scenario.title,
        description=scenario.description,
        priority=scenario.priority,
        fix_flow_available=any(d.commit_ref == "deploy-182" for d in scenario.deployments),
    )
