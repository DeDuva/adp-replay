"""The registered metric and the document that registers it must agree (Task 0.3a).

Two copies of a commitment is one copy too many unless something enforces that
they are the same copy. `registered.py` exists so Task 0.3b reads the definition
instead of restating it; this file is what stops the transcription from drifting
away from the document a reader is pointed at.

A failure here is never fixed by editing one side to match the other. It means a
pre-registered number moved, which is an amendment.
"""

from __future__ import annotations

import re
from pathlib import Path

from adp_replay.context.registered import (
    CLASSIFICATION_COEFFICIENTS,
    ELEMENT_WEIGHTS,
    G0_THRESHOLD,
    MINIMUM_PROVIDERS,
    REGISTERED_AGAINST_COMMIT,
    REGISTERED_ON,
    REGISTERED_PROVIDERS,
    Capability,
    Classification,
    ElementType,
)

DOC = Path(__file__).resolve().parents[1] / "docs" / "pre-registration.md"

# `| `system_instruction` | 3 | the system prompt |`
WEIGHT_ROW = re.compile(r"^\|\s*`(?P<name>\w+)`\s*\|\s*(?P<weight>\d+)\s*\|", re.MULTILINE)


def registered_text() -> str:
    return DOC.read_text(encoding="utf-8")


def test_the_weight_table_is_transcribed_exactly() -> None:
    from_doc = {m["name"]: int(m["weight"]) for m in WEIGHT_ROW.finditer(registered_text())}
    assert from_doc, "the weight table could not be found in docs/pre-registration.md"

    from_code = {element.value: weight for element, weight in ELEMENT_WEIGHTS.items()}
    assert from_doc == from_code


def test_every_element_type_carries_a_weight() -> None:
    # An unweighted type would be silently excluded from the score.
    assert set(ELEMENT_WEIGHTS) == set(ElementType)


def test_weights_are_the_three_registered_bands() -> None:
    assert set(ELEMENT_WEIGHTS.values()) == {1, 2, 3}


def test_coefficients_are_the_registered_ones() -> None:
    assert CLASSIFICATION_COEFFICIENTS == {
        Classification.PRESERVED: 1.0,
        Classification.TRANSFORMED: 0.5,
        Classification.LOST: 0.0,
    }
    # The 0.5 is the load-bearing one: it is the number a later measurement
    # would most want to move, so the document states it in those terms.
    assert "fixed at 0.5 and is not tunable" in registered_text()


def test_the_threshold_is_the_registered_one() -> None:
    assert G0_THRESHOLD == 0.85
    assert "median fidelity ≥ 0.85" in registered_text()


def test_the_threshold_applies_to_every_cell_not_a_pool() -> None:
    assert "every in-scope cell has a median fidelity ≥ 0.85" in registered_text()


def test_capabilities_are_scored_separately() -> None:
    assert {c.value for c in Capability} == {"fork_at_zero", "fork_at_step"}
    assert "separate cells and never pooled" in registered_text()


def test_provider_scope_and_its_permitted_narrowing_are_registered() -> None:
    assert REGISTERED_PROVIDERS == ("anthropic", "openai", "google")
    assert MINIMUM_PROVIDERS == 2

    doc = registered_text().lower()
    for provider in REGISTERED_PROVIDERS:
        assert provider in doc
    assert "two providers and two ordered pairs" in doc


def test_registration_is_dated_and_pinned_to_a_commit() -> None:
    doc = registered_text()
    assert REGISTERED_ON in doc
    assert REGISTERED_AGAINST_COMMIT in doc
    # "not yet registered" is the scaffold's placeholder. Its survival in the
    # G0 section would mean this whole file is asserting against a stub.
    g0_section = doc.split("## Experiment design")[0]
    assert "not yet registered" not in g0_section


def test_the_threshold_is_written_down_in_exactly_one_place() -> None:
    # Until Task 0.3b landed, this file asserted that no scoring code existed
    # yet — the check that the pass mark was not settled by the work that has to
    # clear it. That ordering is now history, and git holds it. What has to keep
    # holding is the property the ordering protected: the scoring code reads the
    # registered numbers and never carries its own copy, so the metric cannot be
    # nudged by editing the module that measures against it.
    threshold = str(G0_THRESHOLD)
    package = Path(__file__).resolve().parents[1] / "src" / "adp_replay"

    carriers = sorted(
        path.relative_to(package).as_posix()
        for path in package.rglob("*.py")
        if threshold in path.read_text(encoding="utf-8")
    )
    assert carriers == ["context/registered.py"]


def test_the_scoring_code_reads_the_registration() -> None:
    from adp_replay.context import fidelity

    source = Path(fidelity.__file__).read_text(encoding="utf-8")
    assert "from adp_replay.context.registered import" in source
    # The weight table and the coefficients are applied through the accessors,
    # never transcribed a second time.
    assert "weight_of(" in source
    assert "coefficient_of(" in source
