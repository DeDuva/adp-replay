"""Builders for fully-populated test objects.

A manifest with every optional field left empty would pass most of these tests
for the wrong reason — a digest is only interesting once there is something under
it — so the default here is deliberately full rather than minimal.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from adp_replay.manifest import (
    AdpBinding,
    EnvironmentSpec,
    ModelSpec,
    ReplayMode,
    RunManifest,
    StateCompleteness,
    StepKind,
    StepRecord,
    StepStatus,
    ToolSpec,
    VerdictRecord,
)
from adp_replay.verdict import Verdict

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64
DIGEST_D = "sha256:" + "d" * 64
DIGEST_E = "sha256:" + "e" * 64
GIT_SHA = "0" * 40


def a_step(seq: int) -> StepRecord:
    return StepRecord(
        producer_seq=seq,
        kind=StepKind.TOOL_CALL,
        client_event_id=f"evt-{seq}",
        payload_digest=DIGEST_A,
        status=StepStatus.SUCCESS,
        duration_ms=12,
        pre_state_digest=DIGEST_B,
        post_state_digest=DIGEST_C,
        occurred_at=datetime(2026, 8, 5, 12, 0, seq, tzinfo=UTC),
    )


def an_adp_binding(**overrides: Any) -> AdpBinding:
    fields: dict[str, Any] = {
        "base_url": "https://adp.example",
        "owner": "acme",
        "repo": "widgets",
        "run_id": "adp-run-9",
        "session_ids": ("sess-1",),
        "trajectory_digest": DIGEST_E,
        "final_git_sha": GIT_SHA,
    }
    fields.update(overrides)
    return AdpBinding(**fields)


def a_manifest(**overrides: Any) -> RunManifest:
    fields: dict[str, Any] = {
        "run_id": "local-run-1",
        "task_id": "tb2/fix-the-thing",
        "recorded_at": datetime(2026, 8, 5, 12, 0, tzinfo=UTC),
        "mode": ReplayMode.RECORDING,
        "state_completeness": StateCompleteness.FILESYSTEM,
        "environment": EnvironmentSpec(
            image="ghcr.io/example/tb2",
            image_digest=DIGEST_A,
            harness="inspect-ai",
            harness_version="0.3.0",
            attributes={"locale": "C.UTF-8"},
        ),
        "model": ModelSpec(
            provider="anthropic",
            model="claude-opus-5",
            parameters={"temperature": 0.0, "max_tokens": 4096},
        ),
        "tools": (ToolSpec(name="bash", definition_digest=DIGEST_B),),
        "steps": (a_step(1), a_step(2)),
        "verdicts": (
            VerdictRecord(
                name="tb2-tests",
                verdict=Verdict.PASS,
                score=1.0,
                scorer_spec_digest=DIGEST_D,
                separately_authorized=True,
            ),
        ),
        "adp": an_adp_binding(),
        "context_fidelity": 0.91,
    }
    fields.update(overrides)
    return RunManifest(**fields)
