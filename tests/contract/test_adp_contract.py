"""Contract tests against a live ADP (docs/execution-plan.md §2).

Marked `contract` and excluded from the default run: they need a real ADP. They
are what makes an ADP change break this repo loudly instead of silently, so they
must assert against a running instance and never self-skip into a green run.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.contract


@pytest.fixture
def adp_base_url() -> str:
    url = os.environ.get("ADP_BASE_URL")
    if not url:
        pytest.fail("ADP_BASE_URL is not set; contract tests require a live ADP")
    return url


@pytest.mark.skip(reason="§2 — awaiting the generated client")
def test_served_api_version_matches_expected(adp_base_url: str) -> None:
    """The pinned contract version is the one ADP serves."""


@pytest.mark.skip(reason="Task 1.4 — awaiting the recorder")
def test_append_gap_returns_expected_next_seq(adp_base_url: str) -> None:
    """A deliberate producer_seq gap is rejected with a resume point."""


@pytest.mark.skip(reason="Task 3.3 — awaiting evidence gating")
def test_verify_reports_separately_authorized(adp_base_url: str) -> None:
    """A score reported by the runner's own identity is not independent."""
