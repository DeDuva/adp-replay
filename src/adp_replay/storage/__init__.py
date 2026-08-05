"""Content-addressed storage for state snapshots.

Task 1.1 — CAStore protocol and LocalCAStore.
Task 1.2 — filesystem-delta capture.
"""

from adp_replay.storage.castore import CAStore, LocalCAStore

__all__ = ["CAStore", "LocalCAStore"]
