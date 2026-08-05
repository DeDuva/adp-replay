"""Content-addressed store (Task 1.1).

Snapshot bytes stay local. They are attested to ADP by digest through a session
checkpoint, whose response is a signed DSSE envelope binding the commit to a
SHA-256 digest of the checkpoint state. That gives attested provenance without
pushing multi-megabyte tarballs through a JSON API.

A remote CAS backend is post-MVP.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class CAStore(Protocol):
    """A store addressed by the SHA-256 of its contents."""

    def put(self, data: bytes) -> str:
        """Store ``data`` and return its digest."""
        ...

    def get(self, digest: str) -> bytes:
        """Return the bytes previously stored under ``digest``."""
        ...

    def has(self, digest: str) -> bool:
        """Whether ``digest`` is present, without reading it back."""
        ...


class LocalCAStore:
    """The MVP backend: a directory of digest-named files."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def put(self, data: bytes) -> str:
        raise NotImplementedError("Task 1.1 — content-addressed store")

    def get(self, digest: str) -> bytes:
        raise NotImplementedError("Task 1.1 — content-addressed store")

    def has(self, digest: str) -> bool:
        raise NotImplementedError("Task 1.1 — content-addressed store")
