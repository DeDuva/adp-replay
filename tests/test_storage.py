"""Content-addressed store (Task 1.1) and filesystem capture (Task 1.2).

The done-conditions:

* a snapshot digest recorded in a checkpoint verifies against the returned
  envelope — the binding half is here, the live half is in `tests/contract/`;
* capturing the same tree twice on two machines yields identical digests.

"Two machines" cannot be literal in a unit test, so what is varied here is
everything that actually differs between two machines: the absolute path of the
tree, the mtimes, the order files were created in, and the modes a umask left
behind. If a digest survives all four it is a function of content.
"""

from __future__ import annotations

import base64
import gzip
import json
import os
import stat
import time
from pathlib import Path
from typing import Any

import pytest

from adp_replay.storage import (
    AttestationError,
    Capture,
    CaptureOptions,
    CorruptObject,
    LocalCAStore,
    capture_tree,
    digest_of,
    restore_tree,
    snapshot_state,
    state_digest,
    tree_digest,
    verify_checkpoint,
)
from adp_replay.storage.attest import CHECKPOINT_PREDICATE_TYPE, state_bytes

SHA = "348be7838e230e4366420b4c685cf6059764a363"


def build_tree(root: Path, *, mtime: float, reverse: bool = False, mode: int = 0o644) -> Path:
    """The same logical tree, made in a way a different machine might make it."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "src").mkdir(exist_ok=True)
    (root / "empty").mkdir(exist_ok=True)

    files = [
        ("src/a.py", "print(1)\n"),
        ("src/b.py", "print(2)\n"),
        ("README.md", "# hi\n"),
    ]
    for name, body in reversed(files) if reverse else files:
        path = root / name
        path.write_text(body)
        os.chmod(path, mode)

    script = root / "run.sh"
    script.write_text("#!/bin/sh\necho go\n")
    os.chmod(script, 0o755)

    link = root / "link"
    if not link.exists():
        link.symlink_to("src/a.py")

    for path in sorted(root.rglob("*"), reverse=True):
        os.utime(path, (mtime, mtime), follow_symlinks=False)
    os.utime(root, (mtime, mtime))
    return root


# --- Task 1.2: the same tree digests the same anywhere ------------------------


def test_the_same_tree_digests_identically_under_different_conditions(
    tmp_path: Path,
) -> None:
    # Different root path, different mtimes, different creation order, different
    # umask. Everything that varies between two machines, varied.
    first = build_tree(tmp_path / "machine-a" / "work", mtime=1_000_000_000, mode=0o644)
    second = build_tree(
        tmp_path / "elsewhere" / "deeper" / "checkout",
        mtime=time.time(),
        reverse=True,
        mode=0o664,
    )

    assert tree_digest(first) == tree_digest(second)


def test_content_still_changes_the_digest(tmp_path: Path) -> None:
    # The complement: a digest stable for the wrong reason would pass the test
    # above and be worthless.
    original = build_tree(tmp_path / "a", mtime=1_000)
    baseline = tree_digest(original)

    (original / "src" / "a.py").write_text("print(99)\n")
    assert tree_digest(original) != baseline


def test_the_executable_bit_is_content(tmp_path: Path) -> None:
    # Whether a file can be run changes what the agent can do. The rest of the
    # mode does not.
    root = build_tree(tmp_path / "a", mtime=1_000)
    baseline = tree_digest(root)

    os.chmod(root / "run.sh", 0o644)
    assert tree_digest(root) != baseline


def test_a_umask_difference_is_not_content(tmp_path: Path) -> None:
    root = build_tree(tmp_path / "a", mtime=1_000, mode=0o600)
    other = build_tree(tmp_path / "b", mtime=2_000, mode=0o666)
    assert tree_digest(root) == tree_digest(other)


def test_empty_directories_survive(tmp_path: Path) -> None:
    # An empty directory is state: a task can fail because it is missing.
    root = build_tree(tmp_path / "a", mtime=1_000)
    assert "empty" in capture_tree(root).entries

    baseline = tree_digest(root)
    (root / "empty").rmdir()
    assert tree_digest(root) != baseline


def test_symlinks_are_stored_as_links_not_followed(tmp_path: Path) -> None:
    root = build_tree(tmp_path / "a", mtime=1_000)
    escape = root / "escape"
    escape.symlink_to(tmp_path.parent)

    capture = capture_tree(root)
    # The link is recorded; whatever it points at is not pulled in.
    assert "escape" in capture.entries
    assert not any(entry.startswith("escape/") for entry in capture.entries)


def test_git_is_excluded_by_default(tmp_path: Path) -> None:
    # Git objects carry committer timestamps and pack files that differ between
    # machines holding identical history. ADP attests the commit sha instead.
    root = build_tree(tmp_path / "a", mtime=1_000)
    (root / ".git").mkdir()
    (root / ".git" / "HEAD").write_text("ref: refs/heads/main\n")

    assert not any(entry.startswith(".git") for entry in capture_tree(root).entries)


def test_exclusions_match_at_any_depth(tmp_path: Path) -> None:
    root = build_tree(tmp_path / "a", mtime=1_000)
    (root / "src" / "__pycache__").mkdir()
    (root / "src" / "__pycache__" / "a.pyc").write_bytes(b"\x00")

    options = CaptureOptions(exclude=(".git", "__pycache__"))
    assert not any("__pycache__" in e for e in capture_tree(root, options).entries)


def test_a_socket_is_reported_rather_than_silently_dropped(tmp_path: Path) -> None:
    # v0 captures the filesystem and nothing else. A tree containing something
    # outside that has to be visible, or a manifest claiming FILESYSTEM
    # completeness would be overstating what was captured.
    import socket

    root = build_tree(tmp_path / "a", mtime=1_000)
    server = socket.socket(socket.AF_UNIX)
    server.bind(str(root / "sock"))
    try:
        capture = capture_tree(root)
        assert "sock" in capture.skipped
        assert "sock" not in capture.entries
        assert not capture.is_complete_for_filesystem
    finally:
        server.close()


def test_a_plain_tree_reports_itself_complete(tmp_path: Path) -> None:
    assert capture_tree(build_tree(tmp_path / "a", mtime=1_000)).is_complete_for_filesystem


# --- restore ------------------------------------------------------------------


def test_a_restored_tree_recaptures_to_the_same_digest(tmp_path: Path) -> None:
    # The strongest form of the property: capture, restore, capture again.
    root = build_tree(tmp_path / "a", mtime=1_000)
    capture = capture_tree(root)

    destination = tmp_path / "restored"
    restore_tree(capture.data, destination)

    assert capture_tree(destination).digest == capture.digest
    assert (destination / "run.sh").stat().st_mode & stat.S_IXUSR
    assert (destination / "link").is_symlink()


def test_restore_refuses_to_write_outside_its_destination(tmp_path: Path) -> None:
    # A snapshot is untrusted input the moment it comes back off disk.
    import io
    import tarfile

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        info = tarfile.TarInfo(name="../escaped.txt")
        info.size = 3
        archive.addfile(info, io.BytesIO(b"bad"))

    with pytest.raises(tarfile.TarError):
        restore_tree(buffer.getvalue(), tmp_path / "dest")
    assert not (tmp_path / "escaped.txt").exists()


# --- Task 1.1: the store ------------------------------------------------------


def test_put_returns_the_digest_of_the_content(tmp_path: Path) -> None:
    store = LocalCAStore(tmp_path / "cas")
    assert store.put(b"hello") == digest_of(b"hello")


def test_round_trip(tmp_path: Path) -> None:
    store = LocalCAStore(tmp_path / "cas")
    digest = store.put(b"snapshot bytes")
    assert store.has(digest)
    assert store.get(digest) == b"snapshot bytes"


def test_putting_twice_is_idempotent(tmp_path: Path) -> None:
    store = LocalCAStore(tmp_path / "cas")
    assert store.put(b"same") == store.put(b"same")


def test_a_missing_object_raises(tmp_path: Path) -> None:
    store = LocalCAStore(tmp_path / "cas")
    assert not store.has(digest_of(b"absent"))
    with pytest.raises(KeyError):
        store.get(digest_of(b"absent"))


def test_reads_are_verified(tmp_path: Path) -> None:
    # A store that hands back bytes without checking them is a directory with
    # extra steps, and silent snapshot corruption is a replay that diverges for
    # a reason nobody can find.
    store = LocalCAStore(tmp_path / "cas")
    digest = store.put(b"honest")

    path = next((tmp_path / "cas").rglob("*.gz"))
    path.write_bytes(gzip.compress(b"tampered"))

    with pytest.raises(CorruptObject):
        store.get(digest)


def test_the_digest_is_of_the_content_not_the_stored_bytes(tmp_path: Path) -> None:
    # Compression output is not stable across zlib versions. If the digest
    # covered it, "the same tree on two machines" would depend on which zlib
    # each machine shipped.
    store = LocalCAStore(tmp_path / "cas")
    data = b"x" * 4096
    digest = store.put(data)

    stored = next((tmp_path / "cas").rglob("*.gz")).read_bytes()
    assert stored != data, "expected the object to be compressed on disk"
    assert digest == digest_of(data)


def test_a_malformed_digest_is_refused(tmp_path: Path) -> None:
    store = LocalCAStore(tmp_path / "cas")
    for bad in ("nonsense", "sha256:zz", "md5:" + "a" * 32, "sha256:" + "A" * 64):
        with pytest.raises(ValueError):
            store.has(bad)


def test_objects_are_sharded(tmp_path: Path) -> None:
    store = LocalCAStore(tmp_path / "cas")
    digest = store.put(b"content")
    hexdigest = digest.removeprefix("sha256:")

    assert (tmp_path / "cas" / hexdigest[:2] / hexdigest[2:4] / f"{hexdigest}.gz").exists()


def test_a_capture_goes_into_the_store_unchanged(tmp_path: Path) -> None:
    root = build_tree(tmp_path / "a", mtime=1_000)
    capture = capture_tree(root)
    store = LocalCAStore(tmp_path / "cas")

    assert store.put(capture.data) == capture.digest
    assert store.get(capture.digest) == capture.data


# --- Task 1.1: the attestation ------------------------------------------------


def envelope_for(state: Any, *, git_sha: str = SHA, **predicate: Any) -> dict[str, Any]:
    """A checkpoint response shaped the way ADP shapes one."""
    statement = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [{"name": "git+http://adp/x/y", "digest": {"sha1": git_sha}}],
        "predicateType": CHECKPOINT_PREDICATE_TYPE,
        "predicate": {
            "sessionId": "s-1",
            "seq": 1,
            "harness": "adp-replay",
            "stateSha256": state_digest(state),
            "trajectoryHead": "abc",
            "eventCount": 0,
            **predicate,
        },
    }
    payload = base64.b64encode(json.dumps(statement).encode()).decode()
    return {"envelope": {"payloadType": "application/vnd.in-toto+json", "payload": payload}}


def test_a_snapshot_digest_verifies_against_the_envelope(tmp_path: Path) -> None:
    root = build_tree(tmp_path / "a", mtime=1_000)
    capture = capture_tree(root)
    state = snapshot_state(capture.digest, entries=len(capture.entries))

    attestation = verify_checkpoint(envelope_for(state), state=state, git_sha=SHA)

    assert attestation.state_sha256 == state_digest(state)
    assert attestation.git_sha == SHA


def test_a_tampered_snapshot_digest_fails_to_verify(tmp_path: Path) -> None:
    state = snapshot_state("sha256:" + "a" * 64)
    checkpoint = envelope_for(state)

    with pytest.raises(AttestationError, match="attests state"):
        verify_checkpoint(checkpoint, state=snapshot_state("sha256:" + "b" * 64))


def test_an_envelope_for_another_commit_fails_to_verify() -> None:
    state = snapshot_state("sha256:" + "a" * 64)
    with pytest.raises(AttestationError, match="attests commit"):
        verify_checkpoint(envelope_for(state), state=state, git_sha="f" * 40)


def test_a_foreign_predicate_type_is_refused() -> None:
    state = snapshot_state("sha256:" + "a" * 64)
    checkpoint = envelope_for(state)
    statement = json.loads(base64.b64decode(checkpoint["envelope"]["payload"]))
    statement["predicateType"] = "https://example.com/something/v1"
    checkpoint["envelope"]["payload"] = base64.b64encode(json.dumps(statement).encode()).decode()

    with pytest.raises(AttestationError, match=r"not 'https://adp\.dev"):
        verify_checkpoint(checkpoint, state=state)


def test_a_missing_envelope_is_refused() -> None:
    with pytest.raises(AttestationError, match="no envelope"):
        verify_checkpoint({}, state=snapshot_state("sha256:" + "a" * 64))


def test_a_malformed_envelope_is_refused() -> None:
    with pytest.raises(AttestationError, match="base64"):
        verify_checkpoint({"envelope": {"payload": "not base64!"}}, state={})


def test_state_is_serialized_the_way_adp_hashes_it() -> None:
    # Compact separators, no ASCII escaping, key order as written. ADP hashes
    # sha256(JSON.stringify(state)), so any of the three differing makes the
    # attested digest unverifiable.
    assert state_bytes({"b": 1, "a": "é"}) == b'{"b":1,"a":"\xc3\xa9"}'


def test_a_float_in_the_state_is_refused_up_front() -> None:
    # Python and JavaScript do not agree on the decimal form of every double.
    # Caught where the fix is obvious rather than as a digest mismatch later.
    with pytest.raises(AttestationError, match="must not contain floats"):
        state_digest({"snapshot": "sha256:x", "ratio": 0.1})

    with pytest.raises(AttestationError, match="must not contain floats"):
        state_digest({"nested": {"list": [1, 2.5]}})


def test_a_capture_is_a_frozen_record(tmp_path: Path) -> None:
    capture = capture_tree(build_tree(tmp_path / "a", mtime=1_000))
    assert isinstance(capture, Capture)
    with pytest.raises(AttributeError):
        capture.digest = "sha256:" + "0" * 64  # type: ignore[misc]
