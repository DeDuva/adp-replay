"""Evidence-gated verdicts.

Task 3.3 — a verdict is admissible only with resolvable scorer identity and
verifiable step evidence.
"""

from adp_replay.verdict.gating import Verdict, gate_verdict

__all__ = ["Verdict", "gate_verdict"]
