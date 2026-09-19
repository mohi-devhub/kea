"""Needs `make up`. Run with `make test-int`."""

import asyncio

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
            scenarios = (await c.get("/scenarios")).json()
            assert {item["id"] for item in scenarios} == {
                "s1_bad_deploy_payment",
                "s2_postgres_degradation",
                "s3_red_herring_deploy",
                "s4_benign_deploy",
            }
        rec, _, _ = await app.state.driver.execute_query("MATCH (s:Service) RETURN count(s) AS n")
        assert rec[0]["n"] == 8


async def test_live_s1_pipeline_reset_and_second_run() -> None:
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            response = await client.post(
                "/simulate/s1_bad_deploy_payment",
                json={"seed": 42, "speed": 10_000, "skip_warmup": True},
            )
            run_id = response.json()["run_id"]
            incident_id = None
            for _ in range(100):
                incidents = (await client.get("/incidents")).json()
                if incidents:
                    incident_id = incidents[0]["incident_id"]
                    break
                await asyncio.sleep(0.1)
            assert incident_id is not None
            assert (await client.get(f"/runs/{run_id}/metrics")).status_code == 200
            assert (await client.get(f"/incidents/{incident_id}/timeline")).status_code == 200
            preview = (await client.get(f"/incidents/{incident_id}/prediction")).json()
            assert preview["frozen"] is False and preview["candidate_id"] == "deployment:dep-182"
            assert (
                await client.get(
                    f"/incidents/{incident_id}/causal-path",
                    params={"candidate": "deployment:dep-182"},
                )
            ).status_code == 200
            assert (await client.get(f"/incidents/{incident_id}/blast-radius")).status_code == 200
            assert (await client.post(f"/runs/{run_id}/recover")).status_code == 200
            prediction = (await client.get(f"/incidents/{incident_id}/prediction")).json()
            assert prediction["candidate_id"] == "deployment:dep-182"
            assert prediction["frozen"] is True and prediction["verification"] is None
            for _ in range(200):
                current = (await client.get(f"/incidents/{incident_id}")).json()
                if current.get("state") == "resolved":
                    break
                await asyncio.sleep(0.1)
            assert current["state"] == "resolved"
            timeline = (await client.get(f"/incidents/{incident_id}/timeline")).json()
            rollbacks = [
                i["payload"]["payload"]["deployment_id"]
                for i in timeline
                if i["type"] == "rollback"
            ]
            assert rollbacks == ["dep-182"]
            verified = (await client.get(f"/incidents/{incident_id}/prediction")).json()
            assert verified["verification"]["verdict"] == "confirmed"
            assert (await client.post("/reset")).json() == {"status": "ok"}
            assert (await client.get("/incidents")).json() == []
            second = await client.post(
                "/simulate/s1_bad_deploy_payment",
                json={"seed": 43, "speed": 10_000, "skip_warmup": True},
            )
            assert second.status_code == 200


async def test_s2_recovery_fixes_postgres_not_the_decoy_deploy() -> None:
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            await client.post("/reset")
            run_id = (
                await client.post(
                    "/simulate/s2_postgres_degradation",
                    json={"seed": 42, "speed": 10_000, "skip_warmup": True},
                )
            ).json()["run_id"]
            incident_id = None
            for _ in range(100):
                incidents = (await client.get("/incidents")).json()
                if incidents:
                    incident_id = incidents[0]["incident_id"]
                    break
                await asyncio.sleep(0.1)
            assert incident_id is not None
            assert (await client.post(f"/runs/{run_id}/recover")).status_code == 200
            for _ in range(300):
                if (await client.get(f"/incidents/{incident_id}")).json()["state"] == "resolved":
                    break
                await asyncio.sleep(0.1)
            timeline = (await client.get(f"/incidents/{incident_id}/timeline")).json()
            assert not [i for i in timeline if i["type"] == "rollback"]
            assert [i for i in timeline if i["type"] == "log"]
            verified = (await client.get(f"/incidents/{incident_id}/prediction")).json()
            assert verified["candidate_id"] == "service_fault:postgres"
            assert verified["verification"]["verdict"] == "confirmed"
            blast = (await client.get(f"/incidents/{incident_id}/blast-radius")).json()
            assert blast["root_service"] == "postgres" and blast["callers"]
            await client.post("/reset")
