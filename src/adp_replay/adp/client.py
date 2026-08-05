"""Hand-written wrapper over the generated ADP client.

Only the surfaces docs/execution-plan.md §2 lists are exposed. Keeping the
wrapper narrow is deliberate: it is the seam that absorbs an ADP rewrite, and a
wrapper that re-exports everything absorbs nothing.
"""

from __future__ import annotations

from typing import Any


class AdpClient:
    """Client for ADP's native plane.

    Two identities are required, not one. A score is independent evidence only
    when the identity that reported it is not the identity that did the work —
    ADP reports this as ``separately_authorized``. Passing the same token for
    both collapses that distinction into a self-report that still looks like a
    score, so the runner asserts they differ before any spend (Task 2.3).
    """

    def __init__(self, base_url: str, *, runner_token: str, scorer_token: str) -> None:
        self.base_url = base_url
        self._runner_token = runner_token
        self._scorer_token = scorer_token

    def create_run(self, owner: str, repo: str, **fields: Any) -> dict[str, Any]:
        """POST /api/adp/repos/{owner}/{repo}/runs"""
        raise NotImplementedError("§2 — ADP client")

    def append_events(
        self, owner: str, repo: str, session_id: str, events: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """POST .../sessions/{id}/events — batched; carries ``producer_seq``.

        Returns the append receipt, including ``accepted_through`` and, on a 409,
        ``expected_next_seq`` (Task 1.4).
        """
        raise NotImplementedError("§2 — ADP client")

    def create_checkpoint(
        self, owner: str, repo: str, session_id: str, *, git_sha: str, state: Any
    ) -> dict[str, Any]:
        """POST .../sessions/{id}/checkpoints — attests a snapshot digest.

        ``state`` is opaque to ADP and never parsed by it, so the snapshot
        manifest format stays this project's business (Task 1.1).
        """
        raise NotImplementedError("§2 — ADP client")

    def report_eval(self, owner: str, repo: str, run_id: str, **fields: Any) -> dict[str, Any]:
        """POST .../runs/{runId}/evals — sent with the *scorer* token."""
        raise NotImplementedError("§2 — ADP client")

    def verify_run(self, owner: str, repo: str, run_id: str) -> dict[str, Any]:
        """GET .../runs/{runId}/verify — the evidence-gating primitive (Task 3.3)."""
        raise NotImplementedError("§2 — ADP client")
