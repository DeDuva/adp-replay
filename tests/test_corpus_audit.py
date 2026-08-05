"""Closure auditing (Task 1.3).

The audit's job is to answer one question per task: could running this twice, on
two machines, at two different times, differ for a reason that is not the model?
The tests below are mostly about the *severity policy*, because that is where an
audit either earns attention or becomes noise nobody reads.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from adp_replay.corpus import (
    AUDIT_RATIO,
    CorpusBelowTarget,
    FileRole,
    Hazard,
    Severity,
    audit_task,
    audit_tasks,
    build_corpus,
    classify,
    discover_tasks,
)


def make_task(
    root: Path,
    name: str,
    *,
    dockerfile: str = "FROM python:3.12-slim\n",
    solution: str = "#!/bin/sh\nsed -i s/a/b/ main.py\n",
    test: str = "def test_it():\n    assert True\n",
) -> Path:
    task = root / name
    (task / "tests").mkdir(parents=True)
    (task / "task.yaml").write_text(f"instruction: {name}\n")
    (task / "Dockerfile").write_text(dockerfile)
    (task / "solution.sh").write_text(solution)
    (task / "tests" / "test_outputs.py").write_text(test)
    return task


# --- what counts as which kind of file ----------------------------------------


@pytest.mark.parametrize(
    ("path", "role"),
    [
        ("Dockerfile", FileRole.BUILD),
        ("docker-compose.yaml", FileRole.BUILD),
        ("task.yaml", FileRole.STATEMENT),
        ("tests/test_outputs.py", FileRole.TEST),
        ("run-tests.sh", FileRole.TEST),
        ("solution.sh", FileRole.SOLUTION),
        ("helper.sh", FileRole.RUNTIME),
    ],
)
def test_files_are_classified_by_when_they_run(path: str, role: FileRole) -> None:
    assert classify(Path(path)) is role


def test_an_unrecognized_file_is_treated_as_runtime() -> None:
    # The strictest role. Guessing BUILD for an unknown file would quietly
    # downgrade a blocking finding to advisory.
    assert classify(Path("weird/thing.sh")) is FileRole.RUNTIME


# --- the severity policy ------------------------------------------------------


def test_build_time_network_is_advisory(tmp_path: Path) -> None:
    # The image is pinned by digest, so whatever apt-get fetched is inside the
    # artifact every replay starts from.
    task = make_task(tmp_path, "t", dockerfile="FROM python:3.12\nRUN apt-get install -y jq\n")
    audit = audit_task(task)

    assert audit.passed
    assert any(f.hazard is Hazard.NETWORK for f in audit.advisory)


def test_run_time_network_blocks(tmp_path: Path) -> None:
    task = make_task(
        tmp_path,
        "t",
        test="import requests\ndef test_it():\n    assert requests.get('http://x.example').ok\n",
    )
    audit = audit_task(task)

    assert not audit.passed
    assert "network" in audit.hazards


def test_network_in_a_solution_blocks(tmp_path: Path) -> None:
    task = make_task(tmp_path, "t", solution="#!/bin/sh\ncurl -sO http://example.com/patch\n")
    assert not audit_task(task).passed


def test_a_localhost_url_is_not_network_use(tmp_path: Path) -> None:
    # A task that talks to something it started inside its own container is
    # closed. Flagging it would reject a large and legitimate class of task.
    task = make_task(
        tmp_path, "t", test="def test_it():\n    assert 'http://localhost:8080' is not None\n"
    )
    findings = [f for f in audit_task(task).findings if f.hazard is Hazard.NETWORK]
    assert not findings


def test_a_background_process_blocks(tmp_path: Path) -> None:
    task = make_task(tmp_path, "t", solution="#!/bin/sh\nnohup ./server &\n")
    audit = audit_task(task)

    assert not audit.passed
    assert "background_process" in audit.hazards


def test_a_clock_read_in_a_test_blocks(tmp_path: Path) -> None:
    # A solution that reads the clock produces a different trajectory. A test
    # that reads the clock produces a different verdict for the same
    # trajectory, which is what makes a result uninterpretable.
    task = make_task(
        tmp_path,
        "t",
        test="import time\ndef test_it():\n    assert time.time() > 0\n",
    )
    audit = audit_task(task)

    assert not audit.passed
    assert "clock" in audit.hazards


def test_a_clock_read_in_a_solution_is_advisory(tmp_path: Path) -> None:
    task = make_task(tmp_path, "t", solution="#!/bin/sh\nsleep 2\necho done\n")
    audit = audit_task(task)

    assert audit.passed
    assert any(f.hazard is Hazard.CLOCK and f.severity is Severity.ADVISORY for f in audit.findings)


def test_a_clean_task_passes_with_no_findings(tmp_path: Path) -> None:
    audit = audit_task(make_task(tmp_path, "clean"))
    assert audit.passed
    assert audit.findings == ()


# --- not becoming noise -------------------------------------------------------


def test_commented_out_hazards_are_not_flagged(tmp_path: Path) -> None:
    # Flagging a commented-out curl trains people to ignore the audit, and an
    # ignored audit is worse than none: it makes the corpus look examined.
    task = make_task(tmp_path, "t", solution="#!/bin/sh\n# curl http://example.com\necho hi\n")
    assert audit_task(task).findings == ()


def test_a_finding_carries_enough_to_check_it_by_hand(tmp_path: Path) -> None:
    task = make_task(tmp_path, "t", solution="#!/bin/sh\ncurl http://example.com\n")
    finding = next(f for f in audit_task(task).findings if f.hazard is Hazard.NETWORK)

    assert finding.path == "solution.sh"
    assert finding.line == 2
    assert "curl" in finding.text
    assert finding.pattern
    assert finding.note


# --- the corpus ---------------------------------------------------------------


def test_discovery_needs_both_a_statement_and_a_build(tmp_path: Path) -> None:
    make_task(tmp_path, "real")
    (tmp_path / "fixtures").mkdir()
    (tmp_path / "fixtures" / "task.yaml").write_text("not a task\n")

    found = discover_tasks(tmp_path)
    assert [p.name for p in found] == ["real"]


def test_the_audit_target_is_a_quarter_more_than_the_experiment_needs() -> None:
    audit = audit_tasks([], target_tasks=170)
    assert audit.audit_target == 213
    assert AUDIT_RATIO == 1.25


def test_a_short_corpus_is_refused(tmp_path: Path) -> None:
    # The done-condition, enforced rather than checked by eye.
    make_task(tmp_path, "one")

    with pytest.raises(CorpusBelowTarget, match="experiment needs 170"):
        build_corpus(discover_tasks(tmp_path), target_tasks=170)


def test_a_short_corpus_is_not_written_by_default(tmp_path: Path) -> None:
    make_task(tmp_path, "one")
    out = tmp_path / "tb2_closed_corpus.json"

    with pytest.raises(CorpusBelowTarget):
        build_corpus(discover_tasks(tmp_path), target_tasks=170, out=out)
    assert not out.exists()


def test_a_short_corpus_can_be_inspected_but_says_it_is_short(tmp_path: Path) -> None:
    make_task(tmp_path, "one")
    out = tmp_path / "corpus.json"

    build_corpus(discover_tasks(tmp_path), target_tasks=170, out=out, allow_short=True)

    document = json.loads(out.read_text())
    assert document["meets_target"] is False
    assert document["audited_enough"] is False
    assert document["target_tasks"] == 170


def test_a_corpus_that_meets_its_target_is_written(tmp_path: Path) -> None:
    for index in range(3):
        make_task(tmp_path, f"task-{index}")
    out = tmp_path / "corpus.json"

    audit = build_corpus(discover_tasks(tmp_path), target_tasks=3, out=out)

    assert audit.meets_target
    document = json.loads(out.read_text())
    assert document["passing"] == 3
    assert document["meets_target"] is True


def test_the_corpus_records_what_it_threw_away(tmp_path: Path) -> None:
    # A corpus file listing only what survived would hide its own selection.
    # What had to be discarded, and why, is the interesting part.
    make_task(tmp_path, "good")
    make_task(tmp_path, "leaky", solution="#!/bin/sh\ncurl http://example.com\n")
    out = tmp_path / "corpus.json"

    build_corpus(discover_tasks(tmp_path), target_tasks=1, out=out)

    document = json.loads(out.read_text())
    assert document["audited"] == 2
    assert document["passing"] == 1
    assert document["attrition"] == 0.5

    leaky = next(task for task in document["tasks"] if task["task_id"] == "leaky")
    assert leaky["passed"] is False
    assert leaky["blocking_hazards"] == ["network"]
    assert leaky["findings"]


def test_attrition_is_reported(tmp_path: Path) -> None:
    make_task(tmp_path, "a")
    make_task(tmp_path, "b", solution="#!/bin/sh\nnohup ./x &\n")
    make_task(tmp_path, "c", solution="#!/bin/sh\nnohup ./y &\n")

    audit = audit_tasks(discover_tasks(tmp_path), target_tasks=1)
    assert audit.attrition == pytest.approx(2 / 3)
