# Pre-registration

Fixed commitments, recorded before the code that measures against them exists. An entry here is
amended only by adding a dated amendment below it — never by editing the original.

Referenced by `src/adp_replay/context/fidelity.py` and execution-plan Task 0.3a.

---

## Context fidelity (Gate G0)

**Status: not yet registered.** Task 0.3a fills this in *before* Task 0.3b writes any scoring code.

Required entries:

- Canonical context form, and the transform table per provider pair.
- The fidelity score's definition: what counts as preserved, transformed, and lost, and how they
  combine into a single number.
- The distribution the threshold is read against, and the unit it is aggregated over.
- The G0 pass mark (planned: median ≥ 0.85) and what "an accepted narrowing of provider scope"
  means concretely — which pairs may be dropped, and who decides.
- Date and commit at registration.

## Experiment design (Task 0.4)

**Status: not yet registered.** Filled in when the power analysis reports.

Required entries:

- Target effect size and assumed variance, with their justification.
- The recommended (T tasks, n repetitions) and the achieved power.
- The primary outcome and the test applied to it (exact McNemar), fixed before data collection.
- The resampling unit for confidence intervals: **tasks**, never trajectories.

## Amendments

None.
