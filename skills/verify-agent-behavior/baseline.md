# baseline

Establish what the system does **now**, before changing anything.

---

**Do not modify the implementation in this step.** If you have already changed
something, revert it or baseline the unchanged revision. A baseline taken after a change
is not a baseline.

## Run

Run the eval harness against the dimension named in the clause's `verified_by`, on its case set.

**Measure the baseline on both splits now, once**: dev for iteration, held-out for the comparison
at verification. Read only the held-out **aggregate**, never which held-out cases failed.

## If the Method is `model`: validate the judge first

A judge score is only as good as the judge. Before this baseline counts:

1. **Labels (checkpoint C2).** The domain owner labels traces Pass/Fail for the one criterion the
   judge checks — about 100, balanced. Queue it (`checkpoints.md`) and continue other work.
2. **Split the labels — the *judge-calibration* split, not the system split** (`instruments.md`):
   train (few-shot examples) · dev (improve the judge) · test (measure it once).
3. **Measure TPR and TNR on the test labels** — `evals:validate-evaluator`, or by hand. Minimum 0.8
   each; target 0.9.
4. **Compute the numbers with the adapter**, which corrects the observed pass rate for the judge's
   errors and bootstraps an interval over both the cases and the judge labels — with the same code
   the gate uses to check them. Its input needs the judge's labelled items, the baseline's per-case
   verdicts (`baseline_runs`) and the candidate's (`runs`); at baseline time, before any change,
   the two are the same runs:

```bash
uv run <skill>/tools/judge_to_eval_result.py judge-run.yaml --template eval-result-template.yaml --out eval-result.yaml
```

**A judge-calibration test label is never a held-out case.** Keep the two splits apart.

## Pin every version

A score is meaningless without what produced it:

| | |
|---|---|
| model snapshot | |
| prompt version or hash | |
| retrieval index / chunking version | |
| tool versions | |
| `control_policy_version` | |
| **case-set version** and **split** (dev / held-out) | |
| judge prompt version, if model-scored | |
| **judge validation**: TPR / TNR against human labels, label-set version, labeler | |
| **dimension provenance**: `DISC-promoted` or `spec-only` | |

**A baseline missing any of these cannot be compared against later.**

## Establish the noise floor

**Run it at least three times.** Record the spread.

For a model-scored dimension the variance is required, not optional — a threshold of
0.90 against a metric that swings ±0.04 is a coin flip near the boundary.

For a deterministic dimension, state that variance is zero and why.

## Two kinds of uncertainty. Report both.

| | Comes from | Shrinks with |
|---|---|---|
| **Run variance** (noise floor) | model randomness on the same cases | nothing you can fix. Measure it. |
| **Sampling uncertainty** (confidence interval) | how few cases you have | more cases |

**Three tight runs on 24 cases still leave a wide interval.** Report the 95% interval over
cases (Wilson for pass rates) next to the run spread.

**If the judge is an LLM**, correct the raw pass rate for its measured TPR/TNR before
comparing to a threshold. An uncorrected judge score inherits the judge's bias.

## Set the evidence state

The baseline moves the obligation out of `unmeasured`:

| Baseline result | Evidence state |
|---|---|
| Below threshold, or an unacceptable failure fired | **`red`** |
| Threshold inside the confidence interval or noise floor | **`inconclusive`** |
| At or above threshold on **dev** | **still not `green`**. Green is earned on held-out cases at verification. |

## Record

- the score, per case and aggregate — **one record per case per run: `run_id`, `test_case_id`,
  `trace_id`, binary verdict, critique, cited span IDs** (the schema in `verify-before-completion.md`)
- every run in the run ledger, including the ones you don't report — **baseline runs tagged
  `purpose: baseline`**, and their IDs in the result's `baseline.run_ids`
- the variance
- **the outputs and traces**, not just the numbers
- which cases failed

Outputs matter more than the score at this stage: `analyze-failures.md` reads them.

## Report

```
EVAL-D03 conflict recognition            provenance: DISC-promoted (DISC-D02)
baseline: 71% (runs: 69, 71, 73 — noise floor ±2pp)
          95% CI over cases: 51–85%
case set: v4 held-out, n=24, buckets clean/judgment/adversarial/near-miss   (aggregate only; the dev baseline reports per case)
judge:    jp-v3, TPR 0.91 / TNR 0.88 on labels v2 (labeler: domain owner)
failures: 7 (case 04, 07, 11, 13, 18, 19, 22)
evidence_state: unmeasured → red
```

**Never report a baseline without its noise floor and its interval.**
