"""Canonical context form and the context-fidelity probe.

Task 0.3a — define and pre-register the fidelity metric.
Task 0.3b — implement the probe.
"""

from adp_replay.context.fidelity import FidelityScore, score_fidelity

__all__ = ["FidelityScore", "score_fidelity"]
