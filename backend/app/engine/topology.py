"""In-memory topology adapter used by batch mode and tests."""
# ruff: noqa: E501

from collections import deque

from app.models.topology import Topology


class InMemoryTopology:
    def __init__(self, topology: Topology) -> None:
        self.topology = topology

    def callers(self, service: str, depth: int, blocking_only: bool = True) -> dict[str, int]:
        return self._walk(service, depth, reverse=True, blocking_only=blocking_only)

    def callees(self, service: str, depth: int) -> dict[str, int]:
        return self._walk(service, depth, reverse=False, blocking_only=False)

    def _walk(self, service: str, depth: int, reverse: bool, blocking_only: bool) -> dict[str, int]:
        found: dict[str, int] = {}
        queue: deque[tuple[str, int]] = deque([(service, 0)])
        while queue:
            current, hops = queue.popleft()
            if hops == depth:
                continue
            for edge in self.topology.edges:
                if blocking_only and not edge.blocking:
                    continue
                source, target = (edge.to, edge.from_) if reverse else (edge.from_, edge.to)
                if source == current and target not in found:
                    found[target] = hops + 1
                    queue.append((target, hops + 1))
        return found

    def related(self, first: str, second: str, depth: int) -> bool:
        return second in self.callers(first, depth, False) or second in self.callees(first, depth)

    def tier_weight(self, service: str) -> float:
        return {"customer_facing": 1.0, "edge": 0.5, "internal": 0.3, "data": 0.3}[
            self.topology.services[service].tier
        ]
