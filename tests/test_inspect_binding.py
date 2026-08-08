"""The Inspect binding, against a real `inspect-ai` (Task 1.4).

`RecordingSolver` depends on Inspect's *shape* rather than its imports, so that
analysing an already-recorded experiment never requires the harness stack. That
is the right design, and it has one cost: nothing in it fails if the assumed
shape is wrong. Until 2026-08-08 nothing checked, because `inspect-ai` was
believed to be uninstallable here — it is not, and these tests are what that
belief was standing in the way of.

What is checked is exactly the part the protocol cannot check for itself:

* that Inspect's own `Solver` protocol accepts a `RecordingSolver` — asserted
  through `isinstance`, which works because Inspect marks it `@runtime_checkable`,
  so this is Inspect's judgement rather than this repo's reading of the docs;
* that the wrapper round-trips a real `TaskState` unharmed;
* that `_wrap_generate` passes Inspect's `Generate` call shape through untouched,
  including the `tool_calls` argument a hand-written passthrough would drop.

The recording behaviour itself is not re-tested here. It lives in `Recorder`,
is covered in `test_recorder.py`, and is exercised against a live ADP by the
contract suite. Duplicating it would test the wrapper's mock twice.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from adp_replay.recording.inspect_solver import RecordingSolver

inspect_ai = pytest.importorskip(
    "inspect_ai",
    reason="the harness extra is not installed: pip install -e '.[harness]'",
)

from inspect_ai.model import ChatMessageUser, ModelOutput  # noqa: E402
from inspect_ai.solver import Generate, Solver, TaskState  # noqa: E402


class SpyRecorder:
    """Records what it was asked to record. Not a Recorder — see the module docstring."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def record(self, kind: str, **fields: Any) -> int:
        self.calls.append({"kind": kind, **fields})
        return len(self.calls)


def a_task_state() -> TaskState:
    return TaskState(
        model="mockllm/model",
        sample_id="sample-1",
        epoch=1,
        input=[ChatMessageUser(content="do the thing")],
        messages=[ChatMessageUser(content="do the thing")],
        output=ModelOutput(),
    )


def test_inspects_own_protocol_accepts_the_wrapper() -> None:
    """Inspect's judgement, not ours: `Solver` is @runtime_checkable."""

    async def inner(state: TaskState, generate: Generate) -> TaskState:
        return state

    wrapped = RecordingSolver(inner, SpyRecorder())  # type: ignore[arg-type]
    assert isinstance(wrapped, Solver)


def test_a_real_task_state_round_trips_unharmed() -> None:
    state = a_task_state()

    async def inner(inner_state: TaskState, generate: Generate) -> TaskState:
        return inner_state

    recorder = SpyRecorder()
    wrapped = RecordingSolver(inner, recorder, model="mockllm/model")  # type: ignore[arg-type]

    returned = asyncio.run(wrapped(state, _never_generate))

    assert returned is state
    assert [c["kind"] for c in recorder.calls] == ["custom", "custom"]
    assert [c["type"] for c in recorder.calls] == ["solver_start", "solver_end"]


def test_the_generate_wrapper_preserves_inspects_call_shape() -> None:
    """`Generate` takes `(state, tool_calls=..., **config)`.

    A passthrough that flattened those would silently change how the wrapped
    solver generates — a recording harness altering the run it is recording.
    """
    seen: dict[str, Any] = {}

    async def generate(state: TaskState, tool_calls: str = "loop", **kwargs: Any) -> TaskState:
        seen["tool_calls"] = tool_calls
        seen["kwargs"] = kwargs
        return state

    async def inner(state: TaskState, wrapped_generate: Generate) -> TaskState:
        return await wrapped_generate(state, tool_calls="single", temperature=0.5)

    recorder = SpyRecorder()
    wrapped = RecordingSolver(inner, recorder, model="mockllm/model")  # type: ignore[arg-type]

    asyncio.run(wrapped(a_task_state(), generate))

    assert seen["tool_calls"] == "single"
    assert seen["kwargs"] == {"temperature": 0.5}
    assert [c["kind"] for c in recorder.calls] == ["custom", "model_call", "custom"]


def test_a_failing_solver_records_the_error_and_re_raises() -> None:
    async def inner(state: TaskState, generate: Generate) -> TaskState:
        raise RuntimeError("the agent fell over")

    recorder = SpyRecorder()
    wrapped = RecordingSolver(inner, recorder)  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="fell over"):
        asyncio.run(wrapped(a_task_state(), _never_generate))

    # Recorded as an error and re-raised: swallowing it would leave a
    # trajectory that looks like a run which simply stopped.
    assert recorder.calls[-1]["type"] == "solver_error"
    assert recorder.calls[-1]["status"] == "error"


async def _never_generate(state: TaskState, tool_calls: str = "loop", **kwargs: Any) -> TaskState:
    raise AssertionError("generate should not have been called")
