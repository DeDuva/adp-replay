"""Simulation-based power analysis (Task 0.4).

This task sets the corpus size. Task 1.3's closure audit takes its target from
here and audits at least 1.25x it to absorb attrition — fixing a corpus size
before this reports means re-running the audit when the number moves.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PowerRecommendation:
    """The smallest design reaching the target power."""

    tasks: int
    repetitions: int
    power: float
    assumed_effect_size: float
    assumed_variance: float


def recommend_design(
    target_power: float = 0.8,
    *,
    effect_size: float,
    variance: float,
) -> PowerRecommendation:
    """Smallest (T, n) achieving ``target_power``.

    Task 0.4. Emit a sensitivity curve around both assumptions alongside the
    point recommendation — a design that only holds at one assumed effect size
    is a number, not a result.
    """
    raise NotImplementedError("Task 0.4 — power analysis")
