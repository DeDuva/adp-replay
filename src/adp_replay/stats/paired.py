"""Paired statistics (Task 3.1).

:func:`mcnemar_exact` landed early, with Task 0.4: a simulation-based power
analysis has to run the test it is computing power *for*, and powering a design
against one test while planning to report another is how a study arrives
underpowered on the day. The rest of this module fills in with Task 3.1.
"""

from __future__ import annotations

from collections.abc import Sequence
from math import comb


def mcnemar_exact(both_pass: int, a_only: int, b_only: int, both_fail: int) -> float:
    """Exact McNemar p-value for paired pass/fail outcomes.

    Only the discordant pairs carry information: a task both models solved, or
    neither did, says nothing about which is better. Conditional on the number
    of discordant pairs, the null is that each one falls either way with equal
    probability, so this is an exact two-sided binomial test at p = 0.5.

    Exact rather than the chi-square approximation because the discordant count
    is the sample size here, not the number of tasks. A 60-task corpus can
    easily produce eight discordant pairs, and the approximation is not
    trustworthy there — which is exactly the regime a small corpus lives in.
    """
    for name, value in (
        ("both_pass", both_pass),
        ("a_only", a_only),
        ("b_only", b_only),
        ("both_fail", both_fail),
    ):
        if value < 0:
            raise ValueError(f"{name} must not be negative")

    discordant = a_only + b_only
    if discordant == 0:
        # No evidence either way. Reporting 1.0 rather than raising keeps a
        # sweep over many tasks from turning "these models tied everywhere"
        # into an exception.
        return 1.0

    smaller = min(a_only, b_only)
    tail: float = sum(comb(discordant, k) for k in range(smaller + 1)) / 2**discordant
    return min(1.0, 2.0 * tail)


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
