# adp-replay — Roadmap

**This file is the repo's only status ledger.** A PR that completes, starts, pauses, or
supersedes a phase updates this file in the same PR. Scope is decided by the plan of
record, [`docs/execution-plan.md`](docs/execution-plan.md) — this file says where the
project is, not how the next piece gets built.

## Mission

Record agent trajectories on closed-world coding tasks and replay them under substituted
models, producing statistically defensible, evidence-gated verdicts about model
performance. The primary capability is **fork-at-zero** replay with the harness pinned;
fork-at-step is a diagnostic and is never presented as a model comparison.

## Where this fits

Built on ADP (`github.com/DeDuva/adp`), consumed over its REST wire contract, pinned at
`.github/workflows/ci.yml`'s `ADP_REF` with the client generated from the vendored spec.
`adp_replay.stats.paired` is the statistics library both duva-bench tracks depend on,
pinned by commit. The full dependency map is ADP's `docs/ecosystem.md`.

## Milestone ledger

Phases are this project's milestones. Contract pinned: **ADP 0.2.0**.

| Phase | Status | Evidence / detail |
|---|---|---|
| Phase 0 — specs and de-risking | complete | **Gate G0 passes** — median fidelity 0.951 on the worst in-scope cell, under [Amendment 1](docs/pre-registration.md) (2026-08-05), pre-amendment numbers printed beside current in every report. Power analysis fixes the corpus at **170 tasks × 3 reps** ([`docs/power-analysis.md`](docs/power-analysis.md)) |
| Phase 1 — storage and recording | in progress | Tasks 1.1, 1.2, 1.4, 1.5 complete; **Gate G1 passes** (1.4% median overhead vs 10% budget). Task 1.3's corpus is the only open item, and it is open on a **decision**, not on work — see below |
| Phase 2 — replay | complete | Fork-at-zero, the banner-carrying fork-at-step diagnostic, the identity preflight. No provider is called anywhere in the package by design |
| Phase 3 — analysis and reporting | complete | Exact McNemar, bootstrap over tasks, ICC; evidence gating proven by tampering with a stored event |
| Phase 4 — public artifact | not started | **The primary capability, never yet executed against a real model.** Not blocked on access — needs a budget number and a corpus |

## Now / Next / Later

- **Now:** nothing in flight.
- **Next:** the corpus decision (below) — it gates Task 1.3 and sizes Phase 4. Then
  Phase 4, scoped as its own milestone plan before any spend, run on a small slice
  first with cost-per-trial reported before scaling.
- **Later:** the published artifact — all manifests, all reports, a write-up leading
  with fork-at-zero.

## Blockers and open decisions

- **Corpus attrition — decision needed (author).** Verified 2026-08-08 by running the
  closure audit against a real corpus for the first time: **0 of 80 tasks in
  `terminal-bench-core` 0.1.1 are closed — 100% attrition**, every one on a genuine
  run-time network dependency. The plan's 1.25× audit ratio does not survive this.
  [`docs/corpus-status.md`](docs/corpus-status.md) states three options — widen the
  corpus, move the closure boundary, vendor the harness dependencies — and takes none;
  each changes what the experiment measures.
- **Phase 4 budget — decision needed (author).** Verified 2026-08-08: working Anthropic
  and Gemini keys at `~/.config/squad/`, in daily use by sibling projects. Calibration:
  a comparable 24-trial pilot cost $8.03; an 80-run study ~$28. The only outstanding
  input is a number.
- *(History: three earlier "environment cannot install dependencies" blockers were all
  disproved by direct test on 2026-08-08 — the lesson that blockers carry verification
  dates now, recorded in the plan's retry note.)*

## Plan documents

- [`docs/execution-plan.md`](docs/execution-plan.md) — the plan of record: phases,
  tasks with done-conditions, gates G0/G1, cut lines, kill criteria.
- [`docs/pre-registration.md`](docs/pre-registration.md) — the G0 metric and threshold,
  fixed before scoring code, with amendments logged.
- [`docs/corpus-status.md`](docs/corpus-status.md) — the corpus result and the open
  decision. [`docs/closure-audit.md`](docs/closure-audit.md) is the auditor's method.
- [`docs/adp-contract-findings.md`](docs/adp-contract-findings.md) — defects found in
  ADP's contract, filed as ADP issues.
