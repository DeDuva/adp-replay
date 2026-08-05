"""Scaffold tests: the package imports, the CLI runs, and the invariants hold.

These are deliberately thin. They exist so that `make check` is meaningful on an
empty repo and so a broken import is caught before a task author hits it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from adp_replay import __version__
from adp_replay.cli import build_parser, main
from adp_replay.manifest import StateCompleteness
from adp_replay.replay import CONTINUATION_BANNER
from adp_replay.storage import CAStore, LocalCAStore
from adp_replay.verdict import Verdict


def test_version_is_exposed() -> None:
    assert __version__


def test_cli_with_no_command_prints_help() -> None:
    assert main([]) == 0


def test_cli_rejects_unimplemented_subcommands() -> None:
    # A scaffold that exits 0 reads as success to any script that only checks
    # the exit code.
    with pytest.raises(SystemExit) as excinfo:
        main(["record"])
    assert excinfo.value.code == 2


def test_parser_builds() -> None:
    assert build_parser().prog == "adp-replay"


def test_local_castore_satisfies_the_protocol() -> None:
    # The annotation is the assertion: mypy fails here if LocalCAStore drifts
    # from CAStore.
    store: CAStore = LocalCAStore(root=Path("."))
    assert store is not None


def test_state_completeness_is_filesystem_only_in_v0() -> None:
    # v0 captures the filesystem and nothing else. If a level is added here
    # without the manifest and the report learning to declare it, a published
    # artifact starts overstating what the replay restored.
    assert [level.value for level in StateCompleteness] == ["filesystem"]


def test_continuation_banner_states_it_is_not_a_comparison() -> None:
    assert "Not a pinned-harness model comparison." in CONTINUATION_BANNER


def test_error_is_a_distinct_verdict() -> None:
    # Evidence gating depends on ERROR being neither a pass nor a fail.
    assert Verdict.ERROR not in (Verdict.PASS, Verdict.FAIL)
