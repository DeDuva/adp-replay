"""Fork-at-zero (Task 2.1) and fork-at-step (Task 2.2)."""

from __future__ import annotations

from typing import Any

# Carried verbatim by every artifact, report, and console run that includes
# fork-at-step results. Not suppressible by configuration: the whole reason the
# banner exists is that a continuation diagnostic reads like a model comparison
# to anyone who did not run it, and the one place it would be most tempting to
# omit is the summary someone actually quotes.
CONTINUATION_BANNER = (
    "Continuation diagnostic: measures Model B's ability to continue Model A's "
    "trajectory prefix. Not a pinned-harness model comparison."
)


class ScorerMismatchError(RuntimeError):
    """Raised when results carrying different scorer digests would be compared.

    Scorer identity is ADP's ``spec_digest`` on the eval. Two results produced by
    different scorers are not comparable, and aggregating them anyway is how an
    eval-gated result reports the wrong winner.
    """


def fork_at_zero(task: Any, model: str, repetitions: int) -> Any:
    """Replay ``task`` from its initial state under ``model``, harness pinned.

    Task 2.1.
    """
    raise NotImplementedError("Task 2.1 — fork-at-zero replay")


def fork_at_step(trajectory: Any, step: int, model: str) -> Any:
    """Resume ``trajectory`` from ``step`` under ``model``.

    Task 2.2. Results carry :data:`CONTINUATION_BANNER`.
    """
    raise NotImplementedError("Task 2.2 — fork-at-step diagnostic")
