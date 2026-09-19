"""Raw telemetry baseline input rendering and output parsing.

This package deliberately has no dependency on the simulator or scenario ground truth.
"""

from app.eval.baselines.parser import parse_output
from app.eval.baselines.render import render_baseline_input

__all__ = ["parse_output", "render_baseline_input"]
