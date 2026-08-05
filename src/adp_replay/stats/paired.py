"""Paired statistics (Task 3.1)."""

from __future__ import annotations

from collections.abc import Sequence


def mcnemar_exact(both_pass: int, a_only: int, b_only: int, both_fail: int) -> float:
    """Exact McNemar p-value for paired pass/fail outcomes."""
    raise NotImplementedError("Task 3.1 — paired statistics")


def bootstrap_ci_over_tasks(
    per_task_outcomes: Sequence[Sequence[bool]],
    *,
    resamples: int = 10_000,
    confidence: float = 0.95,
) -> tuple[float, float]:
    """Bootstrap CI resampling **tasks**, never individual trajectories.

    Trajectories within a task are not independent samples. Resampling them
    directly treats correlated repetitions as fresh evidence and inflates
    significance — this is the single easiest way to publish a result that does
    not replicate, so the unit of resampling is fixed here by signature: the
    outer sequence is tasks, and it is the only thing resampled.
    """
    raise NotImplementedError("Task 3.1 — paired statistics")


def icc(per_task_outcomes: Sequence[Sequence[bool]]) -> float:
    """Intraclass correlation: how much variance sits between tasks vs within."""
    raise NotImplementedError("Task 3.1 — paired statistics")
