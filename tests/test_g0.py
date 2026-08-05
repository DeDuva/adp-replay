"""Gate G0's aggregation and its reading (Task 0.3b).

The tests that matter here are the ones that would let a failing gate report a
pass: pooling capabilities, letting a long trajectory outvote a short one, or
taking a median across cells instead of within them.
"""

from __future__ import annotations

import json

import pytest

from adp_replay.context.fidelity import FidelityScore
from adp_replay.context.g0 import Cell, G0Report, Grounding, TaskReading, run_probe
from adp_replay.context.registered import G0_THRESHOLD, Capability


def reading(task_id: str, *scores: float) -> TaskReading:
    return TaskReading(task_id=task_id, scores=tuple(FidelityScore(score=s) for s in scores))


def cell(*tasks: TaskReading, capability: Capability = Capability.FORK_AT_ZERO) -> Cell:
    return Cell(source="a", target="b", capability=capability, tasks=tasks)


# --- the two-level median -----------------------------------------------------


def test_a_long_trajectory_does_not_outvote_a_short_one() -> None:
    # One task with thirty bad contexts, two with one good context each. Pooled
    # over contexts the median is 0.10; over tasks it is 1.0, which is the
    # registered aggregation and the same rule Task 3.1 applies to resampling.
    noisy = reading("long", *([0.10] * 30))
    good_a = reading("short-a", 1.0)
    good_b = reading("short-b", 1.0)

    assert cell(noisy, good_a, good_b).median == pytest.approx(1.0)


def test_a_task_is_summarized_by_its_own_median_first() -> None:
    assert reading("t", 0.2, 0.9, 1.0).median == pytest.approx(0.9)


def test_the_spread_is_reported_beside_the_median() -> None:
    low, high = cell(reading("a", 0.5), reading("b", 0.8), reading("c", 1.0)).iqr
    assert low == pytest.approx(0.65)
    assert high == pytest.approx(0.9)


def test_a_single_task_still_reports_a_spread() -> None:
    # A narrowed corpus must not make the report raise instead of answering.
    low, high = cell(reading("only", 0.7)).iqr
    assert (low, high) == (0.7, 0.7)


# --- the pass mark ------------------------------------------------------------


def test_a_cell_passes_exactly_at_the_threshold() -> None:
    assert cell(reading("t", G0_THRESHOLD)).passed
    assert not cell(reading("t", G0_THRESHOLD - 0.001)).passed


def test_one_failing_cell_fails_the_gate() -> None:
    # Not the pooled median, not most cells.
    report = G0Report(
        cells=(
            cell(reading("t", 1.0)),
            cell(reading("t", 0.5), capability=Capability.FORK_AT_STEP),
        ),
        providers=("a", "b"),
        corpus_digest="sha256:test",
    )
    assert not report.passed
    assert [c.capability for c in report.failing] == [Capability.FORK_AT_STEP]


def test_capabilities_are_never_pooled() -> None:
    # A perfect fork-at-zero must not carry a failing fork-at-step. Pooling the
    # two cells here would give 0.75 and hide the failure behind the easy case.
    report = G0Report(
        cells=(
            cell(reading("t", 1.0)),
            cell(reading("t", 0.5), capability=Capability.FORK_AT_STEP),
        ),
        providers=("a", "b"),
        corpus_digest="sha256:test",
    )
    assert len(report.cells) == 2
    assert not report.passed


# --- grounding ----------------------------------------------------------------


def test_a_report_is_only_as_grounded_as_its_weakest_cell() -> None:
    verified = Cell(
        source="a",
        target="b",
        capability=Capability.FORK_AT_ZERO,
        tasks=(reading("t", 1.0),),
        grounding=Grounding.PROVIDER_VERIFIED,
    )
    mixed = G0Report(
        cells=(verified, cell(reading("t", 1.0))),
        providers=("a", "b"),
        corpus_digest="sha256:test",
    )
    assert mixed.grounding is Grounding.ROUND_TRIP_ONLY


def test_a_round_trip_only_report_says_so_in_the_body() -> None:
    report = run_probe()
    assert report.grounding is Grounding.ROUND_TRIP_ONLY
    assert "Round-trip only" in report.to_markdown()
    assert report.to_dict()["grounding"] == "round_trip_only"


# --- the probe ----------------------------------------------------------------


def test_the_probe_scores_every_ordered_pair_and_capability() -> None:
    report = run_probe()
    # 3 providers -> 6 ordered pairs, 2 capabilities each.
    assert len(report.cells) == 12
    assert {(c.source, c.target) for c in report.cells} == {
        (a, b)
        for a in ("anthropic", "openai", "google")
        for b in ("anthropic", "openai", "google")
        if a != b
    }


def test_the_probe_is_deterministic() -> None:
    first, second = run_probe().to_dict(), run_probe().to_dict()
    assert first == second


def test_narrowing_below_the_registered_floor_is_refused() -> None:
    with pytest.raises(ValueError, match="floor"):
        run_probe(providers=("anthropic",))


def test_an_unknown_provider_is_refused() -> None:
    with pytest.raises(ValueError, match="no translator"):
        run_probe(providers=("anthropic", "nonesuch"))


def test_the_report_names_the_corpus_it_was_read_against() -> None:
    # A reading taken against stand-in contexts must never be mistaken for one
    # taken against recorded trajectories.
    report = run_probe()
    assert report.corpus_digest.startswith("sha256:")
    assert report.corpus_digest in report.to_markdown()


def test_the_report_serializes_to_json() -> None:
    payload = json.loads(json.dumps(run_probe().to_dict()))
    assert payload["gate"] == "G0"
    assert payload["threshold"] == G0_THRESHOLD
    assert all("lost" in c for c in payload["cells"])


def test_fork_at_zero_is_perfect_for_every_pair() -> None:
    # The initial context is a system prompt, tool definitions, and a task
    # statement — the part every format can carry. If this ever regresses, the
    # primary capability is broken and the reading below it means nothing.
    report = run_probe()
    zero = [c for c in report.cells if c.capability is Capability.FORK_AT_ZERO]
    assert all(c.median == pytest.approx(1.0) for c in zero)
