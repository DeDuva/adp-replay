"""Power analysis (Task 0.4) and the exact McNemar test it powers against.

The properties worth pinning are the ones that would let a design ship
underpowered: a recommendation that does not actually meet its own target, a
search that loses a repetition count to simulation noise, and a test that is
approximated where the sample is small.
"""

from __future__ import annotations

import math

import pytest

from adp_replay.stats.paired import mcnemar_exact
from adp_replay.stats.power import (
    Assumptions,
    calibrate,
    majority_pass_probability,
    recommend_design,
    render_markdown,
    report,
    simulate_power,
)

# Small but real: enough to exercise the search without a minute of simulation.
FAST = {
    "task_grid": (20, 40, 60, 80, 100, 140, 200, 300),
    "repetition_grid": (1, 3, 5),
    "search_trials": 150,
    "trials": 600,
}


@pytest.fixture(scope="module")
def recommendation() -> object:
    """One search, shared. Every test below inspects the same recommendation."""
    return recommend_design(target_power=0.8, **FAST)


# --- exact McNemar ------------------------------------------------------------


def test_only_discordant_pairs_carry_information() -> None:
    # A task both models solved says nothing about which is better. Two runs
    # differing only in their concordant counts must give the same p-value.
    assert mcnemar_exact(0, 8, 1, 0) == mcnemar_exact(500, 8, 1, 900)


def test_no_discordant_pairs_is_no_evidence() -> None:
    # Not an exception: a sweep over many tasks must not blow up on a tie.
    assert mcnemar_exact(40, 0, 0, 60) == 1.0


def test_a_perfectly_lopsided_split_matches_the_binomial_tail() -> None:
    # Ten discordant pairs all favouring one model: 2 * 0.5**10.
    assert mcnemar_exact(0, 0, 10, 0) == pytest.approx(2 * 0.5**10)


def test_an_even_split_cannot_reject() -> None:
    assert mcnemar_exact(0, 5, 5, 0) == 1.0


def test_the_test_is_symmetric_in_the_two_models() -> None:
    assert mcnemar_exact(0, 3, 11, 0) == mcnemar_exact(0, 11, 3, 0)


def test_p_values_stay_in_range() -> None:
    for a in range(6):
        for b in range(6):
            assert 0.0 <= mcnemar_exact(0, a, b, 0) <= 1.0


def test_negative_counts_are_rejected() -> None:
    with pytest.raises(ValueError, match="negative"):
        mcnemar_exact(0, -1, 2, 0)


# --- the data-generating model ------------------------------------------------


def test_calibration_hits_the_assumed_marginal_rates() -> None:
    # The assumptions are stated on the probability scale; the model works on
    # the logit scale. If this drifts, every reported effect size is a
    # different one from the one that was assumed.
    from adp_replay.stats.power import _logistic, _mean_success

    assumptions = Assumptions(base_rate=0.45, effect_size=0.10, between_task_sd=1.5)
    mu, shift = calibrate(assumptions)

    assert _mean_success(mu, 1.5) == pytest.approx(0.45, abs=1e-4)
    assert _mean_success(mu + shift, 1.5) == pytest.approx(0.55, abs=1e-4)
    assert _logistic(mu) > 0  # sanity: a real number came back


def test_calibration_refuses_rates_outside_the_unit_interval() -> None:
    with pytest.raises(ValueError, match=r"inside \(0, 1\)"):
        calibrate(Assumptions(base_rate=0.95, effect_size=0.10))


def test_majority_pass_is_the_binomial_tail() -> None:
    # Three repetitions at p: P(2 or 3 successes).
    p = 0.6
    expected = 3 * p**2 * (1 - p) + p**3
    assert majority_pass_probability(p, 3) == pytest.approx(expected, abs=1e-4)


def test_a_single_repetition_is_just_the_run() -> None:
    assert majority_pass_probability(0.37, 1) == pytest.approx(0.37, abs=1e-4)


def test_repetitions_sharpen_a_task_towards_its_own_side() -> None:
    # Above half, more repetitions make a task more reliably counted solved;
    # below half, less. This is the whole reason n buys power.
    assert majority_pass_probability(0.7, 9) > majority_pass_probability(0.7, 3) > 0.7
    assert majority_pass_probability(0.3, 9) < majority_pass_probability(0.3, 3) < 0.3


# --- the simulation -----------------------------------------------------------


def test_power_rises_with_the_task_count() -> None:
    small = simulate_power(30, 3, trials=400, seed=3)
    large = simulate_power(200, 3, trials=400, seed=3)
    assert large > small


def test_a_null_effect_rejects_at_about_alpha() -> None:
    # The test's own false-positive rate. An exact test is conservative, so
    # this is bounded above rather than centred: what must not happen is
    # rejecting more often than alpha.
    settings = Assumptions(effect_size=1e-9, alpha=0.05)
    assert simulate_power(150, 3, assumptions=settings, trials=1500, seed=5) <= 0.05


def test_the_simulation_is_deterministic_under_a_seed() -> None:
    assert simulate_power(50, 3, trials=200, seed=11) == simulate_power(50, 3, trials=200, seed=11)


def test_an_empty_design_is_refused() -> None:
    with pytest.raises(ValueError, match="at least one task"):
        simulate_power(0, 3)


# --- the recommendation -------------------------------------------------------


def test_the_recommendation_actually_meets_its_target(recommendation) -> None:
    # The property the search exists to guarantee, and the one it originally
    # got wrong: a coarse screen that crosses the target is as likely to have
    # crossed it by luck as by merit, so the reported power is a confirmation
    # rather than the estimate that won the scan.
    assert recommendation.power >= recommendation.target_power


def test_the_recommendation_carries_its_assumptions(recommendation) -> None:
    # A corpus size quoted without them is a number someone reuses after the
    # assumptions have moved.
    assert recommendation.assumed_effect_size == recommendation.assumptions.effect_size
    assert recommendation.assumed_variance == pytest.approx(
        recommendation.assumptions.between_task_sd**2
    )


def test_single_run_designs_are_excluded_not_silently_lost(recommendation) -> None:
    # Task 3.1 commits to a between/within variance decomposition, which is
    # undefined at one repetition. Cheaper designs that fall foul of that are
    # reported with their numbers rather than dropped.
    assert recommendation.repetitions >= 3
    for _tasks, reps, _power in recommendation.excluded_cheaper:
        assert reps < 3


def test_a_smaller_effect_needs_a_bigger_corpus() -> None:
    big = recommend_design(target_power=0.8, effect_size=0.15, **FAST)
    small = recommend_design(target_power=0.8, effect_size=0.10, **FAST)
    assert small.tasks * small.repetitions >= big.tasks * big.repetitions


def test_an_undetectable_effect_is_an_error_not_a_guess() -> None:
    with pytest.raises(ValueError, match="no design on the grid"):
        recommend_design(target_power=0.99, effect_size=0.005, **FAST)


def test_the_sensitivity_curve_covers_both_assumptions(recommendation) -> None:
    assert len(recommendation.effect_sensitivity) >= 3
    assert len(recommendation.variance_sensitivity) >= 3
    # Monotone in the effect size: a bigger true difference is easier to find.
    powers = [power for _, power in recommendation.effect_sensitivity]
    assert powers == sorted(powers)


def test_the_report_states_the_audit_target_task_1_3_inherits(recommendation) -> None:
    payload = report(recommendation)
    assert payload["audit_target"] == math.ceil(recommendation.tasks * 1.25)
    assert payload["test"].startswith("exact McNemar")
    assert payload["resampling_unit"] == "tasks"


def test_the_markdown_names_the_test_and_the_resampling_unit(recommendation) -> None:
    rendered = render_markdown(recommendation)
    assert "exact McNemar" in rendered
    assert "resample **tasks**, never trajectories" in rendered
