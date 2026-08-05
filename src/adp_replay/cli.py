"""Command-line entry point."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from adp_replay import __version__


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

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    # Every subcommand is a stub until its task lands. Exiting non-zero keeps a
    # scaffold from being mistaken for a working tool by a script that only
    # checks the exit code.
    parser.exit(2, f"'{args.command}' is not implemented yet — see docs/execution-plan.md\n")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
