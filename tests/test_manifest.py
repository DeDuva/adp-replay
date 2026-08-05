"""Manifest specification (Task 0.1) and state-completeness levels (Task 0.2).

The done-conditions from the execution plan are the first four tests here:
round-trip digest stability, insensitivity to `run_id` and to key ordering, and
a manifest that cannot be built without declaring what its snapshots captured.
"""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from adp_replay.manifest import (
    ManifestEnvelope,
    ReplayMode,
    RunManifest,
    StateCompleteness,
    VerdictRecord,
    manifest_digest,
)
from adp_replay.verdict import Verdict
from tests.factories import DIGEST_E, a_manifest, a_step, an_adp_binding

# --- Task 0.1 done-conditions -------------------------------------------------


def test_manifest_round_trips_with_a_stable_digest() -> None:
    original = a_manifest()
    restored = RunManifest.model_validate_json(original.model_dump_json())

    assert restored == original
    assert restored.digest == original.digest
    assert manifest_digest(restored) == original.digest


def test_digest_is_insensitive_to_run_id() -> None:
    # The self-certifying property: a reader who does not know where the run was
    # filed still recomputes the published number.
    baseline = a_manifest().digest

    assert a_manifest(run_id="somewhere-else").digest == baseline
    assert a_manifest(adp=an_adp_binding(run_id="adp-run-77")).digest == baseline


def test_digest_is_insensitive_to_key_ordering() -> None:
    manifest = a_manifest()
    payload = json.loads(manifest.model_dump_json())

    rng = random.Random(0)
    shuffled = _shuffle_keys(payload, rng)
    assert list(shuffled) != list(payload), "the shuffle did not actually reorder anything"

    assert RunManifest.model_validate(shuffled).digest == manifest.digest


def test_digest_covers_content_that_is_not_a_storage_id() -> None:
    # The complement of the two tests above: everything else is attested. A
    # digest that ignored the model, the environment, or ADP's trajectory digest
    # would be stable for the wrong reason.
    baseline = a_manifest().digest

    assert a_manifest(task_id="tb2/other").digest != baseline
    assert a_manifest(context_fidelity=0.42).digest != baseline
    assert a_manifest(steps=(a_step(1),)).digest != baseline
    assert a_manifest(adp=an_adp_binding(trajectory_digest=DIGEST_E[:-1] + "f")).digest != baseline


# --- Task 0.2 done-condition --------------------------------------------------


def test_manifest_cannot_be_constructed_without_a_completeness_level() -> None:
    with pytest.raises(ValidationError, match="state_completeness"):
        a_manifest(state_completeness=None)

    fields = json.loads(a_manifest().model_dump_json())
    del fields["state_completeness"]
    with pytest.raises(ValidationError, match="state_completeness"):
        RunManifest.model_validate(fields)


def test_v0_declares_filesystem_capture_only() -> None:
    assert [level.value for level in StateCompleteness] == ["filesystem"]


# --- envelope -----------------------------------------------------------------


def test_envelope_verifies_and_detects_tampering() -> None:
    envelope = ManifestEnvelope.of(a_manifest())
    assert envelope.verifies()

    payload = json.loads(envelope.model_dump_json())
    payload["manifest"]["task_id"] = "tb2/something-easier"
    assert not ManifestEnvelope.model_validate(payload).verifies()


def test_envelope_survives_a_change_of_run_id() -> None:
    # Re-filing a published manifest under a different run id must not invalidate
    # the digest that was published with it.
    envelope = ManifestEnvelope.of(a_manifest())
    payload = json.loads(envelope.model_dump_json())
    payload["manifest"]["run_id"] = "re-filed"

    assert ManifestEnvelope.model_validate(payload).verifies()


# --- invariants ---------------------------------------------------------------


def test_steps_must_be_contiguous_from_one() -> None:
    with pytest.raises(ValidationError, match="contiguous"):
        a_manifest(steps=(a_step(1), a_step(3)))


def test_fork_at_step_must_say_where_it_forked() -> None:
    with pytest.raises(ValidationError, match="forked_from_step"):
        a_manifest(mode=ReplayMode.FORK_AT_STEP)

    forked = a_manifest(mode=ReplayMode.FORK_AT_STEP, forked_from_step=4)
    assert forked.forked_from_step == 4


def test_fork_point_is_meaningless_outside_fork_at_step() -> None:
    with pytest.raises(ValidationError, match="meaningless"):
        a_manifest(mode=ReplayMode.FORK_AT_ZERO, forked_from_step=4)


def test_an_error_verdict_records_which_check_failed() -> None:
    with pytest.raises(ValidationError, match="which check failed"):
        VerdictRecord(name="tb2-tests", verdict=Verdict.ERROR)

    downgraded = VerdictRecord(
        name="tb2-tests", verdict=Verdict.ERROR, downgraded_because=("emitters_ok",)
    )
    assert downgraded.downgraded_because == ("emitters_ok",)


def test_timestamps_must_be_timezone_aware() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        a_manifest(recorded_at=datetime(2026, 8, 5, 12, 0))


def test_timestamps_are_normalized_to_utc_before_digesting() -> None:
    elsewhere = datetime(2026, 8, 5, 5, 0, tzinfo=timezone(timedelta(hours=-7)))
    here = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)

    assert a_manifest(recorded_at=elsewhere).digest == a_manifest(recorded_at=here).digest


def test_unknown_fields_are_rejected() -> None:
    fields = json.loads(a_manifest().model_dump_json())
    fields["state_compleatness"] = "filesystem"
    with pytest.raises(ValidationError):
        RunManifest.model_validate(fields)


def test_manifests_are_frozen() -> None:
    with pytest.raises(ValidationError):
        a_manifest().task_id = "changed"  # type: ignore[misc]


def _shuffle_keys(value: Any, rng: random.Random) -> Any:
    if isinstance(value, dict):
        items = [(k, _shuffle_keys(v, rng)) for k, v in value.items()]
        rng.shuffle(items)
        return dict(items)
    if isinstance(value, list):
        return [_shuffle_keys(v, rng) for v in value]
    return value
