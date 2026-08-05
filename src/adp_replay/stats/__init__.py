"""Power analysis and paired statistics.

Task 0.4 — simulation-based power analysis; sets the corpus size.
Task 3.1 — exact McNemar, bootstrap CIs over tasks, ICC and variance decomposition.
"""

from adp_replay.stats.paired import bootstrap_ci_over_tasks, mcnemar_exact
from adp_replay.stats.power import PowerRecommendation, recommend_design

__all__ = [
    "PowerRecommendation",
    "bootstrap_ci_over_tasks",
    "mcnemar_exact",
    "recommend_design",
]
