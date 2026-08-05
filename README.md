# adp-replay

Records agent trajectories on closed-world coding tasks and replays them under substituted models,
producing statistically defensible, evidence-gated verdicts about model performance.

Two capabilities, and the distinction between them is load-bearing:

- **fork-at-zero** — replay a task from its initial state under a different model with the harness
  pinned. This is a model comparison.
- **fork-at-step** — resume a trajectory from step *k* under a different model. This measures
  continuation under a foreign policy prefix. It is a diagnostic, **not** a model comparison, and is
  never presented as one.

The full task-by-task build plan is [`docs/execution-plan.md`](docs/execution-plan.md). It is the
plan of record; this README is orientation only.

## Status

Phase 0 in progress.

- **0.1, 0.2** — manifest models and their self-certifying digest.
- **0.3a** — the context-fidelity metric and the G0 threshold are
  [pre-registered](docs/pre-registration.md), before any code that scores against them.

Everything else under `src/adp_replay/` is still a typed stub naming the task that fills it in.

A manifest verifies from the file alone, with no access to the store it came out of:

```sh
adp-replay manifest verify run-manifest.json
```

## Layout

| Path | Execution-plan task |
|---|---|
| `src/adp_replay/manifest/` | 0.1 — manifest models and the self-certifying digest |
| `src/adp_replay/context/` | 0.3a/0.3b — canonical context form and the fidelity probe |
| `src/adp_replay/stats/` | 0.4 power analysis, 3.1 paired statistics |
| `src/adp_replay/storage/` | 1.1 `CAStore`, 1.2 filesystem-delta capture |
| `src/adp_replay/recording/` | 1.4 recorder and its local spool |
| `src/adp_replay/replay/` | 2.1 fork-at-zero, 2.2 fork-at-step, 2.3 experiment runner |
| `src/adp_replay/verdict/` | 3.3 evidence gating |
| `src/adp_replay/report/` | 3.2 HTML and JSON reports |
| `src/adp_replay/adp/` | the ADP wire-contract client (§2) |

## Relationship to ADP

`adp-replay` depends on [ADP](https://github.com/DeDuva/adp) over its **REST API**, as a versioned
wire contract. It does not link an ADP library and makes no assumption about ADP's implementation
language — the client is generated from ADP's `spec/openapi.yaml`, and the served API version is
asserted at startup.

ADP supplies the trust properties this project needs and does not reimplement: hash-chained
trajectory events, signed checkpoints, scorer identity, and a single verification endpoint that says
whether a run's evidence holds up.

## Development

```sh
make setup    # editable install with dev extras
make lint     # ruff
make types    # mypy
make test     # pytest, excluding contract tests
make check    # all of the above
```

Contract tests need a running ADP instance and are excluded from the default run:

```sh
make test-contract    # requires ADP_BASE_URL and ADP_TOKEN
```

## License

Apache-2.0. See [LICENSE](LICENSE).
