"""Overhead benchmark and Gate G1 (Task 1.5).

The measurement itself needs a live ADP and is in `docs/g1-overhead-report.md`.
What is tested here is the arithmetic and the gate logic — the parts that could
report a pass that was not one.
"""

from __future__ import annotations

from typing import Any

import pytest

from adp_replay.recording import G1_THRESHOLD, REFERENCE_STEP_SECONDS, BenchmarkReport, benchmark
from adp_replay.recording.benchmark import Measurement, measure


def point(step: float, baseline: float, recorded: float) -> Measurement:
    return Measurement(
        step_seconds=step, steps=10, baseline_seconds=baseline, recorded_seconds=recorded
    )


def test_overhead_is_the_fraction_added_to_the_baseline() -> None:
    assert point(0.25, 10.0, 11.0).overhead == pytest.approx(0.10)
    assert point(0.25, 10.0, 10.0).overhead == pytest.approx(0.0)


def test_the_budget_is_ten_percent() -> None:
    assert G1_THRESHOLD == 0.10
    assert point(0.25, 10.0, 11.0).passes
    assert not point(0.25, 10.0, 11.01).passes


def test_the_gate_reads_the_median_as_the_plan_says() -> None:
    # Not the best point, and not the mean — a mean would let one very slow step
    # duration hide a bad result at fast ones.
    report = BenchmarkReport(
        measurements=(
            point(0.05, 10.0, 11.5),
            point(0.1, 10.0, 10.5),
            point(REFERENCE_STEP_SECONDS, 10.0, 10.2),
        )
    )
    assert report.median_overhead == pytest.approx(0.05)


def test_a_failure_at_the_reference_duration_fails_the_gate() -> None:
    """Even when the median passes.

    The reference is the duration the gate was meant to be read at. Letting the
    median override it would make the choice of sampled durations the thing that
    decides the gate — add three slow points and any result passes.
    """
    report = BenchmarkReport(
        measurements=(
            point(REFERENCE_STEP_SECONDS, 10.0, 13.0),  # 30% over, at the reference
            point(1.0, 10.0, 10.1),
            point(2.0, 10.0, 10.1),
        )
    )
    assert report.median_overhead < G1_THRESHOLD
    assert not report.passes


def test_a_clean_result_passes() -> None:
    report = BenchmarkReport(
        measurements=(
            point(0.1, 10.0, 10.2),
            point(REFERENCE_STEP_SECONDS, 10.0, 10.1),
        )
    )
    assert report.passes
    assert report.to_dict()["passed"] is True


def test_the_report_says_it_included_adp_round_trips() -> None:
    # The plan is explicit that the budget covers the real system rather than
    # the recorder in isolation, so the claim is in the artifact.
    payload = BenchmarkReport(measurements=(point(0.25, 10.0, 10.1),)).to_dict()
    assert payload["inclusive_of_adp_round_trips"] is True
    assert payload["reference_step_seconds"] == REFERENCE_STEP_SECONDS


def test_the_final_flush_is_inside_the_measurement() -> None:
    # A recorder that abandoned its tail would look fast by not doing its job.
    called: list[str] = []

    elapsed = measure(
        step_seconds=0.0,
        steps=3,
        record=lambda index: called.append(f"record-{index}"),
        finish=lambda: called.append("finish"),
        work=lambda _: None,
    )

    assert called == ["record-0", "record-1", "record-2", "finish"]
    assert elapsed >= 0.0


def test_the_benchmark_measures_every_step_duration() -> None:
    def make_recorder() -> tuple[Any, Any]:
        return (lambda index: None), (lambda: None)

    report = benchmark(
        make_recorder,
        step_durations=(0.01, 0.02),
        steps=3,
        trials=2,
        work=lambda _: None,
    )

    assert [m.step_seconds for m in report.measurements] == [0.01, 0.02]
    assert report.trials == 2


def test_a_zero_baseline_does_not_divide_by_zero() -> None:
    assert point(0.0, 0.0, 1.0).overhead == float("inf")
