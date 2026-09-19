"""Print the M1 tuning-seed scenario matrix without requiring infrastructure."""
# ruff: noqa: E501

from app.config import get_settings
from app.engine import InMemoryTopology, run_batch
from app.graph.client import load_topology
from app.simulator.generator import generate
from app.simulator.loader import load_scenarios


def main() -> None:
    settings = get_settings()
    topology = load_topology(settings.topology_path)
    scenarios = load_scenarios(settings.topology_path.parent, topology)
    failed = False
    for scenario in scenarios:
        for seed in range(5):
            result = run_batch(generate(scenario, topology, seed), InMemoryTopology(topology))
            actual = result.candidates[0].candidate_id if result.candidates else "no incident"
            truth = scenario.ground_truth
            if not truth.expect_incident:
                expected = "no incident"
            else:
                assert truth.root_cause is not None
                expected = (
                    f"{truth.root_cause.kind}:"
                    f"{truth.root_cause.deployment_id or truth.root_cause.service}"
                )
            passed = actual == expected
            print(f"{scenario.id:28} seed {seed}: {'PASS' if passed else 'FAIL'} ({actual})")
            failed = failed or not passed
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
