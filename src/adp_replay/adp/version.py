"""API version pinning (docs/execution-plan.md §2).

Asserted once at startup and never mid-experiment. A contract break discovered
after an experiment has begun spending has already cost the corpus; the whole
value of pinning is that it fails before that.

Prerequisite: ADP's native plane (``/api/adp/...``) does not yet carry a version
segment and its OpenAPI document declares ``0.0.0-mvp``, so there is nothing
authoritative to pin against. Until ADP serves a pinnable version, callers pin
the ADP container by image digest and treat the contract as provisional.
"""

from __future__ import annotations

VERSION_HEADER = "ADP-API-Version"

# The contract this checkout was generated against. Bump only alongside
# regenerating the client and re-running the contract tests.
EXPECTED_API_VERSION = "0.0.0-mvp"


class ApiVersionMismatch(RuntimeError):
    """The ADP instance does not serve the contract this client was built for."""


def assert_api_version(served: str | None, expected: str = EXPECTED_API_VERSION) -> None:
    """Fail loudly when ``served`` is not the contract we generated against.

    A missing header is a mismatch, not a pass: an ADP old enough to omit it is
    exactly the case this check exists to catch.
    """
    raise NotImplementedError("§2 — pin the ADP wire contract")
