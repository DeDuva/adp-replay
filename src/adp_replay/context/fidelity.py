"""Context-fidelity scoring (Tasks 0.3a and 0.3b).

Gate G0 requires median fidelity >= 0.85. The threshold and the metric's
definition are pre-registered in ``docs/pre-registration.md`` **before** this
module is written: a metric whose pass mark is settled by the same work that
measures against it can be shaped to clear its own bar.

Implementations here must read the pre-registered definition, not restate it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FidelityScore:
    """One provider pair's fidelity, and what accounts for the shortfall."""

    score: float
    preserved: tuple[str, ...] = ()
    transformed: tuple[str, ...] = ()
    lost: tuple[str, ...] = ()
    notes: dict[str, Any] = field(default_factory=dict)


def score_fidelity(source_context: Any, target_context: Any) -> FidelityScore:
    """Score how much of ``source_context`` survives translation to the target.

    Task 0.3b.
    """
    raise NotImplementedError("Task 0.3b — fidelity probe")
