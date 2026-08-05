"""Evidence gating (Task 3.3).

ADP answers this in one call: ``GET /runs/{runId}/verify`` returns a single
``ok`` alongside the sub-checks that produced it — ``chains_ok`` (the events ADP
holds were not edited), ``emitters_ok`` (ADP was given all of them),
``envelope_verified``, ``trajectory_digest_matches``, and per-eval
``separately_authorized``.

If ``ok`` is false the verdict becomes ERROR. An unverifiable result is never
counted as a pass or a fail — silently scoring one is how unverifiable evidence
ends up in a published table. The failing sub-check is recorded so a downgrade
can be diagnosed rather than merely observed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Verdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"


@dataclass(frozen=True)
class GatedVerdict:
    verdict: Verdict
    # Populated when the verdict was downgraded: which sub-check of the ADP
    # verify response failed.
    downgraded_because: tuple[str, ...] = ()


def gate_verdict(scored: Verdict, verify_response: dict[str, Any]) -> GatedVerdict:
    """Downgrade ``scored`` to ERROR unless the run's evidence verifies.

    Task 3.3.
    """
    raise NotImplementedError("Task 3.3 — evidence gating")
