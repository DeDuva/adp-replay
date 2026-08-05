# Closure audit (Task 1.3)

A task is **closed** when running it twice, on two machines, at two different times, can differ only
because the model differed. Three things break that, and the audit flags all three: **network use**,
**background-process dependence**, and **clock dependence**.

```sh
adp-replay audit path/to/tasks --target-tasks 170 --out tb2_closed_corpus.json
```

The target comes from `adp-replay power` (Task 0.4), never from a number typed here.

## Status: the corpus has not been built

**`tb2_closed_corpus.json` does not exist yet, and Task 1.3's done-condition is not met.**

The auditor is implemented and tested. What is missing is the thing to audit: the Terminal Bench task
corpus is not available in the environment this was built in, and `terminal-bench` could not be
installed. Nothing here fakes its way around that. `build_corpus` refuses to write a corpus that
claims to be usable while falling short of the target, so the gap cannot be papered over by running
the tool against a handful of directories.

To finish the task: point `adp-replay audit` at a real Terminal Bench checkout with
`--target-tasks 170`. It needs **213 audited tasks** (1.25×) to have a good chance of leaving 170
closed ones.

## When the hazard fires is the whole policy

The distinction that makes this audit useful rather than a machine for rejecting everything is
*when* a hazard fires.

**Network at build time is acceptable.** The environment is pinned by image digest
(`EnvironmentSpec.image_digest`), so whatever `apt-get` fetched is already inside the artifact every
replay starts from. **Network at run time is not**: it puts a third party's availability and current
state inside the measurement, and a replay six weeks later gets a different internet.

**A clock read in a test blocks; a clock read in a solution does not.** A solution that looks at the
clock produces a different trajectory, which is a thing the experiment measures. A test that looks at
the clock produces a different *verdict for the same trajectory*, which is the thing that makes a
result uninterpretable.

| hazard | build | solution | test | other run-time |
|---|---|---|---|---|
| network | advisory | **blocking** | **blocking** | **blocking** |
| background process | advisory | **blocking** | **blocking** | **blocking** |
| clock | advisory | advisory | **blocking** | advisory |

Advisory findings are reported, never suppressed. A corpus with a hundred advisory clock reads in its
solutions is telling you something even though every task passes.

## A flagged task is not a broken task

It is a task *this experiment* cannot interpret. Terminal Bench tasks that install packages at run
time or poll a service are perfectly good tasks; they just cannot carry a claim about which of two
models is better, because the difference between two runs might be the mirror or the timing.

The 1.25× audit ratio exists precisely because a meaningful fraction of any real corpus will fail
this and has to be replaced. If attrition comes in far above 20%, the honest response is to audit
more tasks, not to loosen the policy — the numbers in the table above are what make the eventual
result mean anything.

## Not becoming noise

Two deliberate restraints, because an audit that over-matches gets ignored, and an ignored audit is
worse than none — it makes the corpus look examined.

- **Commented-out lines are skipped.** Flagging a commented-out `curl` trains people to ignore the
  tool.
- **`localhost` and loopback URLs are not network use.** A task that talks to something it started
  inside its own container is closed, and rejecting that would discard a large, legitimate class of
  task.

Every finding carries the file, the line, the matched text, the pattern that matched it, and why it
matters — enough to check by hand and disagree with.

## What the corpus file records

Both halves. The failing tasks are in `tb2_closed_corpus.json` alongside the passing ones, with their
findings, because a corpus file that listed only what survived would hide its own selection. The
interesting question about a closed corpus is always what had to be thrown away, and why.
