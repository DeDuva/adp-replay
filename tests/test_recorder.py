"""The recorder and its spool (Task 1.4).

The done-condition is blunt: kill the recorder mid-run, start it again, and the
chain ADP holds is complete and gap-free. `test_a_killed_recorder_resumes_a_gap_free_chain`
is that test against a fake ADP that behaves like the real one; the contract
suite runs the same shape against a live server, with a real SIGKILL.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest

from adp_replay.adp.client import AdpError, AppendReceipt, AppendRejected
from adp_replay.recording import Recorder, RecorderStopped, Spool, SpoolCorrupt


class FakeAdp:
    """An ADP that enforces the contiguity rule the real one enforces."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.seen_ids: set[str] = set()
        self.lock = threading.Lock()
        self.fail_next = 0
        self.drop_next = 0
        self.closed = False

    @property
    def next_expected(self) -> int:
        return len(self.events) + 1

    def append_events(
        self,
        owner: str,
        repo: str,
        session_id: str,
        events: list[dict[str, Any]],
        *,
        producer_id: str | None = None,
    ) -> AppendReceipt:
        with self.lock:
            if self.closed:
                raise AppendRejected("session closed", status=409, body={})

            if self.fail_next > 0:
                self.fail_next -= 1
                raise AdpError("boom", status=500, body=None)

            if self.drop_next > 0:
                # Committed, but the caller never learns: a response lost in
                # flight. The resend that follows is legitimate.
                self.drop_next -= 1
                self._commit(events)
                raise AdpError("connection reset", status=502, body=None)

            first = int(events[0]["producer_seq"])
            if first != self.next_expected:
                raise AppendRejected(
                    "not contiguous",
                    status=409,
                    body={"expected_next_seq": self.next_expected},
                )
            return self._commit(events)

    def _commit(self, events: list[dict[str, Any]]) -> AppendReceipt:
        duplicates: list[str] = []
        appended = 0
        for event in events:
            identifier = str(event["client_event_id"])
            if identifier in self.seen_ids:
                duplicates.append(identifier)
                continue
            self.seen_ids.add(identifier)
            self.events.append(event)
            appended += 1
        return AppendReceipt(
            chain_head="sha256:fake",
            accepted_through=len(self.events),
            appended=appended,
            duplicates=tuple(duplicates),
            count=len(self.events),
        )

    @property
    def sequence(self) -> list[int]:
        return [int(event["producer_seq"]) for event in self.events]


def recorder_for(adp: Any, spool: Spool, **kwargs: Any) -> Recorder:
    return Recorder(adp, "acme", "widgets", "s-1", spool, poll_interval=0.01, **kwargs)


# --- the spool ----------------------------------------------------------------


def test_sequence_numbers_are_contiguous_from_one(tmp_path: Path) -> None:
    spool = Spool(tmp_path)
    assert [spool.append({"kind": "message"}) for _ in range(5)] == [1, 2, 3, 4, 5]


def test_client_event_ids_are_derived_not_random(tmp_path: Path) -> None:
    # A replayed event has to carry the id it had the first time, or ADP appends
    # it twice and the resume protocol produces the corruption it exists to
    # prevent.
    spool = Spool(tmp_path)
    spool.append({"kind": "message"})
    first = spool.pending()[0]["client_event_id"]

    reopened = Spool(tmp_path)
    assert reopened.pending()[0]["client_event_id"] == first
    assert first.endswith(":1")


def test_a_reopened_spool_continues_the_sequence(tmp_path: Path) -> None:
    spool = Spool(tmp_path)
    for _ in range(3):
        spool.append({"kind": "message"})

    assert Spool(tmp_path).next_seq == 4


def test_the_sequence_continues_past_a_trim(tmp_path: Path) -> None:
    # The count is ADP's, not the file's. A spool trimmed to empty still knows
    # where it is.
    spool = Spool(tmp_path)
    for _ in range(3):
        spool.append({"kind": "message"})
    spool.trim(3)

    reopened = Spool(tmp_path)
    assert reopened.depth == 0
    assert reopened.append({"kind": "message"}) == 4


def test_trimming_drops_only_what_was_acknowledged(tmp_path: Path) -> None:
    spool = Spool(tmp_path)
    for _ in range(5):
        spool.append({"kind": "message"})

    spool.trim(2)
    assert [event["producer_seq"] for event in spool.pending()] == [3, 4, 5]


def test_a_backwards_trim_is_refused(tmp_path: Path) -> None:
    # ADP acknowledging less than it already had means it lost events. No retry
    # fixes that, so it is reported rather than looped on.
    spool = Spool(tmp_path)
    for _ in range(3):
        spool.append({"kind": "message"})
    spool.trim(3)

    with pytest.raises(SpoolCorrupt, match="behind"):
        spool.trim(1)


def test_resuming_under_a_different_producer_is_refused(tmp_path: Path) -> None:
    # A restart that invented a new producer id would look to ADP like a second
    # emitter on the same session, and its completeness count would restart.
    Spool(tmp_path, producer_id="recorder-a")
    with pytest.raises(SpoolCorrupt, match="belongs to producer"):
        Spool(tmp_path, producer_id="recorder-b")


def test_a_half_written_final_line_is_tolerated(tmp_path: Path) -> None:
    # What a kill mid-append looks like on disk.
    spool = Spool(tmp_path)
    for _ in range(3):
        spool.append({"kind": "message"})

    events = tmp_path / "events.jsonl"
    events.write_text(events.read_text() + '{"kind": "mess')

    reopened = Spool(tmp_path)
    assert [event["producer_seq"] for event in reopened.pending()] == [1, 2, 3]


# --- recording ----------------------------------------------------------------


def test_recording_does_not_block_on_the_network(tmp_path: Path) -> None:
    # The G1 budget is 10% inclusive of ADP round-trips. record() returns
    # without touching the network at all; the thread does that.
    class NeverAnswers:
        def append_events(self, *args: Any, **kwargs: Any) -> AppendReceipt:
            raise AssertionError("record() must not call ADP")

    spool = Spool(tmp_path)
    recorder = recorder_for(NeverAnswers(), spool)
    assert recorder.record("message", payload={}) == 1
    assert spool.depth == 1


def test_events_reach_adp_in_order(tmp_path: Path) -> None:
    adp = FakeAdp()
    with recorder_for(adp, Spool(tmp_path)) as recorder:
        for index in range(25):
            recorder.record("message", payload={"i": index})
        assert recorder.flush(timeout=10)

    assert adp.sequence == list(range(1, 26))


def test_the_spool_is_trimmed_at_what_adp_acknowledged(tmp_path: Path) -> None:
    adp = FakeAdp()
    spool = Spool(tmp_path)
    with recorder_for(adp, spool) as recorder:
        for _ in range(10):
            recorder.record("message", payload={})
        recorder.flush(timeout=10)

    assert spool.depth == 0
    assert spool.accepted_through == 10


def test_closing_flushes_what_is_left(tmp_path: Path) -> None:
    # The last few events of a run are the ones that say how it ended.
    adp = FakeAdp()
    recorder = recorder_for(adp, Spool(tmp_path))
    recorder.start()
    for _ in range(5):
        recorder.record("message", payload={})
    recorder.close(timeout=10)

    assert adp.sequence == [1, 2, 3, 4, 5]


# --- the done-condition -------------------------------------------------------


def test_a_killed_recorder_resumes_a_gap_free_chain(tmp_path: Path) -> None:
    """Task 1.4's done-condition.

    A kill is modelled as what it actually is: the process stops without
    flushing, and the spool on disk is all that survives. A second recorder
    opens the same spool and finishes the job.
    """
    adp = FakeAdp()

    first = recorder_for(adp, Spool(tmp_path))
    first.start()
    for index in range(30):
        first.record("message", payload={"i": index})
    first.flush(timeout=10)

    # Killed: more events land, and nothing gets to send them.
    dying = Spool(tmp_path)
    for index in range(30, 50):
        dying.append({"kind": "message", "payload": {"i": index}})
    first._stopping.set()

    resumed = recorder_for(adp, Spool(tmp_path))
    with resumed:
        assert resumed.flush(timeout=10)

    assert adp.sequence == list(range(1, 51)), "the chain ADP holds must be gap-free"
    assert len(adp.events) == len(set(adp.seen_ids)), "and must contain no event twice"


def test_a_resume_replays_from_where_adp_says_it_is(tmp_path: Path) -> None:
    # ADP is ahead of this client's belief: it already holds events this spool
    # still thinks are pending. The 409 names the resume point and the spool
    # moves to it rather than retrying the same rejected batch forever.
    adp = FakeAdp()
    spool = Spool(tmp_path)
    for index in range(5):
        spool.append({"kind": "message", "payload": {"i": index}})

    # ADP already has 1..3 under the same ids, so a send starting at 1 is fine,
    # but a spool that believed nothing was accepted would loop. Commit them
    # directly to create the divergence.
    adp._commit(spool.pending()[:3])

    with recorder_for(adp, spool) as recorder:
        assert recorder.flush(timeout=10)
        assert recorder.stats.resumes >= 1

    assert adp.sequence == [1, 2, 3, 4, 5]


def test_a_closed_session_stops_the_recorder_rather_than_looping(tmp_path: Path) -> None:
    adp = FakeAdp()
    adp.closed = True

    recorder = recorder_for(adp, Spool(tmp_path))
    recorder.start()
    recorder.record("message", payload={})

    with pytest.raises(RecorderStopped, match="closed"):
        recorder.flush(timeout=10)


def test_adp_asking_for_events_the_spool_dropped_is_fatal(tmp_path: Path) -> None:
    # ADP asking to be replayed from before what it already acknowledged means
    # it lost events. Retrying cannot manufacture them.
    class Regressing:
        def append_events(self, *args: Any, **kwargs: Any) -> AppendReceipt:
            raise AppendRejected("gap", status=409, body={"expected_next_seq": 1})

    spool = Spool(tmp_path)
    spool.append({"kind": "message"})
    spool.trim(1)
    spool.append({"kind": "message"})

    recorder = recorder_for(Regressing(), spool)
    recorder.start()
    with pytest.raises(RecorderStopped, match="not recoverable"):
        recorder.flush(timeout=10)


# --- duplicates ---------------------------------------------------------------


def test_a_lost_response_does_not_duplicate_the_chain(tmp_path: Path) -> None:
    """ADP commits the batch and the response never arrives.

    Worth being precise about which mechanism saves this, because it is not the
    one the plan's "treat duplicates as a bug signal" rule implies. The resend
    starts at a sequence ADP is already past, so the *contiguity* check rejects
    it with a resume point and the spool skips forward. Deduplication by
    `client_event_id` never gets a turn.

    That ordering is the good one: contiguity is checked against a counter ADP
    keeps, so it catches the case whether or not the ids happen to match. The id
    is the second line of defence, not the first.
    """
    adp = FakeAdp()
    adp.drop_next = 1

    with recorder_for(adp, Spool(tmp_path)) as recorder:
        for index in range(4):
            recorder.record("message", payload={"i": index})
        assert recorder.flush(timeout=10)

    assert adp.sequence == [1, 2, 3, 4]
    assert len(adp.events) == len(set(adp.seen_ids))
    assert recorder.stats.resumes == 1
    # Not counted as the bug signal either way: this client could not have known
    # the batch landed.
    assert recorder.stats.unexpected_duplicates == 0


def test_an_unexplained_duplicate_is_a_bug_signal(tmp_path: Path) -> None:
    # The plan's rule: a non-zero duplicates count with no ambiguous send behind
    # it means the recorder sent something twice believing it had not.
    seen: list[tuple[str, ...]] = []

    class AlwaysDuplicates:
        def append_events(
            self, owner: str, repo: str, session: str, events: list[dict[str, Any]], **kwargs: Any
        ) -> AppendReceipt:
            return AppendReceipt(
                chain_head="sha256:x",
                accepted_through=len(events),
                appended=0,
                duplicates=tuple(str(e["client_event_id"]) for e in events),
                count=len(events),
            )

    spool = Spool(tmp_path)
    recorder = recorder_for(AlwaysDuplicates(), spool, on_unexpected_duplicates=seen.append)
    with recorder:
        recorder.record("message", payload={})
        recorder.flush(timeout=10)

    assert recorder.stats.unexpected_duplicates == 1
    assert recorder.stats.duplicates_after_retry == 0
    assert seen and seen[0][0].endswith(":1")


def test_a_transient_failure_is_retried(tmp_path: Path) -> None:
    adp = FakeAdp()
    adp.fail_next = 2

    with recorder_for(adp, Spool(tmp_path)) as recorder:
        for index in range(3):
            recorder.record("message", payload={"i": index})
        assert recorder.flush(timeout=10)

    assert adp.sequence == [1, 2, 3]
    assert recorder.stats.retries == 2


# --- guards -------------------------------------------------------------------


def test_a_non_contiguous_batch_is_caught_locally(tmp_path: Path) -> None:
    from adp_replay.recording.recorder import _assert_contiguous

    with pytest.raises(RecorderStopped, match="not contiguous"):
        _assert_contiguous([{"producer_seq": 1}, {"producer_seq": 3}])


def test_an_oversized_batch_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="batch_size"):
        recorder_for(FakeAdp(), Spool(tmp_path), batch_size=5000)


def test_recording_after_a_fatal_failure_raises(tmp_path: Path) -> None:
    # Spooling into a void would let a run continue believing it was recorded.
    adp = FakeAdp()
    adp.closed = True

    recorder = recorder_for(adp, Spool(tmp_path))
    recorder.start()
    recorder.record("message", payload={})
    with pytest.raises(RecorderStopped):
        recorder.flush(timeout=10)

    with pytest.raises(RecorderStopped):
        recorder.record("message", payload={})


def test_batches_respect_the_configured_size(tmp_path: Path) -> None:
    adp = FakeAdp()
    with recorder_for(adp, Spool(tmp_path), batch_size=5) as recorder:
        for _ in range(20):
            recorder.record("message", payload={})
        assert recorder.flush(timeout=10)

    assert adp.sequence == list(range(1, 21))
    assert recorder.stats.batches >= 4
