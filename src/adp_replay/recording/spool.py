"""Local spool backing the recorder (Task 1.4).

The recorder never blocks a tool call on an ADP write: steps are spooled locally
and flushed asynchronously in batches. That is a correctness property as much as
a performance one — the G1 budget is 10% wall-clock overhead inclusive of ADP
round-trips, and a synchronous append puts network latency on the agent's
critical path.

Resume protocol, which is what makes a killed recorder recoverable:

* append batches carrying ``producer_seq`` and ``client_event_id``
* on a 409 contiguity rejection, replay from the returned ``expected_next_seq``
* trim the spool at ``accepted_through``
* treat a non-zero ``duplicates`` count as a bug signal, not as normal traffic
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class Spool:
    """Durable local queue of events awaiting acknowledgement from ADP."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def append(self, event: dict[str, Any]) -> int:
        """Record an event locally and return its ``producer_seq``."""
        raise NotImplementedError("Task 1.4 — recorder")

    def pending(self, since_seq: int) -> list[dict[str, Any]]:
        """Events at or above ``since_seq``, for replay after a rejection."""
        raise NotImplementedError("Task 1.4 — recorder")

    def trim(self, accepted_through: int) -> None:
        """Drop events ADP has acknowledged."""
        raise NotImplementedError("Task 1.4 — recorder")
