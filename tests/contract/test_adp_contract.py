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
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
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
from adp_replay.recording import Recorder, Spool
from adp_replay.replay import assert_separately_authorized
from adp_replay.storage import (
    AttestationError,
    LocalCAStore,
    capture_tree,
    snapshot_state,
    state_digest,
    verify_checkpoint,
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


def _repo_with_a_commit(
    adp_base_url: str, runner_token: str, tmp_path: Path
) -> tuple[str, str, str]:
    """A fresh ADP repository holding one real commit, pushed over git-http.

    A checkpoint attests a commit, and ADP will not attest one it cannot
    resolve, so a snapshot attestation cannot be exercised against an empty
    repository. The credential helper is replaced rather than configured: git
    otherwise reaches for whatever the host has installed, which on some
    machines is an interactive prompt this test would hang on.
    """
    name = f"ck-{uuid.uuid4().hex[:8]}"
    created = httpx.post(
        f"{adp_base_url}/api/v3/user/repos",
        headers={"Authorization": f"Bearer {runner_token}"},
        json={"name": name},
        timeout=30.0,
    )
    created.raise_for_status()
    owner = str(created.json()["owner"]["login"])

    work = tmp_path / "git" / name
    work.mkdir(parents=True)

    def git(*args: str) -> str:
        helper = f"!f(){{ echo username=x; echo password={runner_token}; }};f"
        result = subprocess.run(
            ["git", "-c", "credential.helper=", "-c", f"credential.helper={helper}", *args],
            cwd=work,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise AssertionError(f"git {args[0]} failed: {result.stderr}")
        return result.stdout.strip()

    git("init", "-q", "-b", "main")
    git("config", "user.email", "contract@example.invalid")
    git("config", "user.name", "contract")
    (work / "a.txt").write_text("hi\n")
    git("add", "-A")
    git("commit", "-qm", "init")
    git("push", "-q", f"{adp_base_url}/{owner}/{name}.git", "main")

    return owner, name, git("rev-parse", "HEAD")


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


def test_a_snapshot_digest_verifies_against_the_returned_envelope(
    adp_base_url: str, client: AdpClient, runner_token: str, tmp_path: Path
) -> None:
    """Task 1.1's done-condition, against a real ADP.

    Needs a repository with an actual commit, because a checkpoint attests a
    commit and ADP refuses to attest one it cannot resolve. So this pushes one
    over git-http, which is also a small end-to-end check that the snapshot path
    and the git path agree about the same repository.
    """
    owner, repo, git_sha = _repo_with_a_commit(adp_base_url, runner_token, tmp_path)

    work = tmp_path / "work"
    work.mkdir()
    (work / "a.txt").write_text("hi\n")
    capture = capture_tree(work)

    store = LocalCAStore(tmp_path / "cas")
    digest = store.put(capture.data)

    session = client.create_session(owner, repo, harness="adp-replay")
    state = snapshot_state(digest, entries=len(capture.entries))
    checkpoint = client.create_checkpoint(
        owner, repo, session["id"], git_sha=git_sha, state=state, harness="adp-replay"
    )

    attestation = verify_checkpoint(checkpoint, state=state, git_sha=git_sha)

    # The binding that matters: ADP's signed envelope names the digest of bytes
    # that never left this machine, and those bytes are still here.
    assert attestation.state_sha256 == state_digest(state)
    assert store.get(digest) == capture.data


def test_the_envelope_does_not_verify_against_a_different_snapshot(
    adp_base_url: str, client: AdpClient, runner_token: str, tmp_path: Path
) -> None:
    # The complement: an attestation that verified against anything would be
    # attesting nothing.
    owner, repo, git_sha = _repo_with_a_commit(adp_base_url, runner_token, tmp_path)
    session = client.create_session(owner, repo, harness="adp-replay")

    state = snapshot_state("sha256:" + "a" * 64)
    checkpoint = client.create_checkpoint(
        owner, repo, session["id"], git_sha=git_sha, state=state, harness="adp-replay"
    )

    with pytest.raises(AttestationError, match="attests state"):
        verify_checkpoint(checkpoint, state=snapshot_state("sha256:" + "b" * 64))


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


# --- Task 1.4: killing the recorder -------------------------------------------


RECORDER_CHILD = """
import os, sys
from adp_replay.adp import AdpClient
from adp_replay.recording import Recorder, Spool
from adp_replay.replay import assert_separately_authorized

base, runner, scorer, owner, repo, session, spool_root = sys.argv[1:8]
client = AdpClient(base, runner_token=runner, scorer_token=scorer)
recorder = Recorder(client, owner, repo, session, Spool(spool_root), poll_interval=0.01)
recorder.start()
for index in range(60):
    recorder.record("message", payload={"i": index})
recorder.flush(timeout=5)
print("READY", flush=True)
# Wait to be killed. Anything still spooled is what the parent has to recover.
for index in range(60, 120):
    recorder.record("message", payload={"i": index})
sys.stdout.write("SPOOLED\\n")
sys.stdout.flush()
while True:
    pass
"""


def test_killing_the_recorder_leaves_a_resumable_gap_free_chain(
    adp_base_url: str,
    runner_token: str,
    scorer_token: str,
    client: AdpClient,
    repository: tuple[str, str],
    intent_id: str,
    tmp_path: Path,
) -> None:
    """Task 1.4's done-condition, with a real SIGKILL against a real ADP.

    A child process records, is killed without any chance to flush, and a fresh
    recorder opens the same spool and finishes. What ADP ends up holding has to
    be every event exactly once, in order.
    """
    owner, repo = repository
    run_id = client.create_run(owner, repo, intent_id=intent_id, orchestrator="adp-replay")["id"]
    session = client.create_session(owner, repo, harness="adp-replay", run_id=run_id)["id"]
    spool_root = tmp_path / "spool"

    script = tmp_path / "child.py"
    script.write_text(RECORDER_CHILD)

    child = subprocess.Popen(
        [
            sys.executable,
            str(script),
            adp_base_url,
            runner_token,
            scorer_token,
            owner,
            repo,
            str(session),
            str(spool_root),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert child.stdout is not None
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if (child.stdout.readline() or "").startswith("SPOOLED"):
                break
        else:  # pragma: no cover - only on a hung child
            raise AssertionError("child never spooled")
        # SIGKILL: no cleanup, no flush, no final append. The spool on disk is
        # the only thing that survives.
        child.kill()
        child.wait(timeout=30)
    finally:
        if child.poll() is None:  # pragma: no cover
            child.kill()

    resumed = Recorder(client, owner, repo, str(session), Spool(spool_root), poll_interval=0.01)
    with resumed:
        assert resumed.flush(timeout=60), "the resumed recorder did not drain the spool"

    events = httpx.get(
        f"{adp_base_url}/api/adp/repos/{owner}/{repo}/sessions/{session}/events",
        headers={"Authorization": f"Bearer {runner_token}"},
        params={"limit": 1000},
        timeout=30.0,
    )
    events.raise_for_status()
    payload = events.json()
    rows = payload["events"] if isinstance(payload, dict) else payload

    sequences = [row["producer_seq"] for row in rows if row.get("producer_seq") is not None]
    assert sequences == list(range(1, 121)), "the chain ADP holds must be complete and gap-free"

    # And ADP agrees, by its own counter rather than by ours: emitters_ok is the
    # check that says nothing was withheld, which is the guarantee a resumed
    # recorder has to preserve.
    verified = client.verify_run(owner, repo, run_id)
    session_state = next(s for s in verified["sessions"] if s["session_id"] == session)
    assert session_state["emitter_tracked"] is True
    assert session_state["emitter_complete"] is True


# --- Task 2.3: the identity preflight -----------------------------------------


def test_the_scorer_is_confirmed_independent_before_any_spend(
    adp_base_url: str,
    runner_token: str,
    scorer_token: str,
    repository: tuple[str, str],
    intent_id: str,
    tmp_path: Path,
) -> None:
    """Two principals, and ADP says so — the preflight passes and spend begins."""
    owner, repo = repository
    _, _, git_sha = _repo_with_a_commit(adp_base_url, runner_token, tmp_path)

    with AdpClient(adp_base_url, runner_token=runner_token, scorer_token=scorer_token) as adp:
        assert assert_separately_authorized(adp, owner, repo, intent_id=intent_id, git_sha=git_sha)


def test_adp_calls_a_self_reported_score_what_it_is(
    adp_base_url: str,
    runner_token: str,
    scorer_token: str,
    client: AdpClient,
    repository: tuple[str, str],
    intent_id: str,
    tmp_path: Path,
) -> None:
    """The fact the whole preflight rests on, checked against a live ADP.

    A score reported by the identity that opened the run is not independent
    evidence, and ADP says ``separately_authorized: false`` rather than leaving
    a consumer to work it out. The preflight is only worth running because this
    answer is real.

    The dangerous configuration is not two identical tokens — the client refuses
    those outright — but two *different* tokens belonging to one principal.
    Nothing over REST can mint a second token, so what is verified here is the
    underlying answer; the preflight's refusal on that answer is unit-tested.
    """
    owner, repo = repository
    _, _, git_sha = _repo_with_a_commit(adp_base_url, runner_token, tmp_path)
    run_id = client.create_run(owner, repo, intent_id=intent_id, orchestrator="adp-replay")["id"]

    independent = client.report_eval(
        owner, repo, run_id, name="by-scorer", passed=True, git_sha=git_sha, spec={"v": 1}
    )
    assert independent["separately_authorized"] is True

    # Same call, reported with the runner's own identity.
    self_reported = httpx.post(
        f"{adp_base_url}/api/adp/repos/{owner}/{repo}/runs/{run_id}/evals",
        headers={"Authorization": f"Bearer {runner_token}"},
        json={"name": "by-runner", "passed": True, "git_sha": git_sha, "spec": {"v": 1}},
        timeout=30.0,
    )
    self_reported.raise_for_status()
    assert self_reported.json()["separately_authorized"] is False

    # And the two agree on scorer identity: same spec, same spec_digest, so a
    # comparison across them would be refused for the right reason or not at all.
    assert self_reported.json()["spec_digest"] == independent["spec_digest"]
