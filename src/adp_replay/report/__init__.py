"""Self-contained HTML and JSON reports.

Task 3.2 — state completeness and median context fidelity appear in the header
of every report, not in an appendix.
"""

from adp_replay.report.render import render_html, render_json

__all__ = ["render_html", "render_json"]
