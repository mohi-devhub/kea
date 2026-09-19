"""Neo4j access: schema constraints and static topology seeding. CONTRACTS.md section 5."""

import json
from pathlib import Path

import yaml
from neo4j import AsyncDriver, AsyncGraphDatabase

from app.config import Settings
from app.models.engine import EngineUpdate, Incident
from app.models.events import Event
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


async def write_event(driver: AsyncDriver, event: Event) -> None:
    if event.kind == "deployment":
        await driver.execute_query(
            "MERGE (d:Deployment {run_id:$run_id, id:$id}) SET d.ts=$ts, d.version=$version, "
            "d.commit_ref=$commit_ref, d.summary=$summary, d.status='active' "
            "WITH d MATCH (s:Service {name:$service}) MERGE (d)-[:CHANGED]->(s)",
            run_id=event.run_id,
            id=event.payload.deployment_id,
            ts=event.ts,
            version=event.payload.version,
            commit_ref=event.payload.commit_ref,
            summary=event.payload.summary,
            service=event.service,
        )
    elif event.kind == "rollback":
        await driver.execute_query(
            "MATCH (d:Deployment {run_id:$run_id, id:$id}) SET d.status='rolled_back'",
            run_id=event.run_id,
            id=event.payload.deployment_id,
        )


async def write_engine_update(
    driver: AsyncDriver, update: EngineUpdate, incident: Incident | None
) -> None:
    if incident is None:
        return
    await driver.execute_query(
        "MERGE (i:Incident {id:$id}) SET i.run_id=$run_id, i.state=$state, i.opened_ts=$opened_ts, "
        "i.resolved_ts=$resolved_ts, i.revision=$revision",
        id=incident.incident_id,
        run_id=incident.run_id,
        state=incident.state,
        opened_ts=incident.opened_ts,
        resolved_ts=incident.resolved_ts,
        revision=incident.revision,
    )
    for anomaly in incident.anomalies:
        await driver.execute_query(
            "MERGE (a:Anomaly {id:$id}) SET a.run_id=$run_id, a.metric=$metric, "
            "a.onset_ts=$onset_ts, "
            "a.detected_ts=$detected_ts, a.resolved_ts=$resolved_ts, a.baseline=$baseline, "
            "a.peak_value=$peak_value, a.ratio=$ratio, a.state=$state "
            "WITH a MATCH (s:Service {name:$service}) MERGE (a)-[:OBSERVED_ON]->(s) "
            "WITH a MATCH (i:Incident {id:$incident_id}) MERGE (i)-[:INCLUDES]->(a)",
            id=anomaly.anomaly_id,
            run_id=anomaly.run_id,
            metric=anomaly.metric,
            onset_ts=anomaly.onset_ts,
            detected_ts=anomaly.detected_ts,
            resolved_ts=anomaly.resolved_ts,
            baseline=anomaly.baseline,
            peak_value=anomaly.peak_value,
            ratio=anomaly.ratio,
            state=anomaly.state,
            service=anomaly.service,
            incident_id=incident.incident_id,
        )
    await driver.execute_query(
        "MATCH (i:Incident {id:$incident_id})-[r:ROOT_CAUSE_CANDIDATE]->() DELETE r",
        incident_id=incident.incident_id,
    )
    for candidate in incident.candidates:
        factors = json.dumps(
            candidate.factors,
            default=lambda value: value.model_dump(),
        )
        if candidate.kind == "deployment":
            await driver.execute_query(
                "MATCH (i:Incident {id:$incident_id}), "
                "(d:Deployment {run_id:$run_id, id:$deployment_id}) "
                "MERGE (i)-[r:ROOT_CAUSE_CANDIDATE]->(d) "
                "SET r.rank=$rank, r.score=$score, r.factors_json=$factors",
                incident_id=incident.incident_id,
                run_id=incident.run_id,
                deployment_id=candidate.deployment_id,
                rank=candidate.rank,
                score=candidate.score,
                factors=factors,
            )
        else:
            await driver.execute_query(
                "MATCH (i:Incident {id:$incident_id}), "
                "(s:Service {name:$service}) "
                "MERGE (i)-[r:ROOT_CAUSE_CANDIDATE]->(s) "
                "SET r.rank=$rank, r.score=$score, r.factors_json=$factors",
                incident_id=incident.incident_id,
                service=candidate.service,
                rank=candidate.rank,
                score=candidate.score,
                factors=factors,
            )


async def reset_runs(driver: AsyncDriver) -> None:
    await driver.execute_query(
        "MATCH (n) WHERE n:Deployment OR n:Anomaly OR n:Incident DETACH DELETE n"
    )


async def traverse(
    driver: AsyncDriver, service: str, direction: str, depth: int
) -> list[dict[str, object]]:
    if direction == "upstream":
        query = (
            f"MATCH p=(s:Service {{name:$service}})<-[:CALLS*1..{depth}]-(d:Service) "
            "RETURN DISTINCT d.name AS service, min(length(p)) AS hops"
        )
    else:
        query = (
            f"MATCH p=(s:Service {{name:$service}})-[:CALLS*1..{depth}]->(d:Service) "
            "RETURN DISTINCT d.name AS service, min(length(p)) AS hops"
        )
    records, _, _ = await driver.execute_query(query, service=service, depth=depth)
    return [dict(record) for record in records]


BLAST_CYPHER = (
    "MATCH p=(c:Service)-[:CALLS*1..4]->(s:Service {name:$service}) "
    "WHERE all(r IN relationships(p) WHERE r.blocking) "
    "RETURN DISTINCT c.name AS service, c.customer_facing AS customer_facing, "
    "min(length(p)) AS hops ORDER BY hops, service"
)


async def blast_callers(driver: AsyncDriver, service: str) -> list[dict[str, object]]:
    """Live blast radius: services whose blocking call chain reaches `service`."""
    records, _, _ = await driver.execute_query(BLAST_CYPHER, service=service)
    return [dict(record) for record in records]
