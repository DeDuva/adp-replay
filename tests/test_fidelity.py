"""The fidelity probe (Task 0.3b), scored against the Task 0.3a registration.

The most important test here is the identity round-trip. A translator that
cannot reproduce a context it authored itself has a bug, and every cross-provider
number it produces would be that bug rather than a fact about the providers — so
that check runs before any of the comparative ones mean anything.
"""

from __future__ import annotations

import pytest

from adp_replay.context.canonical import Element, Role, Turn, build, normalize
from adp_replay.context.corpus import PHASE0_CORPUS, as_sourced_from, corpus_digest
from adp_replay.context.fidelity import (
    ElementVerdict,
    classify,
    score_fidelity,
    score_translation,
    score_verdicts,
)
from adp_replay.context.providers import TRANSLATORS, round_trip
from adp_replay.context.registered import Classification, ElementType

TEXT = ElementType.USER_MESSAGE_TEXT
TOOL_DEF = ElementType.TOOL_DEFINITION


# --- the translators can reproduce themselves ---------------------------------


@pytest.mark.parametrize("provider", sorted(TRANSLATORS))
@pytest.mark.parametrize("task", PHASE0_CORPUS, ids=lambda t: t.task_id)
def test_a_provider_round_trips_its_own_contexts_losslessly(provider: str, task: object) -> None:
    translator = TRANSLATORS[provider]
    for context in (task.initial_context(), *task.step_contexts()):  # type: ignore[attr-defined]
        native = as_sourced_from(context, translator)
        assert score_translation(native, translator).score == pytest.approx(1.0)


@pytest.mark.parametrize("provider", sorted(TRANSLATORS))
def test_sourcing_is_a_fixed_point(provider: str) -> None:
    # as_sourced_from must be idempotent, or "what a context recorded there
    # would have contained" is not well defined and the pair scores drift with
    # how many times the helper was applied.
    translator = TRANSLATORS[provider]
    context = PHASE0_CORPUS[0].context(4)
    once = as_sourced_from(context, translator)
    twice = as_sourced_from(once, translator)
    assert once.elements == twice.elements


# --- classification -----------------------------------------------------------


def test_an_identical_element_is_preserved() -> None:
    context = build(system="be helpful")
    verdicts = classify(context, context)
    assert [v.classification for v in verdicts] == [Classification.PRESERVED]


def test_a_dropped_attribute_is_a_transform_not_a_loss() -> None:
    source = build(
        turns=[
            Turn(
                Role.ASSISTANT,
                (Element(ElementType.TOOL_CALL, {"id": "c1", "name": "bash", "arguments": {}}),),
            )
        ]
    )
    stripped = build(
        turns=[
            Turn(
                Role.ASSISTANT,
                (Element(ElementType.TOOL_CALL, {"name": "bash", "arguments": {}}),),
            )
        ]
    )
    call = next(v for v in classify(source, stripped) if v.element.type is ElementType.TOOL_CALL)
    assert call.classification is Classification.TRANSFORMED


def test_a_changed_content_is_a_loss_not_a_transform() -> None:
    source = build(system="run the tests")
    different = build(system="delete the tests")
    system = next(
        v for v in classify(source, different) if v.element.type is ElementType.SYSTEM_INSTRUCTION
    )
    assert system.classification is Classification.LOST


def test_content_arriving_under_another_type_is_a_transform() -> None:
    # A prefill relayed as a completed assistant turn: the text arrived, the
    # instruction to continue it did not.
    source = build(
        turns=[Turn(Role.ASSISTANT, (Element(ElementType.ASSISTANT_PREFILL, {"text": "## Root"}),))]
    )
    flattened = build(
        turns=[
            Turn(
                Role.ASSISTANT,
                (Element(ElementType.ASSISTANT_MESSAGE_TEXT, {"text": "## Root"}),),
            )
        ]
    )
    prefill = next(
        v for v in classify(source, flattened) if v.element.type is ElementType.ASSISTANT_PREFILL
    )
    assert prefill.classification is Classification.TRANSFORMED


def test_merging_consecutive_same_role_turns_is_a_transform() -> None:
    # The registered transform: a format that requires alternating roles folds
    # two user turns into one. Nothing about what the model reads has changed
    # except where one turn ends.
    source = build(
        turns=[
            Turn(Role.USER, (Element(TEXT, {"text": "a"}),)),
            Turn(Role.USER, (Element(TEXT, {"text": "b"}),)),
        ]
    )
    merged = build(
        turns=[
            Turn(Role.USER, (Element(TEXT, {"text": "a"}), Element(TEXT, {"text": "b"}))),
        ]
    )
    structure = next(
        v for v in classify(source, merged) if v.element.type is ElementType.TURN_STRUCTURE
    )
    assert structure.classification is Classification.TRANSFORMED


def test_collapsing_a_tool_turn_into_a_user_turn_is_a_loss() -> None:
    # Not the registered same-role merge: a model that can no longer tell a tool
    # result from something the user typed has lost the structure, not had it
    # rearranged. The translators in this repo avoid it — they carry tool
    # results inside a user message but split them back out on parse — so this
    # asserts the rule rather than a behaviour any pair currently exhibits.
    source = build(
        turns=[
            Turn(Role.TOOL, (Element(ElementType.TOOL_RESULT, {"content": "ok"}),)),
            Turn(Role.USER, (Element(TEXT, {"text": "next"}),)),
        ]
    )
    collapsed = build(
        turns=[
            Turn(
                Role.USER,
                (
                    Element(ElementType.TOOL_RESULT, {"content": "ok"}),
                    Element(TEXT, {"text": "next"}),
                ),
            )
        ]
    )
    structure = next(
        v for v in classify(source, collapsed) if v.element.type is ElementType.TURN_STRUCTURE
    )
    assert structure.classification is Classification.LOST


def test_a_reordered_turn_sequence_is_a_loss() -> None:
    source = build(
        turns=[
            Turn(Role.USER, (Element(TEXT, {"text": "a"}),)),
            Turn(Role.ASSISTANT, (Element(ElementType.ASSISTANT_MESSAGE_TEXT, {"text": "b"}),)),
        ]
    )
    swapped = build(
        turns=[
            Turn(Role.ASSISTANT, (Element(ElementType.ASSISTANT_MESSAGE_TEXT, {"text": "b"}),)),
            Turn(Role.USER, (Element(TEXT, {"text": "a"}),)),
        ]
    )
    structure = next(
        v for v in classify(source, swapped) if v.element.type is ElementType.TURN_STRUCTURE
    )
    assert structure.classification is Classification.LOST


def test_one_survivor_cannot_be_credited_to_several_sources() -> None:
    # A translator that collapses three results into one must not score as if
    # all three arrived.
    source = build(
        turns=[
            Turn(
                Role.TOOL,
                tuple(Element(ElementType.TOOL_RESULT, {"content": "same"}) for _ in range(3)),
            )
        ]
    )
    collapsed = build(
        turns=[Turn(Role.TOOL, (Element(ElementType.TOOL_RESULT, {"content": "same"}),))]
    )

    results = [v for v in classify(source, collapsed) if v.element.type is ElementType.TOOL_RESULT]
    assert [v.classification for v in results].count(Classification.PRESERVED) == 1
    assert [v.classification for v in results].count(Classification.LOST) == 2


# --- the registered aggregation -----------------------------------------------


def test_scoring_is_per_type_not_per_instance() -> None:
    # Twenty surviving user texts and one dropped tool definition. Per instance
    # this reads 0.95 and sails through; per type it is the registered number
    # and the loss is visible.
    texts = [
        ElementVerdict(Element(TEXT, {"text": f"{i}"}), Classification.PRESERVED) for i in range(20)
    ]
    dropped = ElementVerdict(Element(TOOL_DEF, {"name": "bash", "schema": {}}), Classification.LOST)

    score = score_verdicts([*texts, dropped]).score
    # weights: user_message_text 3, tool_definition 3 -> (3*1 + 3*0) / 6
    assert score == pytest.approx(0.5)


def test_an_absent_type_is_excluded_rather_than_scored_zero() -> None:
    # A context with no images is not thereby less faithful.
    only_text = score_verdicts(
        [ElementVerdict(Element(TEXT, {"text": "hi"}), Classification.PRESERVED)]
    )
    assert only_text.score == pytest.approx(1.0)


def test_weights_come_from_the_registration() -> None:
    # citation_annotation is weight 1, user_message_text weight 3: losing the
    # cheap one must cost a quarter, not a half.
    verdicts = [
        ElementVerdict(Element(TEXT, {"text": "hi"}), Classification.PRESERVED),
        ElementVerdict(
            Element(ElementType.CITATION_ANNOTATION, {"source": "a", "text": "b"}),
            Classification.LOST,
        ),
    ]
    assert score_verdicts(verdicts).score == pytest.approx(3 / 4)


def test_a_transform_scores_the_registered_half() -> None:
    verdicts = [ElementVerdict(Element(TEXT, {"text": "hi"}), Classification.TRANSFORMED)]
    assert score_verdicts(verdicts).score == pytest.approx(0.5)


def test_the_score_reports_what_accounts_for_the_shortfall() -> None:
    task = PHASE0_CORPUS[0]
    source = as_sourced_from(task.context(4), TRANSLATORS["anthropic"])
    score = score_translation(source, TRANSLATORS["google"])

    assert "reasoning_trace" in score.lost
    assert "tool_call" in score.transformed
    assert score.per_type["tool_definition"] == pytest.approx(1.0)


# --- normalization ------------------------------------------------------------


def test_normalization_ignores_whitespace_and_key_order() -> None:
    assert normalize("  a   b ") == normalize("a b")
    assert normalize({"a": 1, "b": 2}) == normalize({"b": 2, "a": 1})


def test_normalization_compares_numbers_by_value() -> None:
    # A translator that serializes max_tokens through JSON and back must not
    # show a loss no model could observe.
    assert normalize({"max_tokens": 4096}) == normalize({"max_tokens": 4096.0})


# --- corpus -------------------------------------------------------------------


def test_the_corpus_exercises_every_registered_element_type() -> None:
    seen = {
        element.type for task in PHASE0_CORPUS for element in task.context(len(task.turns)).elements
    }
    assert seen == set(ElementType), f"never exercised: {sorted(set(ElementType) - seen)}"


def test_the_corpus_digest_identifies_the_contexts_scored() -> None:
    assert corpus_digest().startswith("sha256:")
    assert corpus_digest(PHASE0_CORPUS[:2]) != corpus_digest()


def test_step_contexts_resume_only_where_the_model_would_act() -> None:
    task = PHASE0_CORPUS[0]
    for context in task.step_contexts():
        assert context.turns()[-1].role in (Role.USER, Role.TOOL)


def test_round_trip_is_the_registered_procedure() -> None:
    context = PHASE0_CORPUS[0].initial_context()
    translator = TRANSLATORS["openai"]
    assert (
        round_trip(context, translator).elements
        == translator.parse(translator.render(context)).elements
    )


def test_scoring_an_empty_context_is_not_a_division_by_zero() -> None:
    assert score_fidelity(build(), build()).score == pytest.approx(1.0)
