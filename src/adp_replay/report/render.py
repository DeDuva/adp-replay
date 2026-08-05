"""Report rendering (Task 3.2).

State completeness and median context fidelity go in the **header** of every
report. Both are limits on what the numbers below them mean, and a limit that
appears after the conclusion has already been read is not a limit.
"""

from __future__ import annotations

from typing import Any


def render_json(results: Any) -> str:
    """Render results as JSON, against a documented schema."""
    raise NotImplementedError("Task 3.2 — reports")


def render_html(results: Any) -> str:
    """Render a self-contained HTML report — no external asset references."""
    raise NotImplementedError("Task 3.2 — reports")
