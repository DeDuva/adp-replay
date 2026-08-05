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

**Status: not yet registered.** Filled in when the power analysis reports.

Required entries:

- Target effect size and assumed variance, with their justification.
- The recommended (T tasks, n repetitions) and the achieved power.
- The primary outcome and the test applied to it (exact McNemar), fixed before data collection.
- The resampling unit for confidence intervals: **tasks**, never trajectories.

## Amendments

None.
