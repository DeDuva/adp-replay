# Gate G1 — recording overhead

**PASS** — median overhead 1.4% against a 10% budget, inclusive of ADP round-trips.

Reference step duration: 0.25s. 3 trial(s) per point, best-of taken to suppress scheduler noise.

Overhead is the recorder's cost divided by how long a step takes, so a single
percentage means nothing without the step duration beside it. The curve is what
says whether the headline is robust or an artifact of one choice.

| step | steps | baseline | recorded | overhead | |
|---|---|---|---|---|---|
| 0.05s | 40 | 2.007s | 2.068s | +3.1% | pass |
| 0.1s | 40 | 4.008s | 4.067s | +1.5% | pass |
| 0.25s | 40 | 10.007s | 10.135s | +1.3% | pass |
| 0.5s | 40 | 20.007s | 20.055s | +0.2% | pass |

## How this was measured

Against a live ADP serving contract 0.1.0, on one developer machine, with Postgres in a
local container. The recorded arm spools an event per step, flushes asynchronously in batches, and
**closes** — the final flush is inside the measurement, because a recorder that abandoned its tail
would look fast by not doing its job.

Both arms simulate the step itself with a sleep. That is the honest way to isolate the recorder's
cost: a real model call would add seconds of variance that swamp the thing being measured, and would
make the result a fact about provider latency rather than about recording.

## What this does not establish

The absolute cost per step, not the percentage, is the transferable number here — roughly a
millisecond of wall clock per recorded step on this machine, against a local ADP. A remote ADP with
50ms of round-trip latency does not change it much, because the flush is asynchronous and batched,
but it has not been measured and the claim above is not evidence for it.

Nor is this a full corpus: 40 steps per run against a warm database. The Phase 4 run at the Task 0.4
scale is what would confirm it holds under sustained load.
