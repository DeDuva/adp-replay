# Report schema (Task 3.2)

`adp_replay.report.render_json` emits this document. Version `0.1.0`.

The ordering of the top-level keys is part of the schema. **State completeness and median context
fidelity come before the statistics**, in the JSON as well as in the HTML, because both are limits on
what the numbers mean and a limit that appears after the conclusion has already been read is not a
limit. A consumer that reads only the head of this document still gets them.

## Top level

| field | type | meaning |
|---|---|---|
| `schema_version` | string | This schema's version. |
| `state_completeness` | `"filesystem"` | What the snapshots captured. v0 captures the filesystem and nothing else — no processes, sockets, or kernel state. |
| `median_context_fidelity` | number \| null | Median fidelity for the provider pair these results used (Task 0.3b). `null` means **not measured**, which is different from `0`. |
| `is_model_comparison` | boolean | True only when every result is fork-at-zero. |
| `banner` | string | Present **only** when some result is a continuation diagnostic, and then always. See below. |
| `corpus_digest` | string \| null | Which corpus was scored. |
| `adp_contract_version` | string \| null | The ADP wire contract the evidence came from. |
| `tasks` | integer | Task count, identical in both arms. |
| `arms` | object | `baseline` and `treatment` labels. |
| `statistics` | object | See below. |
| `results` | object | Per-task results for each arm. |

## `statistics`

| field | type | meaning |
|---|---|---|
| `test` | string | Always exact McNemar on paired per-task outcomes. Fixed before data collection (pre-registration, Task 0.4). |
| `p_value` | number | Exact two-sided McNemar p-value. |
| `contingency` | object | `both`, `baseline_only`, `treatment_only`, `neither` — task counts. Only the discordant cells carry information. |
| `difference_ci` | `[low, high]` | 95% bootstrap interval for the difference in solve rate. |
| `resampling_unit` | `"tasks"` | **Always tasks, never trajectories.** |
| `confidence` | number | 0.95. |
| `baseline`, `treatment` | object | Per-arm: `solved`, `errors`, `rate_ci`, `variance`. |

### `variance`

`icc`, `between_tasks`, `within_tasks` — a one-way random-effects ICC(1) over per-repetition
outcomes. Near 1, the corpus is doing the work and more repetitions buy little. Near 0, the outcome
is mostly run-to-run noise and no number of such tasks settles anything.

When there are too few repetitions to separate the two components, this is
`{"unavailable": "<reason>"}` rather than zero. Reporting zero would read as "no within-task
variance" instead of "not measured".

## `errors` are not failures

An attempt whose evidence did not verify is `error`, never `pass` and never `fail` — those are claims
about the model, and a run whose evidence does not stand up supports neither. Errors count **against**
the majority when deciding whether a task was solved, so a task with one pass and four unverifiable
attempts does not report as solved.

Each downgraded verdict records which sub-check of ADP's `verify` failed, so a downgrade is
diagnosable rather than merely observed.

## The banner

When present it is exactly:

> Continuation diagnostic: measures Model B's ability to continue Model A's trajectory prefix. Not a
> pinned-harness model comparison.

It is computed from the mode rather than stored, so no configuration can drop it. A consumer
rendering this document must show it whenever it is present; a fork-at-step result quoted without it
reads as a model comparison, which it is not.
