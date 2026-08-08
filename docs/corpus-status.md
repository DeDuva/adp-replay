# Corpus status — Task 1.3, first run against real Terminal Bench

**Date:** 2026-08-08. **Result: 0 of 80 tasks closed. 100% attrition.**

This is the first time the closure auditor has been pointed at a real corpus. It
had never been run, because `terminal-bench` was recorded as impossible to install
in this environment. That was wrong — see the retry note in
[`execution-plan.md`](execution-plan.md) — and the corpus was one command away the
whole time.

## What was audited

| | |
|---|---|
| Dataset | `terminal-bench-core`, version **0.1.1**, from the Terminal Bench registry |
| Tasks discovered | **80** |
| Target (Task 0.4 power analysis) | 170 closed tasks, 213 audited to absorb attrition |
| **Closed** | **0** |
| Attrition | **100.0%** |

Blocking hazards, by number of tasks affected:

| hazard | tasks blocked |
|---|---|
| network | 80 |
| background_process | 17 |
| clock | 13 |

## This is a real result, not an instrument artefact

That deserves stating explicitly, because 80-out-of-80 on a single hazard is
exactly the shape a broken detector produces, and the first hypothesis here was
that the detector was at fault.

It is not. Checking every blocking finding for whether its matched token sits in
**command position** (line start, or after `|`, `;`, `&`, `$(`, a backtick, or
`sudo`) rather than merely appearing somewhere in the line:

```
tasks blocked ONLY by non-command-position matches:  0
tasks with at least one genuine blocking finding:   80
```

**Every one of the 80 has a genuine run-time network dependency.** Removing every
questionable match would change nothing about the outcome.

The structural reason is visible in the corpus layout: all 80 tasks share a
`run-tests.sh` that begins

```sh
source $TEST_DIR/setup-uv-pytest.sh
bash $TEST_DIR/run-uv-pytest.sh
```

— the test harness fetches its own Python dependencies at **run** time. Under the
closure definition in `corpus/audit.py` that is blocking by design: network at
build time is pinned by the image digest and acceptable, network at run time puts
a third party's availability inside the measurement, and a replay six weeks later
gets a different internet.

## One genuine precision bug, which does not change the verdict

The network pattern matches bare tokens, so `nc` matches an ordinary variable:

```
nc = c - self.min_col            → flagged NETWORK / BLOCKING
grid[nr][nc] = self.maze[(r, c)] → flagged NETWORK / BLOCKING
```

Counting matches that are *not* in command position: `curl` 183, `dig` 26,
`ssh` 23, `wget` 22, `telnet` 6, `ping` 5, `nc` 4. Most of those are arguments
(`apt-get install curl`) or prose rather than false positives in the damaging
sense, and as measured above **none of them is load-bearing for any task's
verdict**. Worth tightening for the sake of a readable report; not worth
tightening in the hope of a different answer.

## What this means for the plan

The power analysis fixes the design at **170 tasks × 3 repetitions** and assumes a
1.25× audit ratio covers attrition. Against this corpus that assumption does not
survive: the attrition is not 20%, it is total.

`build_corpus` refused to write `tb2_closed_corpus.json`, which is the behaviour
it was built for — a short corpus cannot be quietly mistaken for a finished one.

Three options, none of them chosen here because each changes what the experiment
measures and that is not a decision to take inside an audit:

1. **Widen the corpus.** Audit other registry datasets (`usaco`, adapters) and the
   larger `terminal-bench-core` releases. Whether *any* public corpus of this shape
   is network-closed at run time is now an open question, and this result is weak
   evidence that none is.
2. **Move the closure boundary.** Treat a pinned dependency fetch inside the test
   harness as build-time — defensible if the harness's fetch is itself digest-pinned
   and cached, and a material weakening of the guarantee if it is not.
3. **Vendor the harness dependencies** so `run-tests.sh` needs no registry, making
   the tasks closed by construction rather than by classification.

Option 2 is the cheapest and the most dangerous: it would make 80 tasks "closed"
by redefinition rather than by fact, and the fidelity claim in the pre-registration
rests on that definition meaning what it says.

## Reproducing this

```sh
# Install into a venv built with the uv-managed interpreter — system python3
# here is 3.14 with no ensurepip and cannot create one.
~/.local/share/uv/python/cpython-3.12-linux-x86_64-gnu/bin/python3.12 -m venv .venv
.venv/bin/python -m pip install terminal-bench

.venv/bin/tb datasets download -d terminal-bench-core==0.1.1 --output-dir ./tb-tasks
.venv/bin/python -m adp_replay.cli audit ./tb-tasks --target-tasks 170
```

Note that `-d terminal-bench-core` without a pinned version resolves to `head`,
whose layout the registry client fails to unpack (`FileNotFoundError: .../tasks`).
Pin the version.
