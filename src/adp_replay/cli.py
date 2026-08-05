"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

import pydantic

from adp_replay import __version__
from adp_replay.manifest import ManifestEnvelope, RunManifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="adp-replay",
        description="Record agent trajectories and replay them under substituted models.",
    )
    parser.add_argument("--version", action="version", version=f"adp-replay {__version__}")

    sub = parser.add_subparsers(dest="command")
    sub.add_parser("record", help="Record a trajectory (Task 1.4)")
    sub.add_parser("replay", help="Replay under a substituted model (Tasks 2.1, 2.2)")
    sub.add_parser("report", help="Render reports from recorded runs (Task 3.2)")

    manifest = sub.add_parser("manifest", help="Inspect and verify run manifests (Task 0.1)")
    manifest_sub = manifest.add_subparsers(dest="manifest_command", required=True)

    digest = manifest_sub.add_parser("digest", help="Print a manifest's self-certifying digest")
    digest.add_argument("path", type=Path, help="A manifest or a manifest envelope, as JSON")

    verify = manifest_sub.add_parser("verify", help="Recompute an envelope's digest and compare")
    verify.add_argument("path", type=Path, help="A manifest envelope, as JSON")

    return parser


def _load(path: Path) -> RunManifest:
    """Read a manifest from either a bare manifest file or an envelope."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "manifest" in payload:
        return ManifestEnvelope.model_validate(payload).manifest
    return RunManifest.model_validate(payload)


def _manifest_digest(path: Path) -> int:
    print(_load(path).digest)
    return 0


def _manifest_verify(path: Path) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    envelope = ManifestEnvelope.model_validate(payload)
    if envelope.verifies():
        print(f"ok {envelope.manifest_digest}")
        return 0
    # Print both, because the useful question after a failure is which of the
    # two moved — an edited manifest and a copied-in digest look identical from
    # a bare "mismatch".
    print(
        f"MISMATCH\n  recorded:   {envelope.manifest_digest}\n"
        f"  recomputed: {envelope.manifest.digest}",
        file=sys.stderr,
    )
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "manifest":
        handler = {"digest": _manifest_digest, "verify": _manifest_verify}[args.manifest_command]
        try:
            return handler(args.path)
        except (OSError, json.JSONDecodeError, pydantic.ValidationError) as exc:
            print(f"{args.path}: {exc}", file=sys.stderr)
            return 2

    # Every remaining subcommand is a stub until its task lands. Exiting
    # non-zero keeps a scaffold from being mistaken for a working tool by a
    # script that only checks the exit code.
    parser.exit(2, f"'{args.command}' is not implemented yet — see docs/execution-plan.md\n")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
