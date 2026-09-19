"""Scenario loader and validation; only this package reads scenario YAML."""

from pathlib import Path

import yaml

from app.models.topology import Topology
from app.simulator.models import Scenario


def load_scenarios(directory: Path, topology: Topology) -> list[Scenario]:
    scenarios = [
        Scenario.model_validate(yaml.safe_load(path.read_text()))
        for path in sorted(directory.glob("s[1-9]_*.yaml"))
    ]
    for scenario in scenarios:
        validate_scenario(scenario, topology)
    return scenarios


def validate_scenario(scenario: Scenario, topology: Topology) -> None:
    services = set(topology.services)
    for deployment in scenario.deployments:
        if deployment.service not in services:
            raise ValueError(f"{scenario.id}: unknown deployment service {deployment.service}")
    for effect in scenario.effects:
        if effect.service not in services or effect.metric not in topology.metrics[effect.service]:
            raise ValueError(f"{scenario.id}: invalid effect {effect.service}.{effect.metric}")
        if (effect.target_multiplier is None) == (effect.target_value is None):
            raise ValueError(f"{scenario.id}: effect needs exactly one target")
    for first, second in scenario.ground_truth.ordering_constraints:
        a = next(e for e in scenario.effects if f"{e.service}.{e.metric}" == first)
        b = next(e for e in scenario.effects if f"{e.service}.{e.metric}" == second)
        if b.start_s - a.start_s - 8 < 10:
            raise ValueError(f"{scenario.id}: jitter makes {first} and {second} too close")
