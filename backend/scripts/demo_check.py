"""End-to-end smoke of S1-S4 through the running stack (`make up` first). Exit 1 on any failure."""

import sys
import time

import httpx

BASE = "http://localhost:8000"
EXPECT = {  # scenario -> (top candidate, rejected decoy) ; None = no incident expected
    "s1_bad_deploy_payment": ("deployment:dep-182", None),
    "s2_postgres_degradation": ("service_fault:postgres", "deployment:dep-171"),
    "s3_red_herring_deploy": ("service_fault:redis", "deployment:dep-203"),
    "s4_benign_deploy": None,
}


def wait(predicate, timeout: float):  # type: ignore[no-untyped-def]
    end = time.time() + timeout
    while time.time() < end:
        if (value := predicate()) is not None:
            return value
        time.sleep(0.25)
    return None


def check(client: httpx.Client, scenario: str) -> list[str]:
    problems: list[str] = []
    expected = EXPECT[scenario]
    speed = 10 if expected else 100
    run_id = client.post(f"/simulate/{scenario}", json={"seed": 42, "speed": speed}).json()[
        "run_id"
    ]
    if expected is None:
        done = wait(
            lambda: True if client.get(f"/runs/{run_id}").json()["status"] == "completed" else None,
            90,
        )
        if not done:
            problems.append("run never completed")
        if client.get("/incidents").json():
            problems.append("benign scenario opened an incident")
        return problems
    top, decoy = expected
    incident = wait(lambda: (client.get("/incidents").json() or [None])[0], 60)
    if incident is None:
        return ["no incident opened within 60s"]
    if incident["candidates"][0]["candidate_id"] != top:
        problems.append(f"top candidate {incident['candidates'][0]['candidate_id']} != {top}")
    if decoy and decoy not in {r["candidate_id"] for r in incident["rejected_candidates"]}:
        problems.append(f"{decoy} not rejected")
    iid = incident["incident_id"]
    if client.get(f"/incidents/{iid}/prediction").json().get("frozen") is not False:
        problems.append("prediction preview missing before recover")
    if client.post(f"/runs/{run_id}/recover").status_code != 200:
        return [*problems, "recover failed"]
    resolved = wait(
        lambda: True if client.get(f"/incidents/{iid}").json()["state"] == "resolved" else None, 60
    )
    if not resolved:
        return [*problems, "incident did not resolve after recover"]
    verdict = (client.get(f"/incidents/{iid}/prediction").json().get("verification") or {}).get(
        "verdict"
    )
    if verdict != "confirmed":
        problems.append(f"prediction verdict {verdict}")
    return problems


def main() -> int:
    failed = False
    with httpx.Client(base_url=BASE, timeout=30) as client:
        if client.get("/health").json() != {"status": "ok", "kafka": True, "neo4j": True}:
            print("stack not healthy; run `make up`")
            return 1
        for scenario in EXPECT:
            client.post("/reset")
            started = time.time()
            problems = check(client, scenario)
            print(
                f"{'FAIL' if problems else 'PASS'} {scenario} "
                f"({time.time() - started:.0f}s) {'; '.join(problems)}"
            )
            failed = failed or bool(problems)
        client.post("/reset")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
