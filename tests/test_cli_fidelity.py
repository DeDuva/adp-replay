"""`adp-replay fidelity` — the gate, as something CI can fail on."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from adp_replay.cli import main
from adp_replay.context.g0 import run_probe


def test_a_failing_gate_exits_non_zero(capsys: pytest.CaptureFixture[str]) -> None:
    # A gate that exits 0 when it fails is not a gate. This asserts the wiring,
    # whichever way the current reading happens to go.
    expected = 0 if run_probe().passed else 1
    assert main(["fidelity"]) == expected


def test_the_failing_cells_are_named_on_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    report = run_probe()
    main(["fidelity"])
    err = capsys.readouterr().err

    for cell in report.failing:
        assert cell.pair in err
        assert cell.capability.value in err


def test_json_output_is_machine_readable(capsys: pytest.CaptureFixture[str]) -> None:
    main(["fidelity", "--format", "json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["gate"] == "G0"
    assert len(payload["cells"]) == 12


def test_the_report_can_be_written_to_a_file(tmp_path: Path) -> None:
    out = tmp_path / "g0.md"
    main(["fidelity", "--out", str(out)])
    assert "Gate G0" in out.read_text(encoding="utf-8")


def test_narrowing_below_the_floor_is_refused_with_an_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["fidelity", "--providers", "anthropic"]) == 2
    assert "floor" in capsys.readouterr().err
