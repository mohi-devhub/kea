"""Read-only tools exposed to the agent.

The registry is deliberately explicit: adding a mutating tool requires a
separate contract review instead of silently expanding agent capabilities.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.api.store import RunView
from app.llm.models import ToolSpec
from app.models.topology import Topology


@dataclass(frozen=True)
class AgentTool:
    spec: ToolSpec
    handler: Callable[[dict[str, Any]], dict[str, Any]]
    read_only: bool = True


class ToolContext:
    def __init__(self, view: RunView, topology: Topology) -> None:
        self.view = view
        self.topology = topology

    def incident(self, _: dict[str, Any]) -> dict[str, Any]:
        return self.view.incident.model_dump(mode="json") if self.view.incident else {}

    def timeline(self, _: dict[str, Any]) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        for event in self.view.events:
            if event.kind in {"deployment", "rollback", "log"}:
                items.append(
                    {"type": event.kind, "ts": event.ts, "payload": event.model_dump(mode="json")}
                )
        return {"items": items}

    def deployments(self, _: dict[str, Any]) -> dict[str, Any]:
        return {"deployments": list(self.view.deployments[-100:])}

    def metrics(self, args: dict[str, Any]) -> dict[str, Any]:
        service = args.get("service")
        metric = args.get("metric")
        points = [
            point
            for (point_service, point_metric), values in self.view.metrics.items()
            if (service is None or point_service == service)
            and (metric is None or point_metric == metric)
            for point in values
        ]
        return {"points": points[-200:]}

    def logs(self, args: dict[str, Any]) -> dict[str, Any]:
        service = args.get("service")
        logs = [
            item for item in self.view.logs if service is None or item.get("service") == service
        ]
        return {"logs": logs[-100:]}

    def service_graph(self, _: dict[str, Any]) -> dict[str, Any]:
        return {
            "services": list(self.topology.services),
            "edges": [edge.model_dump(mode="json", by_alias=True) for edge in self.topology.edges],
        }

    def traverse(self, args: dict[str, Any]) -> dict[str, Any]:
        service = str(args.get("service", ""))
        direction = str(args.get("direction", "downstream"))
        edges = self.topology.edges
        if direction == "upstream":
            nodes = [edge.from_ for edge in edges if edge.to == service]
        else:
            nodes = [edge.to for edge in edges if edge.from_ == service]
        return {"service": service, "direction": direction, "nodes": sorted(set(nodes))}

    def registry(self) -> dict[str, AgentTool]:
        def spec(name: str, description: str, parameters: dict[str, Any] | None = None) -> ToolSpec:
            return ToolSpec(
                name=name, description=description, parameters=parameters or {"type": "object"}
            )

        return {
            "get_incident": AgentTool(
                spec("get_incident", "Read the current incident and engine ranking."), self.incident
            ),
            "get_incident_timeline": AgentTool(
                spec("get_incident_timeline", "Read incident timeline events."), self.timeline
            ),
            "get_recent_deployments": AgentTool(
                spec("get_recent_deployments", "Read observed deployments."), self.deployments
            ),
            "get_service_metrics": AgentTool(
                spec("get_service_metrics", "Read metrics for a service."), self.metrics
            ),
            "get_logs": AgentTool(spec("get_logs", "Read structured logs."), self.logs),
            "get_service_graph": AgentTool(
                spec("get_service_graph", "Read the static service graph."), self.service_graph
            ),
            "get_downstream_services": AgentTool(
                spec("get_downstream_services", "Read downstream dependencies."), self.traverse
            ),
            "get_upstream_services": AgentTool(
                spec("get_upstream_services", "Read upstream callers."), self.traverse
            ),
        }
