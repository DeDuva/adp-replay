"""`adp-replay manifest` — verifying a published manifest from the file alone."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from adp_replay.cli import main
from adp_replay.manifest import ManifestEnvelope
from tests.factories import a_manifest


def _write(tmp_path: Path, payload: object, name: str = "manifest.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_digest_reads_a_bare_manifest(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    manifest = a_manifest()
    path = _write(tmp_path, json.loads(manifest.model_dump_json()))

    assert main(["manifest", "digest", str(path)]) == 0
    assert capsys.readouterr().out.strip() == manifest.digest


def test_digest_reads_an_envelope(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    manifest = a_manifest()
    path = _write(tmp_path, json.loads(ManifestEnvelope.of(manifest).model_dump_json()))

    assert main(["manifest", "digest", str(path)]) == 0
    assert capsys.readouterr().out.strip() == manifest.digest


def test_verify_accepts_an_intact_envelope(tmp_path: Path) -> None:
    path = _write(tmp_path, json.loads(ManifestEnvelope.of(a_manifest()).model_dump_json()))
    assert main(["manifest", "verify", str(path)]) == 0


def test_verify_rejects_a_tampered_envelope(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = json.loads(ManifestEnvelope.of(a_manifest()).model_dump_json())
    payload["manifest"]["context_fidelity"] = 0.99
    path = _write(tmp_path, payload)

    assert main(["manifest", "verify", str(path)]) == 1
    # Both digests are printed so the failure says which side moved.
    assert "recomputed:" in capsys.readouterr().err


def test_a_malformed_manifest_is_an_error_not_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path, {"nope": True})
    assert main(["manifest", "digest", str(path)]) == 2
    assert "validation error" in capsys.readouterr().err.lower()


def test_a_missing_file_is_an_error(tmp_path: Path) -> None:
    assert main(["manifest", "digest", str(tmp_path / "absent.json")]) == 2
