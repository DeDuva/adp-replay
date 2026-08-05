"""Manifest models (Task 0.1) and state-completeness levels (Task 0.2)."""

from __future__ import annotations

from enum import Enum
from typing import Any


class StateCompleteness(str, Enum):
    """What a snapshot actually captured.

    v0 supports FILESYSTEM only. Processes, sockets, and kernel state are out of
    scope and must be declared as such rather than left unsaid — a reader of a
    published artifact has no other way to know what the replay did not restore.
    """

    FILESYSTEM = "filesystem"


def manifest_digest(manifest: Any) -> str:
    """Digest a manifest over its canonical form, excluding ``run_id``.

    Excluding ``run_id`` is what makes the digest self-certifying: the same
    recorded run verifies identically no matter where it was stored or what
    identifier the store assigned it.

    Task 0.1.
    """
    raise NotImplementedError("Task 0.1 — manifest specification")
