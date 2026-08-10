# adp-replay — MVP Execution Plan (v0.3)

An execution-grade plan for building the `adp-replay` MVP. Tasks are written to be followed in order
by AI coding agents or junior engineers without requiring strategic context. Each task states its
deliverable and its done-condition. Gates are hard stops.

**Scope:** 2 engineers × 14–16 weeks.

> **Status moved 2026-08-09.** Current phase status, blockers, and open decisions live in
> [`/ROADMAP.md`](../ROADMAP.md) — the repo's single status ledger, updated in the same PR
> as any status change, per the planning convention shared by every repo in this line of
> work. This plan decides scope; it no longer carries dated status blocks, because a stack
> of status blockquotes at the top of a plan is exactly how the ledger and reality drift
> apart.
>
> One lesson from that drift stays here, because it is about how to *read* this plan: on
> 2026-08-08 three items recorded as "blocked on a dependency unavailable in the build
> environment" were all disproved by direct test — the system Python cannot build a venv,
> but the uv-managed CPython 3.12 (see `CLAUDE.md`) always could, and the cost was that the
> project's primary capability sat unexecuted behind a false blocker. **A recorded blocker
> without a verification date is a rumor; re-verify before believing it.**

---

## 1. What this builds

`adp-replay` records agent trajectories on closed-world coding tasks and replays them under
substituted models, producing statistically defensible, evidence-gated verdicts about model
performance.

The primary capability is **fork-at-zero**: replay a task from its initial state under a different
model, with the harness pinned. This is a model comparison and may be described as one.

The secondary capability is **fork-at-step**: resume a trajectory from step *k* under a different
model. This measures continuation under a foreign policy prefix. It is a diagnostic. It is **not** a
model comparison and must never be presented as one.

---

## 2. Repository and dependencies

Standalone repo, Apache-2.0. Source modules: `storage/`, `manifest/`, `recording/`, `context/`,
`replay/`, `verdict/`, `stats/`, `report/`.

### Dependency on ADP

`adp-replay` depends on ADP over its **REST API**, as a versioned wire contract. It does not link an
ADP library and does not assume ADP's implementation language.

- Generate the client from ADP's `spec/openapi.yaml`. Do not hand-write it.
- Assert the served API version at startup and fail loudly on mismatch — never mid-experiment.
- Maintain a contract test against a pinned ADP container in CI, so an ADP change breaks
  `adp-replay` loudly rather than silently.
- ADP's GraphQL endpoint may be used for read-side reporting. The recording hot path is REST.

ADP serves its contract version as `ADP-API-Version` on every response, including 401s and 404s, so
the assertion runs before this client holds a token. The contract is **0.1.0**; ADP's
`docs/api-compatibility.md` states what a bump promises. Pinning the ADP container by image digest
alongside the version assertion is reasonable belt-and-braces pre-1.0.

### ADP surfaces this plan consumes

| Purpose | Endpoint / field |
|---|---|
| Record trajectory steps | `POST /api/adp/repos/{o}/{r}/sessions/{id}/events` (batch) |
| Attest state snapshots | `POST /api/adp/repos/{o}/{r}/sessions/{id}/checkpoints` |
| Open / close a run | `POST /api/adp/repos/{o}/{r}/runs`, `.../runs/{runId}/close` |
| Report a score | `POST /api/adp/repos/{o}/{r}/runs/{runId}/evals` |
| Gate a verdict on evidence | `GET /api/adp/repos/{o}/{r}/runs/{runId}/verify` |

---

## 3. Phase 0 — Specs and de-risking (weeks 1–3)

### Task 0.1 — Manifest specification

Pydantic models for: environment, state completeness, model, tools, step records, verdicts, run
manifest.

The manifest digest **self-certifies**: computed over the canonical form with `run_id` excluded, so a
manifest can be verified without knowing where it was stored.

Where a run is recorded to ADP, the manifest records ADP's `trajectory_digest` for that run. Bind to
it; do not recompute a parallel chain digest.

**Done when:** a manifest round-trips through serialization with a stable digest, and digest equality
is insensitive to `run_id` and to key ordering.

### Task 0.2 — State-completeness levels

Document the levels. **v0 supports filesystem capture only.** Processes, sockets, and kernel state are
out of scope and must be declared as such in every manifest.

`state_completeness` is a required manifest field, not an annotation. Every report reprints it.

**Done when:** a manifest cannot be constructed without declaring a level.

### Task 0.3a — Define and pre-register the fidelity metric

Define the canonical context form and the transform tables per provider pair. Define the
context-fidelity score: what counts as preserved, transformed, or lost.

**Pre-register the G0 threshold and its distribution before any scoring code is written.** Record the
threshold in the repo with a timestamp. The metric's definition and its pass mark must not be
finalized by the same work that measures against it.

**Done when:** threshold and metric are committed, and neither can be adjusted by later measurement
without an explicit, logged amendment.

### Task 0.3b — Implement the fidelity probe

Implement scoring against the pre-registered definition. Report per provider pair: median fidelity,
spread, and the specific elements lost.

### Gate G0 — Fidelity

**Median fidelity ≥ 0.85** on the pre-registered metric, or an accepted narrowing of provider scope
that clears it.

**If neither holds, replayer work stops.** Fidelity below this makes replay results uninterpretable —
differences would be attributable to context loss rather than to the model.

### Task 0.4 — Power analysis

Simulation-based. Output the smallest (T tasks, n repetitions) design achieving **≥ 0.8 power** for
the target effect size.

**This task sets the corpus size.** Task 1.3 takes its target from here. Do not fix a corpus size
before this reports.

**Done when:** the tool emits a recommended (T, n) with its assumed effect size and variance, and a
sensitivity curve around both.

---

## 4. Phase 1 — Storage and recording (weeks 3–7)

### Task 1.1 — Content-addressed store

Implement the `CAStore` protocol with `LocalCAStore`.

**Snapshot bytes stay local.** Attest them to ADP by digest via
`POST /sessions/{id}/checkpoints`: the `state` field is opaque to ADP and never parsed, and the
response is a signed DSSE envelope binding the commit to a SHA-256 digest of `state`. This gives
attested state provenance without moving large payloads.

A remote CAS backend is **post-MVP**.

**Done when:** a snapshot digest recorded in a checkpoint verifies against the returned envelope.

### Task 1.2 — Filesystem-delta capture

Tarball snapshots before and after tool execution. Normalize mtimes and ordering so digests are
content-determined and reproducible across machines.

**Done when:** capturing the same tree twice on two machines yields identical digests.

### Task 1.3 — Terminal Bench plugin and closure audit

Audit tasks for closure, flagging: network use, background-process dependence, and clock dependence.

Target task count comes from **Task 0.4**. Audit at least 1.25× the target to absorb attrition.

Produces `tb2_closed_corpus.json`.

**Done when:** the audited, passing corpus meets or exceeds the Task 0.4 target.

### Task 1.4 — Recorder

An Inspect solver wrapper capturing outbound requests, tool execution, and state deltas, emitting
steps to ADP.

Recording protocol:

- Spool locally; append in **batches** with `producer_seq` and `client_event_id`.
- Flush **asynchronously**. A tool call must never block on an ADP write.
- On a contiguity rejection (409), replay the spool from the returned `expected_next_seq`.
- Trim the spool at `accepted_through`.
- Treat a non-zero `duplicates` count as a bug signal, not as normal operation.

**Done when:** killing the recorder mid-run and restarting it produces a complete, gap-free chain.

### Task 1.5 — Overhead benchmark

Measure wall-clock overhead versus an unrecorded baseline. **The budget is inclusive of ADP
round-trips** — measure the real system, not the recorder in isolation.

### Gate G1 — Overhead

**Median recording overhead ≤ 10%**, inclusive of ADP round-trips, after optimization.

---

## 5. Phase 2 — Replay (weeks 7–11)

### Task 2.1 — Fork-at-zero replay

Materialize base state, reconstruct the initial context, and run independent repetitions against a
substituted model with the harness pinned.

**Refuse any comparison across differing scorer digests.** Scorer identity is ADP's `spec_digest` on
the eval. Two results produced by different scorers are not comparable and the runner must error
rather than aggregate them.

**Done when:** a deliberate scorer-digest mismatch is refused with a clear error.

### Task 2.2 — Fork-at-step diagnostic

Resume from step *k* under a substituted model.

Every artifact, report, and console run carries this banner verbatim:

> Continuation diagnostic: measures Model B's ability to continue Model A's trajectory prefix. Not a
> pinned-harness model comparison.

**Done when:** the banner cannot be suppressed by configuration.

### Task 2.3 — Cross-provider experiment runner

Resumable progress, concurrency controls, per-provider rate limiting, and cost accounting.

**Identity requirement:** the scorer's ADP bearer token must be a **different principal** than the
runner's, or scores are self-reported and `separately_authorized` will be false.

**Assert `separately_authorized === true` at experiment start**, before any spend — not at analysis
time, when the corpus is already burned.

**Done when:** starting a run with a single shared token fails immediately with a clear message.

---

## 6. Phase 3 — Analysis and reporting (weeks 11–14)

### Task 3.1 — Paired statistics

- Exact **McNemar** tests for paired pass/fail.
- Bootstrap confidence intervals resampled **over tasks, never over trajectories**. Trajectories
  within a task are not independent samples; resampling them inflates significance.
- ICC and variance decomposition, reporting how much variance sits between tasks versus within.

### Task 3.2 — Reports

Self-contained HTML and JSON, with the JSON schema documented. **State completeness and median
context fidelity appear in the header of every report**, not in an appendix.

### Task 3.3 — Evidence gating

A verdict is admissible only with resolvable scorer identity and verifiable step evidence.

Implementation: call `GET /runs/{runId}/verify`. It returns a single `ok` alongside `chains_ok`
(events were not edited), `emitters_ok` (no events were withheld), `envelope_verified`,
`trajectory_digest_matches`, and per-eval `separately_authorized`.

**If `ok` is false, the verdict is downgraded to `error`.** An unverifiable result is never counted as
a pass or a fail. Record which sub-check failed, so a downgrade is diagnosable.

**Done when:** tampering with a recorded event causes the corresponding verdict to become `error`.

---

## 7. Phase 4 — Public artifact (weeks 14–16)

Run the full experiment at the scale Task 0.4 recommends, across providers.

Publish all manifests, all reports, and a write-up that leads with **fork-at-zero**. The
state-completeness specification from Task 0.2 is **reprinted verbatim in the limitations section**.

Fork-at-step results, if included, carry the Task 2.2 banner.

---

## 8. Cut lines

In priority order, when time is short:

1. Third provider → two providers.
2. Divergence categorical analysis → step-level only.
3. HTML report polish → JSON minimum.

**Never cut:** the power analysis, the closure audit, fidelity reporting, evidence gating, or the
confidence-intervals-over-tasks rule. These are what make the result trustworthy; without them the
artifact is not worth publishing.

## 9. Kill criteria

- **G0:** median fidelity < 0.85 with no acceptable narrowing.
- **G1:** overhead > 10% after optimization.

## 10. Non-goals

Network cassettes. Process or VM checkpointing. Multi-agent runs. Non-Inspect harnesses. A web UI.
OpenTelemetry export. ADP feature work.
