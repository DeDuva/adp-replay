"""The ADP wire contract (docs/execution-plan.md §2).

These run against a mock transport: they pin what this client *sends* and how it
reads what comes back. What they cannot pin is that ADP agrees — that is
`tests/contract/`, against a live instance, and no amount of mocking substitutes
for it.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from adp_replay.adp import (
    EXPECTED_API_VERSION,
    SPEC_VERSION,
    VERSION_HEADER,
    AdpClient,
    AdpError,
    ApiVersionMismatch,
    AppendRejected,
    assert_api_version,
)
from adp_replay.adp._generated import OPERATIONS, operation

RUNNER = "runner-token"
SCORER = "scorer-token"


def transport(handler: Any) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def client(handler: Any, **kwargs: Any) -> AdpClient:
    return AdpClient(
        "https://adp.example",
        runner_token=RUNNER,
        scorer_token=SCORER,
        transport=transport(handler),
        **kwargs,
    )


def ok(payload: dict[str, Any], status: int = 200) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload, headers={VERSION_HEADER: EXPECTED_API_VERSION})

    return handler


# --- version pinning ----------------------------------------------------------


def test_the_expected_version_comes_from_the_generated_module() -> None:
    # Written down once. If this ever diverges, "the contract this checkout was
    # built for" has two answers and the assertion is checking the wrong one.
    assert EXPECTED_API_VERSION == SPEC_VERSION


def test_a_matching_version_passes() -> None:
    assert_api_version(EXPECTED_API_VERSION)


def test_a_missing_header_is_a_mismatch_not_a_pass() -> None:
    # An ADP old enough to omit the header is exactly what this catches.
    with pytest.raises(ApiVersionMismatch, match="served no"):
        assert_api_version(None)


def test_a_different_version_is_refused_by_default() -> None:
    with pytest.raises(ApiVersionMismatch, match=r"0\.2\.0"):
        assert_api_version("0.2.0", "0.1.0")


def test_compatible_mode_accepts_a_newer_minor() -> None:
    # ADP documents a minor bump as additive, so a client generated against an
    # older minor still works.
    assert_api_version("0.2.0", "0.1.0", allow_compatible=True)
    assert_api_version("0.1.4", "0.1.0", allow_compatible=True)


def test_compatible_mode_still_refuses_a_major_bump() -> None:
    with pytest.raises(ApiVersionMismatch, match="different major"):
        assert_api_version("1.0.0", "0.1.0", allow_compatible=True)


def test_compatible_mode_refuses_an_older_server() -> None:
    # Older means it may not carry fields this client was built to read.
    with pytest.raises(ApiVersionMismatch, match="older than"):
        assert_api_version("0.1.0", "0.2.0", allow_compatible=True)


def test_a_nonsense_version_is_refused() -> None:
    with pytest.raises(ApiVersionMismatch, match="not a semver"):
        assert_api_version("banana", "0.1.0", allow_compatible=True)


def test_the_contract_check_runs_without_a_valid_token() -> None:
    # ADP sets the header on 401s deliberately, so pinning happens before
    # authentication. A check that needed a good token would miss the case it
    # exists for: a client pointed at the wrong instance.
    def unauthorized(request: httpx.Request) -> httpx.Response:
        assert "Authorization" not in request.headers
        return httpx.Response(
            401, json={"message": "no"}, headers={VERSION_HEADER: EXPECTED_API_VERSION}
        )

    assert client(unauthorized).assert_contract() == EXPECTED_API_VERSION


def test_a_server_serving_another_contract_fails_the_check() -> None:
    def wrong(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={}, headers={VERSION_HEADER: "9.9.9"})

    with pytest.raises(ApiVersionMismatch):
        client(wrong).assert_contract()


# --- two identities -----------------------------------------------------------


def test_one_token_for_both_roles_is_refused_at_construction() -> None:
    # Task 2.3 asserts this again before spend; refusing it here means the
    # mistake cannot even be built.
    with pytest.raises(ValueError, match="self-report"):
        AdpClient("https://adp.example", runner_token="same", scorer_token="same")


def test_scores_are_reported_with_the_scorer_identity() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["Authorization"]
        return httpx.Response(201, json={"separately_authorized": True})

    client(handler).report_eval("acme", "widgets", "run-1", name="tb2", passed=True)
    assert seen["auth"] == f"Bearer {SCORER}"


def test_everything_else_is_reported_with_the_runner_identity() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["Authorization"]
        return httpx.Response(201, json={})

    client(handler).create_run("acme", "widgets", intent_id="i-1", orchestrator="adp-replay")
    assert seen["auth"] == f"Bearer {RUNNER}"


# --- paths and required fields come from the contract -------------------------


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("post_repos_by_owner_by_repo_runs", "/api/adp/repos/{owner}/{repo}/runs"),
        (
            "post_repos_by_owner_by_repo_sessions_by_id_events",
            "/api/adp/repos/{owner}/{repo}/sessions/{id}/events",
        ),
        (
            "get_repos_by_owner_by_repo_runs_by_run_id_verify",
            "/api/adp/repos/{owner}/{repo}/runs/{runId}/verify",
        ),
    ],
)
def test_the_generated_operations_match_the_plan(key: str, expected: str) -> None:
    assert operation(key).path == expected


def test_only_the_native_plane_is_generated() -> None:
    # The compat plane is GitHub's shape, served for `gh`. Nothing here should
    # reach for it.
    assert all(op.path.startswith("/api/adp/") for op in OPERATIONS.values())


def test_a_dropped_endpoint_fails_loudly() -> None:
    with pytest.raises(KeyError, match="regenerate the client"):
        operation("post_repos_by_owner_by_repo_time_machine")


def test_an_incomplete_path_is_refused_before_the_request() -> None:
    with pytest.raises(KeyError, match="path parameters"):
        operation("get_repos_by_owner_by_repo_runs_by_run_id_verify").url(
            "https://adp.example", owner="acme", repo="widgets"
        )


def test_a_missing_required_field_is_caught_at_the_call_site() -> None:
    # The contract says `final_git_sha` is required. Catching it here turns a
    # 422 halfway through a recording into a programming error.
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("the request should never have been sent")

    with pytest.raises(ValueError, match="requires"):
        client(handler)._call(
            operation("post_repos_by_owner_by_repo_runs_by_run_id_close"),
            {"owner": "a", "repo": "b", "runId": "r"},
            body={},
        )


def test_the_url_is_built_from_the_contract_path() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"ok": True})

    client(handler).verify_run("acme", "widgets", "run-9")
    assert seen["url"] == "https://adp.example/api/adp/repos/acme/widgets/runs/run-9/verify"


# --- appending ----------------------------------------------------------------


def test_an_append_returns_the_mark_a_spool_trims_against() -> None:
    # Field names are ADP's own, taken from a live server rather than from the
    # spec's prose: the chain head arrives as `head`, and `duplicates` is a list
    # of client_event_ids rather than a count. Both were wrong here until the
    # contract tests ran (docs/adp-contract-findings.md).
    receipt = client(
        ok(
            {
                "head": "sha256:abc",
                "accepted_through": 7,
                "appended": 1,
                "duplicates": [],
                "count": 7,
            },
            201,
        )
    ).append_events("acme", "widgets", "s-1", [{"kind": "tool_call", "producer_seq": 7}])

    assert receipt.accepted_through == 7
    assert receipt.chain_head == "sha256:abc"
    assert receipt.duplicates == ()
    assert receipt.duplicate_count == 0


def test_duplicates_name_the_events_that_were_dropped() -> None:
    receipt = client(
        ok(
            {
                "head": "sha256:abc",
                "accepted_through": 3,
                "appended": 0,
                "duplicates": ["e1", "e2"],
                "count": 3,
            },
            201,
        )
    ).append_events("acme", "widgets", "s-1", [{"kind": "message"}])

    assert receipt.duplicates == ("e1", "e2")
    assert receipt.duplicate_count == 2
    assert receipt.appended == 0


def test_an_event_without_a_payload_gets_one_before_it_is_sent() -> None:
    # ADP's spec marks payload optional; the column is NOT NULL, so an event
    # without one is a 500. Until ADP fixes that, a recorder must not be able to
    # take down its own run by emitting an event the contract says is legal.
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(201, json={"appended": 1, "duplicates": [], "count": 1})

    client(handler).append_events("acme", "widgets", "s-1", [{"kind": "message"}])
    assert seen["events"][0]["payload"] == {}


def test_an_explicit_payload_is_left_alone() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(201, json={"appended": 1, "duplicates": [], "count": 1})

    client(handler).append_events(
        "acme", "widgets", "s-1", [{"kind": "message", "payload": {"text": "hi"}}]
    )
    assert seen["events"][0]["payload"] == {"text": "hi"}


def test_a_contiguity_rejection_carries_its_resume_point() -> None:
    def gap(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"expected_next_seq": 4, "message": "gap"})

    with pytest.raises(AppendRejected) as excinfo:
        client(gap).append_events("acme", "widgets", "s-1", [{"kind": "message"}])

    assert excinfo.value.expected_next_seq == 4


def test_a_closed_session_is_a_409_with_no_resume_point() -> None:
    # Same status, different condition. Replaying the spool does not fix this
    # one, so the absence of a resume point has to be distinguishable.
    def closed(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"message": "session is closed"})

    with pytest.raises(AppendRejected) as excinfo:
        client(closed).append_events("acme", "widgets", "s-1", [{"kind": "message"}])

    assert excinfo.value.expected_next_seq is None


def test_the_producer_id_is_sent_when_given() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(201, json={"accepted_through": 1, "duplicates": [], "appended": 1})

    client(handler).append_events(
        "acme", "widgets", "s-1", [{"kind": "message"}], producer_id="recorder-1"
    )
    assert seen["producer_id"] == "recorder-1"


# --- errors -------------------------------------------------------------------


def test_a_failure_carries_its_status_and_body() -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"message": "intent not found"})

    with pytest.raises(AdpError) as excinfo:
        client(broken).create_run("acme", "widgets", intent_id="nope", orchestrator="x")

    assert excinfo.value.status == 422
    assert excinfo.value.body == {"message": "intent not found"}


def test_a_non_json_error_body_does_not_mask_the_status() -> None:
    def html(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="<html>bad gateway</html>")

    with pytest.raises(AdpError) as excinfo:
        client(html).verify_run("acme", "widgets", "run-1")

    assert excinfo.value.status == 502


def test_the_client_closes_cleanly_as_a_context_manager() -> None:
    with client(ok({})) as adp:
        assert adp.base_url == "https://adp.example"
