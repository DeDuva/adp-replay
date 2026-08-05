# Task 0.4 — power analysis

**170 tasks x 3 repetitions** reaches power 0.806 against a target of 0.8.

That is 1020 recorded trajectories across both models. Task 1.3 audits at least 213 tasks (1.25x) to absorb attrition.

## Assumptions

Every one of these is a guess until pilot data replaces it.

| assumption | value |
|---|---|
| base success rate | 0.45 |
| effect size to detect | 0.1 |
| between-task SD (logit) | 1.5 |
| alpha | 0.05 |

## Design

- Primary outcome: a task counts as solved when a majority of its repetitions pass.
- Test: exact McNemar on the paired per-task outcomes.
- Confidence intervals resample **tasks**, never trajectories.

## Sensitivity

A design that only holds at one assumed effect size is a number, not a result.

| effect size | power |
|---|---|
| 0.05 | 0.282 |
| 0.075 | 0.562 |
| 0.1 | 0.812 |
| 0.125 | 0.935 |
| 0.15 | 0.989 |

| between-task SD | power |
|---|---|
| 0.75 | 0.771 |
| 1.0 | 0.786 |
| 1.5 | 0.812 |
| 2.0 | 0.846 |
| 2.5 | 0.888 |

Power rises with between-task spread rather than falling, which is worth stating
because it reads backwards. Holding the marginal success rate fixed, a wider spread
of task difficulty needs a larger shift on the log-odds scale to move that rate by
the same ten points — and the larger shift produces more discordant pairs, which are
the only pairs McNemar reads. The design is therefore not at risk from a corpus that
turns out more heterogeneous than assumed; it is at risk from a smaller true effect.

## Cheaper designs that were not chosen

These reached the target power for fewer trajectories and were still ruled out.
Task 3.1 commits to reporting ICC and a between/within variance decomposition,
and within-task variance is not defined at a single repetition. A design cannot
be recommended on cost when it cannot support the analysis it exists to feed.

| tasks | repetitions | power | trajectories |
|---|---|---|---|
| 310 | 1 | 0.812 | 620 |
