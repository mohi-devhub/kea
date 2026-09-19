"""Needs `make up`. Run with `make test-int`."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

pytestmark = pytest.mark.integration


async def test_health_and_topology() -> None:
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            h = (await c.get("/health")).json()
            assert h == {"status": "ok", "kafka": True, "neo4j": True}
            assert len((await c.get("/topology")).json()["services"]) == 8
            assert (await c.get("/scenarios")).json() == []
        rec, _, _ = await app.state.driver.execute_query("MATCH (s:Service) RETURN count(s) AS n")
        assert rec[0]["n"] == 8
