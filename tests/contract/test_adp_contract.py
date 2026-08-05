"""Contract tests against a live ADP (docs/execution-plan.md §2).

Marked `contract` and excluded from the default run: they need a real ADP. They
are what makes an ADP change break this repo loudly instead of silently, so they
assert against a running instance and never self-skip into a green run.

These found three things a mock could not, all recorded in
`docs/adp-contract-findings.md`: the append response's field names are not the
ones the prose implies, `payload` is documented optional and is NOT NULL in the
database, and the native plane cannot open a run on its own because nothing in
it creates an intent.

Setup uses the compat plane for exactly that last reason. A repository and an
intent have to exist before a run can be opened, and `POST /api/v3/.../issues`
is the only documented way to make an intent.

    ADP_BASE_URL=http://localhost:3999 \
    ADP_RUNNER_TOKEN=... ADP_SCORER_TOKEN=... make test-contract
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from adp_replay.adp import (
    EXPECTED_API_VERSION,
    VERSION_HEADER,
    AdpClient,
    AdpError,
    ApiVersionMismatch,
    AppendRejected,
    assert_api_version,
)

pytestmark = pytest.mark.contract


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.fail(f"{name} is not set; contract tests require a live ADP")
    return value


@pytest.fixture(scope="session")
def adp_base_url() -> str:
    return _required("ADP_BASE_URL").rstrip("/")


@pytest.fixture(scope="session")
def runner_token() -> str:
    return _required("ADP_RUNNER_TOKEN")


@pytest.fixture(scope="session")
def scorer_token() -> str:
    return _required("ADP_SCORER_TOKEN")


@pytest.fixture(scope="session")
def client(adp_base_url: str, runner_token: str, scorer_token: str) -> Iterator[AdpClient]:
    with AdpClient(adp_base_url, runner_token=runner_token, scorer_token=scorer_token) as adp:
        yield adp


@pytest.fixture(scope="session")
def repository(adp_base_url: str, runner_token: str) -> tuple[str, str]:
    """A fresh repository, created through the compat plane.

    The native plane has no endpoint that creates one. That is a finding, not an
    oversight in this fixture — see docs/adp-contract-findings.md.
    """
    name = f"replay-contract-{uuid.uuid4().hex[:8]}"
    response = httpx.post(
        f"{adp_base_url}/api/v3/user/repos",
        headers={"Authorization": f"Bearer {runner_token}"},
        json={"name": name},
        timeout=30.0,
    )
    response.raise_for_status()
    return str(response.json()["owner"]["login"]), name


@pytest.fixture
def intent_id(adp_base_url: str, runner_token: str, repository: tuple[str, str]) -> str:
    """An intent, which exists only because an issue was filed for it."""
    owner, repo = repository
    response = httpx.post(
        f"{adp_base_url}/api/v3/repos/{owner}/{repo}/issues",
        headers={"Authorization": f"Bearer {runner_token}"},
        json={"title": "contract probe"},
        timeout=30.0,
    )
    response.raise_for_status()
    return str(response.json()["intent_id"])


@pytest.fixture
def session_id(client: AdpClient, repository: tuple[str, str]) -> str:
    owner, repo = repository
    return str(client.create_session(owner, repo, harness="adp-replay")["id"])


# --- the version assertion ----------------------------------------------------


def test_the_served_version_matches_the_contract_we_generated_against(
    client: AdpClient,
) -> None:
    assert client.assert_contract() == EXPECTED_API_VERSION


def test_the_version_header_is_present_before_authentication(adp_base_url: str) -> None:
    # The case pinning exists to catch is a client pointed at the wrong
    # instance, which by definition holds no valid token for it.
    response = httpx.get(f"{adp_base_url}/api/adp/repos/_/_/runs", timeout=30.0)
    assert response.status_code == 401
    assert response.headers.get(VERSION_HEADER) == EXPECTED_API_VERSION


def test_the_version_header_is_present_on_a_404(adp_base_url: str, runner_token: str) -> None:
    response = httpx.get(
        f"{adp_base_url}/api/adp/repos/nobody/nothing/runs/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {runner_token}"},
        timeout=30.0,
    )
    assert response.status_code == 404
    assert response.headers.get(VERSION_HEADER) == EXPECTED_API_VERSION


def test_a_client_built_for_another_contract_refuses_this_server(adp_base_url: str) -> None:
    served = httpx.get(f"{adp_base_url}/api/adp/repos/_/_/runs", timeout=30.0).headers[
        VERSION_HEADER
    ]
    with pytest.raises(ApiVersionMismatch):
        assert_api_version(served, "99.0.0")


# --- recording ----------------------------------------------------------------


def test_a_run_can_be_opened_and_a_session_attached(
    client: AdpClient, repository: tuple[str, str], intent_id: str
) -> None:
    owner, repo = repository
    run = client.create_run(owner, repo, intent_id=intent_id, orchestrator="adp-replay")
    assert run["status"] == "open"

    session = client.create_session(owner, repo, harness="adp-replay", run_id=run["id"])
    assert session["id"]


def test_an_append_returns_the_mark_a_spool_trims_against(
    client: AdpClient, repository: tuple[str, str], session_id: str
) -> None:
    owner, repo = repository
    receipt = client.append_events(
        owner,
        repo,
        session_id,
        [
            {"kind": "message", "producer_seq": 1, "client_event_id": "e1"},
            {"kind": "tool_call", "producer_seq": 2, "client_event_id": "e2"},
        ],
        producer_id="contract-test",
    )

    assert receipt.accepted_through == 2
    assert receipt.appended == 2
    assert receipt.chain_head
    assert receipt.duplicates == ()


def test_an_untracked_emitter_gets_no_trim_mark(
    client: AdpClient, repository: tuple[str, str], session_id: str
) -> None:
    # No producer_seq means ADP cannot say what it is complete through. None is
    # the honest answer, and a spool must not read it as zero.
    owner, repo = repository
    receipt = client.append_events(owner, repo, session_id, [{"kind": "message"}])
    assert receipt.accepted_through is None


def test_a_gap_is_rejected_with_the_seq_to_replay_from(
    client: AdpClient, repository: tuple[str, str], session_id: str
) -> None:
    owner, repo = repository
    client.append_events(
        owner,
        repo,
        session_id,
        [{"kind": "message", "producer_seq": 1, "client_event_id": "a1"}],
        producer_id="contract-test",
    )

    with pytest.raises(AppendRejected) as excinfo:
        client.append_events(
            owner,
            repo,
            session_id,
            [{"kind": "message", "producer_seq": 9, "client_event_id": "a9"}],
            producer_id="contract-test",
        )

    # The resume point, not a guess: this is what Task 1.4's spool replays from.
    assert excinfo.value.expected_next_seq == 2


def test_a_repeated_client_event_id_is_reported_as_a_duplicate(
    client: AdpClient, repository: tuple[str, str], session_id: str
) -> None:
    # Not an error, and not silent either. A non-empty duplicates list means the
    # recorder sent something twice believing it had not, which Task 1.4 treats
    # as a bug signal.
    owner, repo = repository
    event: dict[str, Any] = {"kind": "message", "producer_seq": 1, "client_event_id": "dup"}
    client.append_events(owner, repo, session_id, [event], producer_id="contract-test")

    receipt = client.append_events(
        owner, repo, session_id, [{**event, "producer_seq": 2}], producer_id="contract-test"
    )
    assert receipt.duplicates == ("dup",)
    assert receipt.appended == 0


def test_an_event_without_a_payload_is_accepted(
    client: AdpClient, repository: tuple[str, str], session_id: str
) -> None:
    # The spec requires only `kind`. The column behind `payload` is NOT NULL, so
    # this is a 500 without the client's workaround. If ADP fixes the schema this
    # still passes; if the workaround is dropped first, this fails.
    owner, repo = repository
    receipt = client.append_events(owner, repo, session_id, [{"kind": "message"}])
    assert receipt.appended == 1


def test_a_checkpoint_against_an_unresolvable_commit_is_a_422(
    client: AdpClient, repository: tuple[str, str], session_id: str
) -> None:
    # A fresh repository has no commits, so ADP cannot resolve the sha. The
    # contract documents that as a 422, and a 422 is the endpoint behaving —
    # what would be wrong is a 500, or a silent success attesting to nothing.
    owner, repo = repository
    with pytest.raises(AdpError) as excinfo:
        client.create_checkpoint(
            owner,
            repo,
            session_id,
            git_sha="0" * 40,
            state={"snapshot": "sha256:" + "a" * 64},
            harness="adp-replay",
        )
    assert excinfo.value.status == 422


# --- evidence -----------------------------------------------------------------


def test_verify_reports_the_sub_checks_task_3_3_gates_on(
    client: AdpClient, repository: tuple[str, str], intent_id: str
) -> None:
    owner, repo = repository
    run = client.create_run(owner, repo, intent_id=intent_id, orchestrator="adp-replay")
    session = client.create_session(owner, repo, harness="adp-replay", run_id=run["id"])
    client.append_events(
        owner,
        repo,
        session["id"],
        [{"kind": "message", "producer_seq": 1, "client_event_id": "v1"}],
        producer_id="contract-test",
    )

    verified = client.verify_run(owner, repo, run["id"])

    for field in ("ok", "chains_ok", "emitters_ok", "envelope_verified"):
        assert field in verified, f"verify response is missing {field}"
    assert verified["chains_ok"] is True
    assert verified["emitters_ok"] is True


def test_verify_separates_chain_integrity_from_emitter_completeness(
    client: AdpClient, repository: tuple[str, str], intent_id: str
) -> None:
    # The guarantee that matters most here: a chain can verify perfectly and
    # still be missing an event that never arrived. Two names, two answers.
    owner, repo = repository
    run = client.create_run(owner, repo, intent_id=intent_id, orchestrator="adp-replay")
    session = client.create_session(owner, repo, harness="adp-replay", run_id=run["id"])
    client.append_events(
        owner,
        repo,
        session["id"],
        [{"kind": "message", "producer_seq": 1, "client_event_id": "g1"}],
        producer_id="contract-test",
    )

    sessions = client.verify_run(owner, repo, run["id"]).get("sessions", [])
    assert sessions, "verify should report per-session emitter state"
    assert "emitter_tracked" in sessions[0]
    assert "emitter_complete" in sessions[0]
