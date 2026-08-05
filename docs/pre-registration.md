# Pre-registration

Fixed commitments, recorded before the code that measures against them exists. An entry here is
amended only by adding a dated amendment below it — never by editing the original.

Referenced by `src/adp_replay/context/fidelity.py` and execution-plan Task 0.3a.

---

## Context fidelity (Gate G0)

**Status: registered 2026-08-05, against `main` at `062a9e5`.**

Registered before any scoring code existed. The machine-readable transcription is
`src/adp_replay/context/registered.py`; `tests/test_registered_metric.py` fails if the two ever
disagree, so the probe cannot quietly score against different numbers than the ones published here.

### Why this gate exists

Fork-at-zero replays a task under a substituted model with the harness pinned. The recorded
trajectory was produced against one provider's wire format; replaying it against another requires
translating the context. Whatever the translation drops, the replayed model never sees.

If enough is dropped, an observed difference between two models is not evidence about the models. It
is evidence about the translator. Fidelity below the bar does not make the result weak — it makes it
uninterpretable, which is why G0 is a hard stop rather than a caveat.

### Canonical context form

A context is an **ordered sequence of elements**. Each element has a type from the closed vocabulary
below and a payload. The canonical form is provider-neutral: every provider's wire format is
rendered *from* it and parsed *back into* it, and neither direction is privileged.

**Scope rule — the metric scores only elements the model can condition on.** An element that changes
cost, latency, or bookkeeping without changing what the model is shown is out of scope and is
reported separately as an *operational delta*, never folded into fidelity. Scoring cache breakpoints
would let a metric about interpretability be moved by a fact about billing.

In scope, with their registered weights:

| element type | weight | what it is |
|---|---|---|
| `system_instruction` | 3 | the system prompt |
| `tool_definition` | 3 | a tool's name, description, and parameter schema as shown to the model |
| `tool_call` | 3 | an assistant's invocation: call id, name, arguments |
| `tool_result` | 3 | the result returned for a call id, and whether it was an error |
| `user_message_text` | 3 | the task statement and any subsequent user turn |
| `assistant_message_text` | 2 | an assistant turn's visible text |
| `assistant_prefill` | 2 | a partial assistant turn the model is required to continue |
| `reasoning_trace` | 2 | model-internal reasoning made visible in the transcript |
| `image_attachment` | 2 | an image in any turn |
| `document_attachment` | 2 | a non-image attachment in any turn |
| `sampling_params` | 2 | temperature, top-p, max tokens, stop sequences |
| `tool_choice` | 2 | auto / none / required / a named tool |
| `turn_structure` | 2 | the sequence of roles, including whether consecutive same-role turns were merged |
| `reasoning_signature` | 1 | a provider's signature binding a reasoning block to its origin |
| `citation_annotation` | 1 | spans attributing assistant text to a source |

Out of scope, reported as operational deltas: cache breakpoints, request identifiers, retry and
timeout configuration, streaming flags, and anything else the model is not shown.

The three weight bands are the whole of the weighting rationale:

- **3 — the task itself.** Losing it changes what is being asked.
- **2 — how the task is framed or constrained.** Losing it changes the conditions under which it is
  being asked.
- **1 — provenance bookkeeping the model does not read as content.**

### Classification: preserved, transformed, lost

Classification is **operational**, not a lookup. For each element `e` of a canonical context `C`
under the ordered pair `A → B`:

1. Render `C` into B's wire format with the harness's translator.
2. Parse that rendering back into canonical form, yielding `C'`.
3. `e` is **preserved** if `C'` contains an element of the same type whose payload is equal after
   normalization, in the same position relative to the other elements of its type.
4. `e` is **transformed** if `C'` contains an element carrying `e`'s payload content — text, tool
   arguments, or parameter schema equal after normalization — but differing in type, role, or a
   documented attribute. A tool result relayed as a user turn because the target has no tool role is
   the canonical case.
5. `e` is **lost** otherwise.

Normalization: text compared with leading and trailing whitespace stripped and internal runs of
whitespace collapsed; JSON compared key-order-insensitively; numbers compared by value.

**Classification follows the consequence, not the mechanism.** If dropping a `reasoning_signature`
forces its `reasoning_trace` to be dropped too, the trace is scored `lost`. A weight-1 element is
not a place to park a weight-2 loss.

**Grounding check.** The round-trip above measures what *this repo's translator* preserves, which is
not the same as what the target provider accepts. For every pair whose target API is reachable, the
rendered request must additionally be accepted by that provider; a request rejected for an element's
sake reclassifies that element as `lost` regardless of what the round-trip said. Where the API is
not reachable the score is reported as round-trip-only and labelled as such in the G0 report.

### The score

Coefficients: `preserved = 1.0`, `transformed = 0.5`, `lost = 0.0`.

A transformed element delivers its content but not its frame. There is no evidence available before
measurement about which of the two matters more, so the neutral split is the only one that cannot be
argued after the fact to have been chosen to clear the bar. It is fixed at 0.5 and is not tunable by
Task 0.3b.

Scoring proceeds **per element type, then across types** — never per element instance directly:

1. For each type `t` present in `C`, its type score is the mean of the coefficients of that type's
   instances.
2. The context's fidelity is the weighted mean of the type scores, using the registered weights,
   renormalized over the types actually present.

Per-instance averaging was rejected for a specific reason: message text outnumbers everything else
by one to two orders of magnitude, so an instance-weighted metric reports "did the prose survive"
and reads near 1.0 while every tool definition is being dropped. The losses that make a replay
uninterpretable are small in count and large in consequence.

A type absent from `C` is excluded from that context's mean rather than scored zero — a context with
no images is not thereby less faithful.

Fidelity is one-directional. A target that supports something the source never used earns nothing;
the question is only what survived.

### The distribution the threshold is read against

- **Unit of observation:** one translated context, scored for one ordered provider pair.
- **Unit of aggregation:** the `(ordered provider pair, capability)` cell, where capability is
  `fork_at_zero` or `fork_at_step`.
- **Within a cell:** take each task's median over its own contexts first, then the median over
  tasks. A task with a long trajectory must not outvote a short one — the same reason Task 3.1
  resamples over tasks and never over trajectories.

`fork_at_zero` and `fork_at_step` are scored as **separate cells and never pooled**. Fork-at-zero
translates only an initial context — a system prompt, tool definitions, and a task statement — which
is the easy case. Pooling would let a near-perfect score there carry a continuation diagnostic that
is uninterpretable on its own.

### The pass mark

**G0 passes when every in-scope cell has a median fidelity ≥ 0.85.**

Reported with it, in the G0 report and not in an appendix: the per-cell median, the interquartile
range, the number of tasks behind it, and every element type classified `lost` at least once, with
its count.

Provider scope at registration is **Anthropic, OpenAI, and Google**, all six ordered pairs, each
scored for both capabilities: twelve cells.

### Accepted narrowing of provider scope

The only narrowing permitted without an amendment is **dropping a whole provider** — removing every
cell involving it — down to a floor of **two providers and two ordered pairs**. This is cut line 1 of
the execution plan, taken as pre-approved.

Everything else requires a dated amendment: dropping one direction of a pair while keeping the
other, dropping a capability, dropping an element type from the metric, or changing any weight,
coefficient, aggregation rule, or the 0.85 mark.

A narrowing is recorded as an amendment **carrying the failing numbers that motivated it**, so that
"we dropped the pair that failed" is legible as exactly that rather than as a scope decision that
happened to precede a pass. The decision is the repository owner's.

If no permitted narrowing clears the bar, replayer work stops. That is kill criterion G0.

### What Task 0.3b may not do

The weight table, the three coefficients, the two-level median, the per-type-then-across-types
aggregation, the scope rule, and the 0.85 mark are fixed as of this registration. Task 0.3b
implements against them and reads them from `registered.py`; it does not restate them and cannot
adjust them.

Any change is an amendment below, dated, with its reason and the measurement that prompted it. Where
an amendment changes a number, results computed under the pre-amendment definition are reported
alongside the new ones.

## Experiment design (Task 0.4)

**Status: registered 2026-08-05.** Fixed before any data is collected. The analysis is
`src/adp_replay/stats/power.py`; the reading is `docs/power-analysis.md`, regenerable with
`adp-replay power`.

### Primary outcome and test

- **Primary outcome:** a task counts as **solved** by a model when a **majority of its repetitions
  pass**. One binary outcome per (task, model), paired across models on the same task.
- **Test:** **exact McNemar** on the paired per-task outcomes, two-sided, alpha 0.05. Exact rather
  than the chi-square approximation because the sample size for this test is the number of
  *discordant pairs*, not the number of tasks, and a corpus this size lands in the regime where the
  approximation is not trustworthy.
- **Resampling unit for confidence intervals: tasks**, never trajectories. Repetitions within a task
  are not independent samples.

These are fixed now, before data exists. The power analysis simulates this exact test rather than a
convenient stand-in, because a design powered against one test and reported with another arrives
underpowered on the day it is analysed.

### Assumptions, and why these values

Every one of them is a guess. They are recorded so that when pilot data replaces them, the
substitution is visible.

| assumption | value | justification |
|---|---|---|
| base success rate | 0.45 | Where frontier models sit on closed, container-scoped coding tasks. Chosen near 0.5 deliberately: that is where a paired binary comparison has the most discordant pairs to work with, so it is not a conservative choice and must be revisited if the real rate is extreme. |
| effect size | 0.10 | The smallest difference worth publishing a model comparison over: 45% against 55%. Smaller differences are within the range that harness and scaffold choices move a result, and this project cannot separate those. |
| between-task SD (logit) | 1.5 | Task difficulty in an agentic corpus is wildly dispersed — some tasks every model solves, some none do. 1.5 puts the middle half of tasks between roughly 20% and 72% success. |
| alpha | 0.05 | Conventional, and fixed here rather than chosen after seeing a p-value. |

### The recommendation

**170 tasks x 3 repetitions**, achieving power **0.806** against a target of 0.8. That is 1020
recorded trajectories across the two models.

**Task 1.3 audits at least 213 tasks** — 1.25x the target, to absorb attrition from the closure
audit.

### Why not the cheapest design

**310 tasks x 1 repetition** reaches power 0.812 for 620 trajectories, which is cheaper, and it is
excluded. Task 3.1 commits to reporting ICC and a between-versus-within variance decomposition, and
within-task variance is not defined at a single repetition. A design cannot be chosen on cost when it
cannot support the analysis it exists to feed.

This is recorded rather than left implicit because "we picked the cheapest design that reached power"
is what a reader would otherwise assume, and it is not what happened.

### Sensitivity

The design is not fragile to the variance assumption and is fragile to the effect-size assumption.

| effect size | power | | between-task SD | power |
|---|---|---|---|---|
| 0.05 | 0.28 | | 0.75 | 0.77 |
| 0.075 | 0.56 | | 1.0 | 0.79 |
| **0.10** | **0.81** | | **1.5** | **0.81** |
| 0.125 | 0.94 | | 2.0 | 0.85 |
| 0.15 | 0.99 | | 2.5 | 0.89 |

Power *rises* with between-task spread, which reads backwards and is worth stating plainly. Holding
the marginal success rate fixed, a wider spread of task difficulty requires a larger shift on the
log-odds scale to move that rate by the same ten points, and the larger shift produces more
discordant pairs — the only pairs McNemar reads.

So the risk to this design is not a corpus more heterogeneous than assumed. It is a **true effect
smaller than 0.10**: at 0.075 the design has power 0.56, and at 0.05 it has 0.28. If the two models
under comparison turn out closer than ten points, this corpus size does not settle the question, and
the honest report is a confidence interval rather than a verdict.

## Amendments

### Amendment 1 — a dropped id is preserved when the binding is order-recoverable

**Dated 2026-08-05. Decided by the repository owner. Amends "Classification: preserved, transformed,
lost".**

#### The measurement that prompted it

The first G0 reading, taken after Task 0.3b landed and before this amendment:

| pair | capability | median | verdict |
|---|---|---|---|
| anthropic->openai | fork_at_zero | 1.000 | pass |
| anthropic->openai | fork_at_step | 0.951 | pass |
| anthropic->google | fork_at_zero | 1.000 | pass |
| **anthropic->google** | **fork_at_step** | **0.846** | **FAIL** |
| openai->anthropic | fork_at_zero | 1.000 | pass |
| openai->anthropic | fork_at_step | 1.000 | pass |
| openai->google | fork_at_zero | 1.000 | pass |
| openai->google | fork_at_step | 0.870 | pass |
| google->anthropic | fork_at_zero | 1.000 | pass |
| google->anthropic | fork_at_step | 1.000 | pass |
| google->openai | fork_at_zero | 1.000 | pass |
| google->openai | fork_at_step | 1.000 | pass |

Grounding `round_trip_only`, corpus
`sha256:0ffe967ad3a1d429f2a572fab6a6654466d4f00af3b9084b97f2e746e2a831f8`.

One cell of twelve failed, at 0.846 against 0.85.

#### The change

A `tool_call`'s `id`, and a `tool_result`'s binding to it, are scored **preserved** when the binding
is reconstructable without them — at most one call outstanding at the point the result appears, so
call and response pair by order alone. With two or more outstanding they remain **transformed**.

Everything else is unchanged: the weights, the other coefficients, the aggregation, the pass mark,
and the provider scope. The carve-out ignores the binding attribute and only that one, so a result
that also loses its error flag is still a transform.

#### Why

The original rule charged a flat transform whenever an id was dropped, whether or not anything had
become ambiguous. For a trajectory that issues one tool call at a time — which is most of them —
nothing is ambiguous: a format matching responses by name rather than by id reconstructs the pairing
from order, and the replayed model sees exactly what the recorded one saw. Scoring that a loss made
the metric report a fact about wire syntax rather than about what reached the model, and it did so on
two weight-3 element types in every trajectory that touches a tool.

The concurrent case is deliberately left alone. With two calls in flight an answer really can be
attributed to the wrong call, and no care in the translator recovers it.

#### The alternative that was rejected, and why it matters

The pre-approved response to a failing cell was to drop a provider. That would have removed the third
provider on the strength of a metric artefact, and the artefact would have stayed in place to mislead
the next reading. Narrowing scope to avoid fixing a metric is the failure mode the pre-registration
exists to make visible, so it is recorded here that this was the available alternative and was not
taken.

#### Effect on the reading

| pair | capability | before | after |
|---|---|---|---|
| anthropic->google | fork_at_step | 0.846 | 0.951 |
| openai->google | fork_at_step | 0.870 | 1.000 |

The other ten cells moved by 0.000. That the amendment touched only the cells targeting the format
whose binding it concerns is the check that it is a correction and not a general lift.

G0 passes under the amended metric. **Both readings are printed in every G0 report** and the
pre-amendment scoring remains computable in code, so this is falsifiable rather than merely
asserted.
