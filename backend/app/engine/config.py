"""Engine defaults from ENGINE_SPEC.md. Every tunable number lives here."""

from dataclasses import dataclass


@dataclass(frozen=True)
class EngineConfig:
    # detection (ENGINE_SPEC section 2)
    baseline_window: int = 24
    min_baseline_samples: int = 12
    consecutive_samples: int = 3
    latency_ratio: float = 2.0
    latency_floor: float = 1.0
    error_rate_min: float = 0.02
    error_rate_ratio: float = 4.0
    error_rate_baseline_floor: float = 0.002
    error_rate_ratio_floor: float = 0.005
    connections_ratio: float = 1.8
    memory_delta_pts: float = 15.0
    # incidents and causality (sections 4-6)
    delta_s: int = 5
    epsilon_s: int = 5
    lookback_s: int = 240
    merge_hops: int = 3  # ponytail: reserved, incident merge by proximity not implemented yet
    resolve_hold_s: int = 30
    # scoring (section 8): temporal, dependency_consistency, anomaly_strength, downstream_impact
    weights: tuple[float, float, float, float] = (0.30, 0.35, 0.15, 0.20)
    temporal_tau_s: int = 90
    strength_scale: float = 3.0
    ambiguity_margin: float = 0.08
