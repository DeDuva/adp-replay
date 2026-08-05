"""Replay (Tasks 2.1, 2.2, 2.3).

The three done-conditions:

* a deliberate scorer-digest mismatch is refused with a clear error;
* the continuation banner cannot be suppressed by configuration;
* starting a run with a single shared token fails immediately.

No provider is called anywhere here, and that is a property of the design rather
than of the tests: the agent is a protocol, so everything this repository can be
wrong about on its own — sequencing, comparability, cost, resume — is testable
without a network or a key.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from adp_replay.manifest.models import ModelSpec, ReplayMode
from adp_replay.replay import (
    CONTINUATION_BANNER,
    Attempt,
    AttemptOutcome,
    AttemptRequest,
    BudgetExceeded,
    Cell,
    CostLedger,
    Progress,
    RateLimiter,
    ReplayResult,
    ScorerMismatchError,
    assert_comparable,
    fork_at_step,
    fork_at_zero,
    plan_cells,
    remaining,
)
from adp_replay.verdict import Verdict

OPUS = ModelSpec(provider="anthropic", model="claude-opus-5")
GPT = ModelSpec(provider="openai", model="gpt-x")
DIGEST_A = "a" * 64
DIGEST_B = "b" * 64


def an_attempt(
    *, verdict: Verdict = Verdict.PASS, digest: str | None = DIGEST_A, repetition: int = 1
) -> Attempt:
    return Attempt(
        task_id="tb2/x",
        model=OPUS,
        repetition=repetition,
        outcome=AttemptOutcome(passed=verdict is Verdict.PASS),
        verdict=verdict,
        scorer_spec_digest=digest,
        separately_authorized=True,
        downgraded_because=("chains_ok",) if verdict is Verdict.ERROR else (),
    )


def a_result(
    *, mode: ReplayMode = ReplayMode.FORK_AT_ZERO, attempts: tuple[Attempt, ...] = (), **kwargs: Any
) -> ReplayResult:
    return ReplayResult(
        task_id="tb2/x",
        model=OPUS,
        mode=mode,
        attempts=attempts or (an_attempt(),),
        **kwargs,
    )


def scripted(outcome: AttemptOutcome, seen: list[AttemptRequest] | None = None) -> Any:
    def agent(request: AttemptRequest) -> AttemptOutcome:
        if seen is not None:
            seen.append(request)
        return outcome

    return agent


def executor(digest: str = DIGEST_A, verdict: Verdict = Verdict.PASS) -> Any:
    """Stands in for the ADP round-trip: record, close, score, gate."""

    def execute(request: AttemptRequest, agent: Any) -> Attempt:
        outcome = agent(request)
        return Attempt(
            task_id=request.task_id,
            model=request.model,
            repetition=request.repetition,
            outcome=outcome,
            verdict=verdict if outcome.passed else Verdict.FAIL,
            scorer_spec_digest=digest,
            separately_authorized=True,
        )

    return execute


# --- Task 2.1: scorer identity ------------------------------------------------


def test_a_scorer_digest_mismatch_is_refused() -> None:
    # Task 2.1's done-condition. Two results produced by different scorers are
    # not two measurements of the same thing.
    first = a_result(attempts=(an_attempt(digest=DIGEST_A),))
    second = a_result(attempts=(an_attempt(digest=DIGEST_B),))

    with pytest.raises(ScorerMismatchError, match="2 different scorers"):
        assert_comparable([first, second])


def test_the_refusal_names_what_disagreed() -> None:
    # A clear error, per the plan: "these are incomparable" without saying which
    # scorers or which tasks leaves nothing to act on.
    first = a_result(attempts=(an_attempt(digest=DIGEST_A),))
    second = ReplayResult(
        task_id="tb2/other",
        model=GPT,
        mode=ReplayMode.FORK_AT_ZERO,
        attempts=(an_attempt(digest=DIGEST_B),),
    )

    with pytest.raises(ScorerMismatchError) as excinfo:
        assert_comparable([first, second])

    message = str(excinfo.value)
    assert "tb2/x" in message and "tb2/other" in message
    assert DIGEST_A in message and DIGEST_B in message


def test_matching_scorer_digests_compare_fine() -> None:
    results = [a_result(attempts=(an_attempt(digest=DIGEST_A),)) for _ in range(3)]
    assert assert_comparable(results) == DIGEST_A


def test_results_with_no_scorer_identity_are_refused() -> None:
    # Unscored is not the same as agreeing. Comparing results that never
    # established who scored them is how an eval-gated claim loses its gate.
    with pytest.raises(ScorerMismatchError, match="no scorer identity"):
        assert_comparable([a_result(attempts=(an_attempt(digest=None),))])


# --- Task 2.2: the banner -----------------------------------------------------


def test_fork_at_step_results_carry_the_banner() -> None:
    assert a_result(mode=ReplayMode.FORK_AT_STEP, forked_from_step=3).banner == CONTINUATION_BANNER


def test_fork_at_zero_results_do_not() -> None:
    # The banner means something only because it is not on everything.
    assert a_result(mode=ReplayMode.FORK_AT_ZERO).banner is None


def test_the_banner_cannot_be_suppressed_by_configuration() -> None:
    """Task 2.2's done-condition.

    There is no field, constructor argument, or `notes` entry that removes it:
    the banner is computed from the mode. The test tries the three things a
    caller would reach for.
    """
    result = a_result(mode=ReplayMode.FORK_AT_STEP, forked_from_step=2)

    # 1. It is not a settable attribute.
    with pytest.raises(AttributeError):
        result.banner = ""  # type: ignore[misc]

    # 2. It is not a constructor parameter.
    with pytest.raises(TypeError):
        ReplayResult(task_id="t", model=OPUS, mode=ReplayMode.FORK_AT_STEP, banner=None)  # type: ignore[call-arg]

    # 3. Notes cannot shadow it.
    noted = replace(result, notes={"banner": "", "suppress_banner": True})
    assert noted.banner == CONTINUATION_BANNER


def test_the_banner_survives_serialization() -> None:
    # The summary someone quotes is exactly where omitting it would be most
    # tempting and most misleading.
    payload = a_result(mode=ReplayMode.FORK_AT_STEP, forked_from_step=2).to_dict()
    assert payload["banner"] == CONTINUATION_BANNER
    assert payload["is_model_comparison"] is False
    assert CONTINUATION_BANNER in json.dumps(payload)


def test_only_fork_at_zero_claims_to_be_a_model_comparison() -> None:
    assert a_result(mode=ReplayMode.FORK_AT_ZERO).is_model_comparison
    assert not a_result(mode=ReplayMode.FORK_AT_STEP, forked_from_step=1).is_model_comparison


def test_the_banner_text_is_the_plans_words() -> None:
    assert CONTINUATION_BANNER == (
        "Continuation diagnostic: measures Model B's ability to continue Model A's "
        "trajectory prefix. Not a pinned-harness model comparison."
    )


# --- running repetitions ------------------------------------------------------


def test_fork_at_zero_runs_independent_repetitions(tmp_path: Path) -> None:
    from adp_replay.context.canonical import build

    seen: list[AttemptRequest] = []
    result = fork_at_zero(
        "tb2/x",
        OPUS,
        4,
        context=build(system="go"),
        agent=scripted(AttemptOutcome(passed=True), seen),
        execute=executor(),
    )

    assert len(result.attempts) == 4
    assert [request.repetition for request in seen] == [1, 2, 3, 4]
    # Each repetition gets its own workspace: sharing one would make repetition
    # n depend on what n-1 left behind, which is not an independent sample.
    assert len({str(request.workspace) for request in seen}) == 4


def test_fork_at_step_records_where_it_resumed_from() -> None:
    from adp_replay.context.canonical import build

    seen: list[AttemptRequest] = []
    result = fork_at_step(
        "tb2/x",
        GPT,
        7,
        context=build(system="go"),
        agent=scripted(AttemptOutcome(passed=True), seen),
        execute=executor(),
    )

    assert result.forked_from_step == 7
    assert seen[0].resumed_from_step == 7
    # A continuation diagnostic that does not say where it continued from cannot
    # be interpreted.
    assert result.to_dict()["forked_from_step"] == 7


def test_a_replay_needs_a_repetition() -> None:
    from adp_replay.context.canonical import build

    with pytest.raises(ValueError, match="at least one repetition"):
        fork_at_zero(
            "t",
            OPUS,
            0,
            context=build(),
            agent=scripted(AttemptOutcome(passed=True)),
            execute=executor(),
        )


def test_base_state_is_materialized_for_each_repetition(tmp_path: Path) -> None:
    from adp_replay.context.canonical import build
    from adp_replay.storage import LocalCAStore, capture_tree

    source = tmp_path / "base"
    (source / "src").mkdir(parents=True)
    (source / "src" / "a.py").write_text("print(1)\n")
    capture = capture_tree(source)
    store = LocalCAStore(tmp_path / "cas")
    store.put(capture.data)

    seen: list[AttemptRequest] = []
    fork_at_zero(
        "tb2/x",
        OPUS,
        2,
        context=build(system="go"),
        agent=scripted(AttemptOutcome(passed=True), seen),
        execute=executor(),
        base_state=capture.digest,
        store=store,
    )

    # The workspace is gone by now, but the agent saw the restored tree.
    assert len(seen) == 2


# --- the primary outcome ------------------------------------------------------


def test_a_cell_is_solved_on_a_majority_of_passes() -> None:
    result = a_result(
        attempts=(
            an_attempt(verdict=Verdict.PASS, repetition=1),
            an_attempt(verdict=Verdict.PASS, repetition=2),
            an_attempt(verdict=Verdict.FAIL, repetition=3),
        )
    )
    assert result.solved


def test_errors_count_against_the_majority_rather_than_being_dropped() -> None:
    # Dropping them would let one pass and four unverifiable attempts report as
    # solved, which is exactly the claim evidence gating exists to prevent.
    result = a_result(
        attempts=(
            an_attempt(verdict=Verdict.PASS, repetition=1),
            *[an_attempt(verdict=Verdict.ERROR, repetition=n) for n in range(2, 6)],
        )
    )
    assert result.errors == 4
    assert not result.solved


def test_an_empty_cell_is_not_solved() -> None:
    assert not ReplayResult(task_id="t", model=OPUS, mode=ReplayMode.FORK_AT_ZERO).solved


# --- Task 2.3: planning, resuming, limiting, accounting -----------------------


def test_the_plan_covers_every_task_model_repetition() -> None:
    cells = plan_cells(["a", "b"], [OPUS, GPT], 3)
    assert len(cells) == 12
    assert len({cell.key for cell in cells}) == 12


def test_resuming_skips_what_is_already_recorded(tmp_path: Path) -> None:
    cells = plan_cells(["a", "b"], [OPUS], 2)
    progress = Progress(tmp_path / "progress.jsonl")

    progress.record(cells[0], {"passed": True})
    progress.record(cells[1], {"passed": False})

    assert [cell.key for cell in remaining(cells, progress)] == [c.key for c in cells[2:]]


def test_progress_survives_being_reopened(tmp_path: Path) -> None:
    # An experiment that runs for hours is an experiment that gets interrupted.
    path = tmp_path / "progress.jsonl"
    cells = plan_cells(["a"], [OPUS], 2)

    first = Progress(path)
    first.record(cells[0], {"passed": True})

    reopened = Progress(path)
    assert cells[0] in reopened
    assert cells[1] not in reopened
    assert reopened.completed == 1


def test_a_half_written_progress_line_is_tolerated(tmp_path: Path) -> None:
    path = tmp_path / "progress.jsonl"
    cells = plan_cells(["a"], [OPUS], 2)

    progress = Progress(path)
    progress.record(cells[0], {"passed": True})
    path.write_text(path.read_text() + '{"key": "tru')

    assert Progress(path).completed == 1


def test_the_cell_key_distinguishes_modes_and_fork_points() -> None:
    zero = Cell("t", OPUS, ReplayMode.FORK_AT_ZERO, 1)
    step = Cell("t", OPUS, ReplayMode.FORK_AT_STEP, 1, forked_from_step=4)
    other = Cell("t", OPUS, ReplayMode.FORK_AT_STEP, 1, forked_from_step=9)

    assert len({zero.key, step.key, other.key}) == 3


def test_the_rate_limiter_lets_a_burst_through_then_paces() -> None:
    waits: list[float] = []
    limiter = RateLimiter(per_second=10, burst=2)

    for _ in range(2):
        assert limiter.acquire(now=0.0, sleep=waits.append) == 0.0
    # Bucket empty: the third has to wait a tenth of a second.
    assert limiter.acquire(now=0.0, sleep=waits.append) == pytest.approx(0.1)
    assert waits == [pytest.approx(0.1)]


def test_the_rate_limiter_refills_over_time() -> None:
    limiter = RateLimiter(per_second=10, burst=1)
    limiter.acquire(now=0.0, sleep=lambda _: None)
    # A second later the bucket is full again.
    assert limiter.acquire(now=1.0, sleep=lambda _: None) == 0.0


def test_a_nonsense_rate_is_refused() -> None:
    with pytest.raises(ValueError, match="positive"):
        RateLimiter(per_second=0)


def test_cost_is_accounted_per_model() -> None:
    ledger = CostLedger()
    ledger.charge(OPUS, cost=1200, tokens_in=100, tokens_out=50)
    ledger.charge(GPT, cost=800, tokens_in=90, tokens_out=40)
    ledger.charge(OPUS, cost=300, tokens_in=10, tokens_out=5)

    assert ledger.spent_micro_usd == 2300
    assert ledger.by_model["anthropic:claude-opus-5"] == 1500
    assert ledger.by_model["openai:gpt-x"] == 800
    assert ledger.tokens_in == 200


def test_the_budget_is_enforced_before_the_spend_not_after() -> None:
    # An experiment that notices its overspend at the end has already overspent.
    ledger = CostLedger(budget_micro_usd=1000)
    ledger.charge(OPUS, cost=900, tokens_in=0, tokens_out=0)

    ledger.check(estimate=50)
    with pytest.raises(BudgetExceeded, match="past the ceiling"):
        ledger.check(estimate=200)


def test_no_budget_means_no_ceiling() -> None:
    ledger = CostLedger()
    ledger.charge(OPUS, cost=10**9, tokens_in=0, tokens_out=0)
    ledger.check(estimate=10**9)


# --- Task 2.3's done-condition: the identity preflight -------------------------


class FakeAdpForPreflight:
    """Just enough of AdpClient to exercise the preflight."""

    def __init__(self, *, separately_authorized: bool, principal: str = "runner") -> None:
        self.separately_authorized = separately_authorized
        self.principal = principal
        self.calls: list[str] = []

    def create_run(self, owner: str, repo: str, **fields: Any) -> dict[str, Any]:
        self.calls.append("create_run")
        return {"id": "run-preflight"}

    def report_eval(self, owner: str, repo: str, run_id: str, **fields: Any) -> dict[str, Any]:
        self.calls.append("report_eval")
        return {
            "separately_authorized": self.separately_authorized,
            "reporter_principal": self.principal,
        }


def test_a_shared_principal_fails_before_any_spend() -> None:
    """Task 2.3's done-condition.

    The refusal happens at experiment start. Establishing this at analysis time
    would establish it exactly when it is too late: the corpus is burned, the
    money is spent, and the only options left are to publish something
    inadmissible or throw it away.
    """
    from adp_replay.replay.runner import SelfReportedScores, assert_separately_authorized

    adp = FakeAdpForPreflight(separately_authorized=False, principal="the-runner")

    with pytest.raises(SelfReportedScores, match="separately_authorized=false"):
        assert_separately_authorized(
            adp,  # type: ignore[arg-type]
            "acme",
            "widgets",
            intent_id="i-1",
            git_sha="0" * 40,
        )


def test_the_refusal_says_what_to_fix() -> None:
    from adp_replay.replay.runner import SelfReportedScores, assert_separately_authorized

    adp = FakeAdpForPreflight(separately_authorized=False, principal="the-runner")
    with pytest.raises(SelfReportedScores) as excinfo:
        assert_separately_authorized(
            adp,  # type: ignore[arg-type]
            "acme",
            "widgets",
            intent_id="i-1",
            git_sha="0" * 40,
        )

    message = str(excinfo.value)
    assert "the-runner" in message
    # The subtle configuration is the one worth naming: two different tokens for
    # one principal looks fine and produces exactly this failure.
    assert "two different tokens for the same principal is not enough" in message
    assert "before any spend" in message


def test_the_preflight_asks_adp_rather_than_comparing_strings() -> None:
    # Two different token strings can belong to one principal. Only ADP knows.
    from adp_replay.replay.runner import assert_separately_authorized

    adp = FakeAdpForPreflight(separately_authorized=True, principal="the-scorer")
    assert (
        assert_separately_authorized(
            adp,  # type: ignore[arg-type]
            "acme",
            "widgets",
            intent_id="i-1",
            git_sha="0" * 40,
        )
        == "run-preflight"
    )
    assert adp.calls == ["create_run", "report_eval"]


def test_two_identical_tokens_never_get_as_far_as_the_preflight() -> None:
    from adp_replay.adp import AdpClient

    with pytest.raises(ValueError, match="self-report"):
        AdpClient("http://adp.invalid", runner_token="same", scorer_token="same")
