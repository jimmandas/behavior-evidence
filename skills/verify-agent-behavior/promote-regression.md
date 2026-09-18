# promote-regression

Turn a discovered failure into permanent coverage. **This is how the eval corpus
accumulates behavioral knowledge, the way a test suite accumulates bug knowledge.**

---

## What qualifies

| Source | Classification needed? |
|---|---|
| A failure found during development or adversarial work | **No** — the case that found it is already labelled |
| **A production failure** | **Yes** — it arrives unlabelled |

## Classify first, for production failures

**This is the step that gets skipped**, and skipping it means the suite collects
incidents rather than cases. Without a taxonomy you accumulate one-offs and the suite
grows without getting better.

State the failure class before writing the case.

## Reproduce before promoting

A failure you cannot reproduce is not a case. If it only fails intermittently, that is
itself the finding — record the rate.

## Write the case

| | |
|---|---|
| What it exercises | |
| Expected behavior | |
| Bucket | `clean · judgment-intensive · adversarial · regression · production-derived` |
| **Provenance** | where it came from |
| Link back | the failure cluster or incident that produced it |
| **Labeler** | who set the expected behavior, and who adjudicated it if reviewers disagreed |
| **Split** | **dev / regression**. Never the held-out set. |

**Promoted cases join dev and regression, never held-out.** You've seen them and fixed
against them, so they can't give an unbiased verification. Refresh held-out separately, from
cases nobody has iterated against.

**Provenance matters**: without it nobody can tell whether the suite is getting better or
just bigger.

## Bump the case-set version

Adding cases changes the case set. **Every earlier score was measured against a different
set** — record the discontinuity rather than comparing across it.

## Rerun the regression set

Confirm the new case fails on the unfixed system and passes on the fixed one. **A
promoted case that passes before the fix proves nothing** — it is the eval equivalent of
a test that never failed.

## The behavioral regression test: TDD for an observed failure

**A pass rate can't go red → green. An observed failure can.** This is where probabilistic behavior
joins the TDD cycle — and because the red comes from a real failure, it doesn't write an evaluator for
an imagined one.

The harness is deterministic; the subject is not. So every case runs **k** times:

| Step | Rule | Default |
|---|---|---|
| **Red — watch it fail** | run the observed failing case on the **unfixed** system `k_red` times; it must fail at least once | `k_red = 10` |
| **Can't reproduce?** | 0 failures in `k_red` runs: not a regression case yet. Record the observed rate from the original trace as a finding, and widen the case (more variants) before promoting | — |
| **Fix** | one change (`run-experiment.md`), handed to TDD if deterministic | — |
| **Green** | on the fixed system, the case passes **m of k** runs | red lines, controls, RAI hard constraints: **k = 10, m = 10** · quality: **k = 5, m = 5** |
| **Commit** | the case, its `k`/`m`, its provenance and labeler, pinned model and prompt versions | — |

**What k-of-n can and can't prove.** It is a **tripwire, not a measurement**:

| Consecutive passes | 95% upper bound on the true failure rate |
|---|---|
| 5 of 5 | 45% |
| 10 of 10 | 26% |
| 30 of 30 | 10% |
| 60 of 60 | 5% |

A case that fails 20% of the time still passes 5 of 5 a third of the time. **The regression test
catches a failure coming back; the dimension gate (`verify-before-completion.md`) measures the rate.**
Both are needed; neither replaces the other.

### Flakiness policy

- **Never retry until it passes.** A retry loop turns a real intermittent failure into a green test.
- **Below `m` of `k` is a regression, not "flaky."** It counts in `regressions` for the dimension's
  gate-check, and the obligation goes `red`.
- **Quarantine only as a recorded decision** — a C4 checkpoint with a reason and an expiry date. A
  quarantined case still runs and still reports; it just doesn't block.
- **Keep the pass history** per case (runs, passes, versions). A case drifting from 10/10 to 8/10
  across versions is an early signal before it crosses `m`.
- **Pinned versions change → every behavioral regression test reruns.** Model, prompt, retrieval or
  judge changed means the old greens are `stale`.

### Where they run

Behavioral regression tests cost `k` model calls each. Run the cases touching the changed layer on
every change, and the full set nightly and before verification. **They sit alongside the
deterministic suite, and a ticket carrying them is red until they pass their k-of-n rule** — together
with its deterministic tests and, where a dimension is warranted, its gate-check.
