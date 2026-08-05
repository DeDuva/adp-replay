"""Paired statistics, evidence gating, and reports (Tasks 3.1, 3.2, 3.3).

Task 3.3's done-condition — tampering with a recorded event turns the verdict
into an error — is here as a unit test over ADP's verify shape, and in the
contract suite against a real ADP where the tampering is real.
"""

from __future__ import annotations

import html
import json
from typing import Any

import pytest

from adp_replay.manifest.models import ModelSpec, ReplayMode, StateCompleteness
from adp_replay.replay import Attempt, AttemptOutcome, ReplayResult, ScorerMismatchError
from adp_replay.report import Arm, Report, render_html, render_json
from adp_replay.stats.paired import (
    bootstrap_ci_over_tasks,
    icc,
    paired_difference_ci_over_tasks,
    variance_decomposition,
)
from adp_replay.verdict import Verdict, failing_checks, gate_verdict

BASE = ModelSpec(provider="anthropic", model="a")
OTHER = ModelSpec(provider="openai", model="b")
DIGEST = "d" * 64


def verified(**overrides: Any) -> dict[str, Any]:
    return {
        "ok": True,
        "chains_ok": True,
        "emitters_ok": True,
        "envelope_verified": True,
        "trajectory_digest_matches": True,
        "evals": [{"name": "tb2", "separately_authorized": True}],
        **overrides,
    }


def result(
    model: ModelSpec, task: str, passes: int, n: int = 3, digest: str = DIGEST
) -> ReplayResult:
    attempts = tuple(
        Attempt(
            task_id=task,
            model=model,
            repetition=index + 1,
            outcome=AttemptOutcome(passed=index < passes),
            verdict=Verdict.PASS if index < passes else Verdict.FAIL,
            scorer_spec_digest=digest,
            separately_authorized=True,
        )
        for index in range(n)
    )
    return ReplayResult(task_id=task, model=model, mode=ReplayMode.FORK_AT_ZERO, attempts=attempts)


# --- Task 3.3: evidence gating ------------------------------------------------


def test_a_verified_run_keeps_its_verdict() -> None:
    assert gate_verdict(Verdict.PASS, verified()).verdict is Verdict.PASS
    assert gate_verdict(Verdict.FAIL, verified()).verdict is Verdict.FAIL


def test_tampering_turns_a_verdict_into_an_error() -> None:
    # Task 3.3's done-condition: an edited event breaks the chain, and an
    # unverifiable result is never counted as a pass or a fail.
    gated = gate_verdict(Verdict.PASS, verified(ok=False, chains_ok=False))

    assert gated.verdict is Verdict.ERROR
    assert "chains_ok" in gated.downgraded_because


def test_a_withheld_event_turns_a_verdict_into_an_error() -> None:
    # A chain can verify perfectly and still be missing an event that never
    # arrived. Two guarantees, two answers.
    gated = gate_verdict(Verdict.PASS, verified(ok=False, emitters_ok=False))

    assert gated.verdict is Verdict.ERROR
    assert gated.downgraded_because == ("emitters_ok",)


def test_a_self_reported_score_turns_a_verdict_into_an_error() -> None:
    gated = gate_verdict(
        Verdict.PASS,
        verified(ok=False, evals=[{"name": "tb2", "separately_authorized": False}]),
    )
    assert gated.verdict is Verdict.ERROR
    assert gated.downgraded_because == ("separately_authorized (tb2)",)


def test_every_failing_sub_check_is_recorded() -> None:
    # "Error" tells you to look; the sub-check tells you where.
    gated = gate_verdict(
        Verdict.PASS,
        verified(ok=False, chains_ok=False, emitters_ok=False, envelope_verified=False),
    )
    assert set(gated.downgraded_because) >= {"chains_ok", "emitters_ok", "envelope_verified"}


def test_a_null_sub_check_is_not_a_failure() -> None:
    # ADP reports envelope_verified as null for a run it never attested. Reading
    # "not applicable" as "failed" would downgrade every open run.
    gated = gate_verdict(
        Verdict.FAIL, verified(envelope_verified=None, trajectory_digest_matches=None)
    )
    assert gated.verdict is Verdict.FAIL
    assert gated.downgraded_because == ()


def test_a_missing_sub_check_is_a_failure() -> None:
    # Assuming the best about a field that is not there is how a gate stops
    # gating.
    response = verified()
    del response["chains_ok"]

    gated = gate_verdict(Verdict.PASS, response)
    assert gated.verdict is Verdict.ERROR
    assert any("chains_ok" in reason for reason in gated.downgraded_because)


def test_adps_own_answer_wins_even_when_nothing_else_explains_it() -> None:
    # ok=false with every sub-check true: ADP knows something this code does
    # not, and its answer is authoritative.
    gated = gate_verdict(Verdict.PASS, verified(ok=False))
    assert gated.verdict is Verdict.ERROR
    assert gated.downgraded_because  # never an unexplained error


def test_failing_checks_reads_the_response_without_gating() -> None:
    assert failing_checks(verified()) == ()
    assert failing_checks(verified(emitters_ok=False)) == ("emitters_ok",)


# --- Task 3.1: resampling over tasks ------------------------------------------


def test_the_interval_resamples_tasks_not_trajectories() -> None:
    """The rule the plan will not let be cut.

    Two datasets with the same number of *trajectories* and different numbers of
    *tasks*. Resampling trajectories would give them near-identical intervals;
    resampling tasks gives the one with fewer tasks a much wider one, which is
    the truth — three tasks is three pieces of evidence however many times each
    was run.
    """
    few_tasks = [[True] * 10, [False] * 10, [True] * 10]
    many_tasks = [[True], [False], [True], [False], [True], [False]] * 5

    narrow_low, narrow_high = bootstrap_ci_over_tasks(many_tasks, resamples=2000)
    wide_low, wide_high = bootstrap_ci_over_tasks(few_tasks, resamples=2000)

    assert (wide_high - wide_low) > (narrow_high - narrow_low)


def test_a_task_is_resampled_whole() -> None:
    # Every repetition travels with its task, which is what preserves the
    # within-task correlation the interval is supposed to account for.
    everything_agrees = [[True] * 5, [True] * 5, [True] * 5]
    low, high = bootstrap_ci_over_tasks(everything_agrees, resamples=500)
    assert (low, high) == (1.0, 1.0)


def test_a_long_task_does_not_outvote_a_short_one() -> None:
    # The statistic is the mean over tasks of each task's own rate.
    low, high = bootstrap_ci_over_tasks([[True] * 100, [False]], resamples=2000)
    assert low <= 0.5 <= high


def test_the_interval_is_deterministic_under_a_seed() -> None:
    tasks = [[True, False], [True, True], [False, False]]
    assert bootstrap_ci_over_tasks(tasks, resamples=500, seed=3) == bootstrap_ci_over_tasks(
        tasks, resamples=500, seed=3
    )


def test_a_paired_interval_keeps_the_two_arms_together() -> None:
    # The paired design's advantage is that task difficulty cancels. Resampling
    # the arms independently would throw that away.
    baseline = [[False] * 3 for _ in range(6)]
    treatment = [[True] * 3 for _ in range(6)]

    low, high = paired_difference_ci_over_tasks(baseline, treatment, resamples=500)
    assert (low, high) == (1.0, 1.0)


def test_mismatched_arms_are_refused() -> None:
    with pytest.raises(ValueError, match="same number of tasks"):
        paired_difference_ci_over_tasks([[True]], [[True], [False]])


def test_an_empty_corpus_is_refused() -> None:
    with pytest.raises(ValueError, match="at least one task"):
        bootstrap_ci_over_tasks([])


# --- Task 3.1: variance decomposition -----------------------------------------


def test_icc_is_one_when_tasks_separate_perfectly() -> None:
    separated = [[True] * 4 for _ in range(4)] + [[False] * 4 for _ in range(4)]
    assert icc(separated) == pytest.approx(1.0)


def test_icc_is_zero_when_everything_is_noise() -> None:
    # Every task behaves like every other: the outcome is run-to-run noise, and
    # no number of such tasks settles anything.
    noise = [[True, False] * 3 for _ in range(8)]
    assert icc(noise) == pytest.approx(0.0)


def test_the_decomposition_splits_between_and_within() -> None:
    split = variance_decomposition([[True] * 4 for _ in range(3)] + [[False] * 4 for _ in range(3)])
    assert split["between_tasks"] + split["within_tasks"] == pytest.approx(1.0)


def test_icc_needs_repetitions_to_be_defined() -> None:
    with pytest.raises(ValueError, match="two or more repetitions"):
        icc([[True], [False], [True]])


def test_icc_needs_more_than_one_task() -> None:
    with pytest.raises(ValueError, match="at least two tasks"):
        icc([[True, False]])


# --- Task 3.2: reports --------------------------------------------------------


def a_report(**overrides: Any) -> Report:
    baseline = Arm("A", tuple(result(BASE, f"t{i}", 3 if i % 3 else 0) for i in range(9)))
    treatment = Arm("B", tuple(result(OTHER, f"t{i}", 3 if i % 2 else 0) for i in range(9)))
    fields: dict[str, Any] = {
        "baseline": baseline,
        "treatment": treatment,
        "state_completeness": StateCompleteness.FILESYSTEM,
        "median_context_fidelity": 0.951,
    }
    fields.update(overrides)
    return Report(**fields)


def test_the_limits_are_in_the_header_not_an_appendix() -> None:
    # A limit that appears after the conclusion has already been read is not a
    # limit. In the JSON that means near the top; in the HTML, before the result.
    payload = json.loads(render_json(a_report(), resamples=200))
    keys = list(payload)
    assert keys.index("state_completeness") < keys.index("statistics")
    assert keys.index("median_context_fidelity") < keys.index("statistics")

    document = render_html(a_report(), resamples=200)
    assert document.index("State completeness") < document.index("<h2>Result</h2>")
    assert document.index("Median context fidelity") < document.index("<h2>Result</h2>")


def test_every_report_reprints_state_completeness() -> None:
    payload = json.loads(render_json(a_report(), resamples=200))
    assert payload["state_completeness"] == "filesystem"


def test_an_unmeasured_fidelity_says_so_rather_than_showing_a_number() -> None:
    document = render_html(a_report(median_context_fidelity=None), resamples=200)
    assert "not measured" in document


def test_the_html_is_self_contained() -> None:
    # A report that needs the network to render is a report that stops
    # rendering, and an artifact nobody can open in five years is not evidence.
    document = render_html(a_report(), resamples=200)
    for reference in ("<script src", "<link ", "@import", 'src="http', 'href="http'):
        assert reference not in document


def test_the_report_carries_the_test_and_the_resampling_unit() -> None:
    statistics = json.loads(render_json(a_report(), resamples=200))["statistics"]
    assert statistics["test"].startswith("exact McNemar")
    assert statistics["resampling_unit"] == "tasks"
    assert len(statistics["difference_ci"]) == 2


def test_a_report_refuses_incomparable_scorers() -> None:
    # A report is exactly where an incomparable pair would stop looking
    # incomparable.
    baseline = Arm("A", (result(BASE, "t0", 3, digest="a" * 64),))
    treatment = Arm("B", (result(OTHER, "t0", 3, digest="b" * 64),))

    with pytest.raises(ScorerMismatchError):
        Report(
            baseline=baseline,
            treatment=treatment,
            state_completeness=StateCompleteness.FILESYSTEM,
            median_context_fidelity=0.9,
        )


def test_a_report_needs_the_same_tasks_in_both_arms() -> None:
    with pytest.raises(ValueError, match="same tasks"):
        Report(
            baseline=Arm("A", (result(BASE, "t0", 3),)),
            treatment=Arm("B", (result(OTHER, "t0", 3), result(OTHER, "t1", 3))),
            state_completeness=StateCompleteness.FILESYSTEM,
            median_context_fidelity=0.9,
        )


def test_a_continuation_report_carries_the_banner() -> None:
    from adp_replay.replay import CONTINUATION_BANNER

    diagnostic = ReplayResult(
        task_id="t0",
        model=OTHER,
        mode=ReplayMode.FORK_AT_STEP,
        forked_from_step=3,
        attempts=result(OTHER, "t0", 3).attempts,
    )
    report = Report(
        baseline=Arm("A", (result(BASE, "t0", 3),)),
        treatment=Arm("B", (diagnostic,)),
        state_completeness=StateCompleteness.FILESYSTEM,
        median_context_fidelity=0.9,
    )

    assert report.banner == CONTINUATION_BANNER
    assert not report.is_model_comparison
    # Escaped in the HTML, because it is rendered as text rather than trusted as
    # markup — but present, which is the property that matters.
    assert html.escape(CONTINUATION_BANNER) in render_html(report, resamples=200)
    assert CONTINUATION_BANNER in json.loads(render_json(report, resamples=200))["banner"]


def test_errors_are_reported_rather_than_folded_into_failures() -> None:
    unverifiable = ReplayResult(
        task_id="t0",
        model=BASE,
        mode=ReplayMode.FORK_AT_ZERO,
        attempts=(
            Attempt(
                task_id="t0",
                model=BASE,
                repetition=1,
                outcome=AttemptOutcome(passed=True),
                verdict=Verdict.ERROR,
                scorer_spec_digest=DIGEST,
                downgraded_because=("chains_ok",),
            ),
        ),
    )
    report = Report(
        baseline=Arm("A", (unverifiable,)),
        treatment=Arm("B", (result(OTHER, "t0", 1, n=1),)),
        state_completeness=StateCompleteness.FILESYSTEM,
        median_context_fidelity=0.9,
    )

    statistics = report.statistics(resamples=200)
    assert statistics["baseline"]["errors"] == 1
