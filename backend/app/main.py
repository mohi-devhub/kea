"""FastAPI app factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import yaml
from fastapi import FastAPI

from app.config import ROOT, get_settings
from app.graph import client as graph
from app.models.api import (
    HealthResponse,
    ScenarioInfo,
    ServiceNode,
    TopologyEdge,
    TopologyResponse,
)
from app.stream import kafka


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    s = get_settings()
    app.state.settings = s
    app.state.topology = graph.load_topology(s.topology_path)
    app.state.driver = graph.make_driver(s)
    if await graph.ping(app.state.driver):
        await graph.init_schema(app.state.driver)
        await graph.seed_topology(app.state.driver, app.state.topology)
    yield
    await app.state.driver.close()


def create_app() -> FastAPI:
    app = FastAPI(title="kea", lifespan=lifespan)

    @app.get("/health")
    async def health() -> HealthResponse:
        k = await kafka.ping(app.state.settings.kafka_bootstrap)
        n = await graph.ping(app.state.driver)
        return HealthResponse(status="ok" if k and n else "degraded", kafka=k, neo4j=n)

    @app.get("/topology")
    async def topology() -> TopologyResponse:
        t = app.state.topology
        return TopologyResponse(
            services=[
                ServiceNode(
                    name=n, kind=d.kind, tier=d.tier, layout=d.layout,
                    customer_facing=d.tier == "customer_facing",
                )
                for n, d in t.services.items()
            ],
            edges=[TopologyEdge(source=e.from_, target=e.to, blocking=e.blocking) for e in t.edges],
        )  # fmt: skip

    @app.get("/scenarios")
    async def scenarios() -> list[ScenarioInfo]:
        out: list[ScenarioInfo] = []
        for f in sorted((ROOT / "scenarios").glob("*.yaml")):
            if f.name == "topology.yaml":
                continue
            d = yaml.safe_load(f.read_text())
            out.append(
                ScenarioInfo(
                    id=d["id"], title=d["title"], description=d["description"],
                    priority=d["priority"], fix_flow_available=d.get("fix_flow_available", False),
                )
            )  # fmt: skip
        return out

    return app


app = create_app()
