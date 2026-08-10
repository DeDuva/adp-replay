# CLAUDE.md — adp-replay

Records agent trajectories on closed-world coding tasks and replays them under
substituted models, producing evidence-gated verdicts about model performance. Built on
ADP (`~/dev/adp`), which supplies hash-chained trajectories, signed run attestations, and
`GET /verify`.

## Where the plans live

- **`ROADMAP.md`** — the single status ledger: phase states, blockers (each with a
  verification date), open decisions. A PR that changes phase status updates it in the
  same PR.
- **`docs/execution-plan.md`** — the plan of record; task-by-task, it decides scope,
  not this file. `README.md` is orientation.

## Process

All work lands on `main` through a pull request — including one-line and docs-only
changes. Commit messages and PR bodies carry no AI attribution.

**Do not regenerate this file with `/init`.** Everything below was decided deliberately
or learned by getting it wrong, and a codebase scan can see none of it. Edit it by hand;
`make check-docs` fails if a path named here stops existing.

## Layout

| Path | What lives there |
|---|---|
| `src/adp_replay/` | the package: manifest, store, recorder, replay, analysis, generated ADP client |
| `spec/adp-openapi.json` | ADP's OpenAPI spec, vendored as JSON — the source the client is generated from |
| `tests/` | pytest suite; `tests/contract/` runs against a **live ADP** |
| `docs/` | the plan, the pre-registration, and every generated report (`g0-`, `g1-`, power analysis, corpus status) |

## Commands

```bash
make check          # the gate: check-docs + lint + types + check-generated + test
make test           # pytest, excluding contract tests
make test-contract  # contract tests against a live ADP (see below)
make generate       # regenerate the ADP client from the vendored spec
```

**`make check` is the gate in every repo in this line of work** — reach for it first
rather than reconstructing the per-repo incantation.

`.claude/settings.json` is checked in and holds the shared permission allowlist — the
targets above plus read-only `gh`. Personal overrides go in `.claude/settings.local.json`,
which is ignored.

**On this machine, pass the interpreter explicitly.** The Makefile defaults to
`PY ?= python3`, and system `python3` is 3.14 without `ensurepip`. `.venv/` here was
created by uv and has **no `pip` inside it**, so `make setup` fails. Either run
`make check PY=.venv/bin/python`, or rebuild the venv from the uv-managed CPython 3.12
(`~/.local/share/uv/python/cpython-3.12-linux-x86_64-gnu/bin/python3.12 -m venv .venv`),
which does ship pip. PyPI is reachable — installs work, including `inspect-ai` and
`terminal-bench`. CI matrixes 3.11 and 3.12.

## Running the contract tests

They never self-skip — a missing environment is a `pytest.fail`, because a gate that
silently stops being tested is worse than one never claimed. CI builds ADP from a pinned
commit (`ADP_REF` in `.github/workflows/ci.yml`) and runs them on every PR.

Locally, bring ADP up from its own checkout, then mint **two** identities — the point is
that the scorer is a different principal from the runner:

```bash
cd ~/dev/adp/server
npx tsx src/bootstrap.ts replay-runner    # prints Identity + Token
npx tsx src/bootstrap.ts replay-scorer
npx tsx src/db/migrate.ts && PORT=3999 npx tsx src/main.ts &
```

```bash
export ADP_BASE_URL=http://localhost:3999
export ADP_RUNNER_TOKEN=... ADP_SCORER_TOKEN=...
export ADP_DATABASE_URL=postgres://adp:adp@localhost:5432/adp   # Task 3.3 only
export ADP_PG_CONTAINER=$(docker ps --format '{{.Names}}' | grep postgres | head -1)
make test-contract PY=.venv/bin/python
```

`ADP_DATABASE_URL` is required by the tamper test, which edits a stored event behind
ADP's back — there is no honest way to check tamper-evidence without tampering. This box
has no `psql`, so that test falls back to `docker exec $ADP_PG_CONTAINER psql`.

## Invariants — the reasons this project is worth anything

- **fork-at-step is a diagnostic, never a model comparison.** Resuming a trajectory from
  step *k* under a different model measures continuation under a foreign policy prefix.
  It carries an unsuppressible banner and is never presented as a ranking. fork-at-zero
  is the comparison.
- **Pre-registration precedes scoring code.** The context-fidelity metric and the G0
  threshold were fixed in `docs/pre-registration.md` before anything could score against
  them. Keep that ordering for any new gate.
- **An unverifiable verdict is an `error`, not a pass or a fail.** Evidence gating
  downgrades any result whose ADP verification does not hold; this is checked by actually
  tampering with a stored event, not by mocking the failure.
- **The runtime is deliberately stdlib + pydantic + httpx.** The power analysis, the
  bootstrap, ICC and the exact McNemar test are hand-written rather than reaching for
  numpy/scipy, so that analysing a published artifact never requires a scientific stack to
  resolve. `inspect-ai` and `terminal-bench` are an optional `harness` extra for the same
  reason. Don't add a core dependency to save a hundred lines of statistics.
- **Bootstrap intervals resample over *tasks*,** not over trials — the unit of
  generalisation is the task.
- **The generated client must match the vendored spec.** `make check-generated` fails on
  drift and CI runs it weekly on a schedule, because ADP moves on its own timeline rather
  than this repository's. Re-vendoring is two-stage on purpose: `make sync-spec` needs
  PyYAML (which only the *system* python has) and writes `spec/adp-openapi.json`;
  `make generate` turns that into Python with the stdlib alone.
- Contract findings against ADP are recorded in `docs/adp-contract-findings.md` and filed
  as ADP issues rather than worked around silently. Setup deliberately uses ADP's compat
  plane — nothing under `/api/adp` mints a repository or an intent — and that is one of
  the recorded findings, not a shortcut.
