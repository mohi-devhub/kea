"""Neo4j access: schema constraints and static topology seeding. CONTRACTS.md section 5."""

from pathlib import Path

import yaml
from neo4j import AsyncDriver, AsyncGraphDatabase

from app.config import Settings
from app.models.topology import Topology

CONSTRAINTS = [
    "CREATE CONSTRAINT service_name IF NOT EXISTS FOR (s:Service) REQUIRE s.name IS UNIQUE",
    "CREATE CONSTRAINT deployment_key IF NOT EXISTS "
    "FOR (d:Deployment) REQUIRE (d.run_id, d.id) IS UNIQUE",
    "CREATE CONSTRAINT anomaly_id IF NOT EXISTS FOR (a:Anomaly) REQUIRE a.id IS UNIQUE",
    "CREATE CONSTRAINT incident_id IF NOT EXISTS FOR (i:Incident) REQUIRE i.id IS UNIQUE",
]


def load_topology(path: Path) -> Topology:
    return Topology.model_validate(yaml.safe_load(path.read_text()))


def make_driver(s: Settings) -> AsyncDriver:
    return AsyncGraphDatabase.driver(s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password))


async def ping(driver: AsyncDriver) -> bool:
    try:
        await driver.verify_connectivity()
        return True
    except Exception:
        return False


async def init_schema(driver: AsyncDriver) -> None:
    for stmt in CONSTRAINTS:
        await driver.execute_query(stmt)


async def seed_topology(driver: AsyncDriver, topo: Topology) -> None:
    """Idempotent: MERGE services and CALLS edges from the topology file."""
    for name, svc in topo.services.items():
        await driver.execute_query(
            "MERGE (s:Service {name:$name}) SET s.kind=$kind, s.tier=$tier, "
            "s.customer_facing=$cf, s.layout_x=$x, s.layout_y=$y",
            name=name, kind=svc.kind, tier=svc.tier, cf=svc.tier == "customer_facing",
            x=svc.layout.x, y=svc.layout.y,
        )  # fmt: skip
    for e in topo.edges:
        await driver.execute_query(
            "MATCH (a:Service {name:$a}), (b:Service {name:$b}) "
            "MERGE (a)-[r:CALLS]->(b) SET r.blocking=$blocking",
            a=e.from_, b=e.to, blocking=e.blocking,
        )  # fmt: skip
