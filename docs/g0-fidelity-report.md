# Gate G0 — context fidelity

**PASS** — every in-scope cell must reach a median of 0.85.

- Grounding: `round_trip_only`
- Providers: anthropic, openai, google
- Corpus: `sha256:0ffe967ad3a1d429f2a572fab6a6654466d4f00af3b9084b97f2e746e2a831f8`

| pair | capability | median | IQR | tasks | contexts | verdict |
|---|---|---|---|---|---|---|
| anthropic->openai | fork_at_zero | 1.000 | 1.000-1.000 | 5 | 5 | pass |
| anthropic->openai | fork_at_step | 0.951 | 0.885-0.962 | 5 | 8 | pass |
| anthropic->google | fork_at_zero | 1.000 | 1.000-1.000 | 5 | 5 | pass |
| anthropic->google | fork_at_step | 0.951 | 0.885-0.962 | 5 | 8 | pass |
| openai->anthropic | fork_at_zero | 1.000 | 1.000-1.000 | 5 | 5 | pass |
| openai->anthropic | fork_at_step | 1.000 | 1.000-1.000 | 5 | 8 | pass |
| openai->google | fork_at_zero | 1.000 | 1.000-1.000 | 5 | 5 | pass |
| openai->google | fork_at_step | 1.000 | 1.000-1.000 | 5 | 8 | pass |
| google->anthropic | fork_at_zero | 1.000 | 1.000-1.000 | 5 | 5 | pass |
| google->anthropic | fork_at_step | 1.000 | 1.000-1.000 | 5 | 8 | pass |
| google->openai | fork_at_zero | 1.000 | 1.000-1.000 | 5 | 5 | pass |
| google->openai | fork_at_step | 1.000 | 1.000-1.000 | 5 | 8 | pass |

## The same cells before the amendments

Printed because an amended metric that only ever showed its post-amendment
numbers could not be checked. Amendments in force: 1 (2026-08-05): a dropped id is preserved when the binding is order-recoverable.

| pair | capability | before | after | moved |
|---|---|---|---|---|
| anthropic->openai | fork_at_zero | 1.000 | 1.000 | +0.000 |
| anthropic->openai | fork_at_step | 0.951 | 0.951 | +0.000 |
| anthropic->google | fork_at_zero | 1.000 | 1.000 | +0.000 |
| anthropic->google | fork_at_step | 0.846 | 0.951 | +0.105 |
| openai->anthropic | fork_at_zero | 1.000 | 1.000 | +0.000 |
| openai->anthropic | fork_at_step | 1.000 | 1.000 | +0.000 |
| openai->google | fork_at_zero | 1.000 | 1.000 | +0.000 |
| openai->google | fork_at_step | 0.870 | 1.000 | +0.130 |
| google->anthropic | fork_at_zero | 1.000 | 1.000 | +0.000 |
| google->anthropic | fork_at_step | 1.000 | 1.000 | +0.000 |
| google->openai | fork_at_zero | 1.000 | 1.000 | +0.000 |
| google->openai | fork_at_step | 1.000 | 1.000 | +0.000 |

## Elements lost, by cell

- `anthropic->openai` / fork_at_zero: document_attachment x1
- `anthropic->openai` / fork_at_step: reasoning_signature x5, reasoning_trace x5, citation_annotation x1, document_attachment x1
- `anthropic->google` / fork_at_zero: none
- `anthropic->google` / fork_at_step: reasoning_signature x5, reasoning_trace x5, citation_annotation x1
- `openai->anthropic` / fork_at_zero: none
- `openai->anthropic` / fork_at_step: none
- `openai->google` / fork_at_zero: none
- `openai->google` / fork_at_step: none
- `google->anthropic` / fork_at_zero: none
- `google->anthropic` / fork_at_step: none
- `google->openai` / fork_at_zero: document_attachment x1
- `google->openai` / fork_at_step: document_attachment x1

> Round-trip only. These numbers say what this repository's translators preserve, not what the target providers accept. The registered grounding check — the rendered request must additionally be accepted by the target API — has not run.
