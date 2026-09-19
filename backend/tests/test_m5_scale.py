from app.engine import InMemoryTopology, run_batch
from app.eval.runner import EvalRunner
from app.eval.scale import SWEEP, build_scaled
from app.simulator.generator import generate
from app.simulator.loader import validate_scenario


def test_scaled_scenarios_are_valid_and_engine_finds_the_root() -> None:
    for width in SWEEP:
        topology, scenario = build_scaled(width)
        assert len(topology.services) == 5 + 2 * width
        validate_scenario(scenario, topology)
        incident = run_batch(generate(scenario, topology, 0), InMemoryTopology(topology)).incident
        assert incident is not None and incident.candidates[0].service == "postgres"


def test_runner_accepts_a_swapped_topology() -> None:
    runner = EvalRunner()
    runner.topology, _ = build_scaled(1)
    assert len(runner.topology.services) == 7
