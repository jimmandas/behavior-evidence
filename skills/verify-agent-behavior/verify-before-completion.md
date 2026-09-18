# verify-before-completion

**The gate.** Extends Superpowers' `verification-before-completion` for behavioral
claims.

---

```
NO BEHAVIORAL COMPLETION CLAIM WITHOUT FRESH EVALUATION EVIDENCE
```

If you have not run the eval in this session, you cannot claim the behavior holds.

## Run on held-out cases, once

Verification runs the **held-out** split: cases nobody iterated against. Dev success
qualifies a candidate for verification. **It never makes an obligation green.**

## The checks

- [ ] A baseline exists. The evidence state was **not** `unmeasured` before this run
- [ ] The required eval was **executed**, not referenced
- [ ] Run on the **held-out** split, which was not used to choose any change
- [ ] Case-set version and method recorded, and **the same as the baseline's**
- [ ] Threshold met, **judged by the stage rule below**
- [ ] **Variance reported** for any model-scored dimension, **and** the 95% confidence interval over cases
- [ ] For a model-scored dimension, the judge has **recorded TPR/TNR** against human labels, and the pass rate is corrected for them
- [ ] Delta **exceeds the noise floor** — not `inconclusive`
- [ ] No previously-passing case now fails
- [ ] **No unacceptable failure fired** — `EVAL-T*` at zero
- [ ] Discovered failures promoted
- [ ] **The gate-check exited `0`**, and its result file is attached
- [ ] Judgment review done where the stage or risk requires it (below)

**Cannot check every box? The behavior is not verified.** Report actual status with
evidence.

## The stage rule for "threshold met"

| Stage | Threshold met means | If only the point estimate clears it |
|---|---|---|
| **discovery** | Not a threshold gate. The hypothesis is credible or falsified, and the decision is recorded. | — |
| **build** | Point estimate ≥ threshold, **with its CI reported** | **`green-provisional`** if the lower bound is below threshold. Fine for build; it can't ship. |
| **release · production** | **95% lower bound ≥ threshold**, or the threshold is itself declared as a lower bound in `04` | **`inconclusive`**. Grow the held-out set or keep improving. |

**91% on 24 cases has a 95% lower bound of 74%.** A threshold only means something alongside
the case count behind it.

## Claims and what they require

| Claim | Requires | Not sufficient |
|---|---|---|
| Behavior improved | delta > noise floor, same case set and method | the score went up |
| Requirement met | **TDD green *and* BEV green**, where both are routed | structural tests passing |
| Eval passes | threshold met by the stage rule **with variance and CI reported**, on held-out cases | a single run; a dev-set score |
| No regression | previously-passing cases re-run, **behavioral regression tests at m of k** | new cases passing; a retry that eventually passed |
| Observed failure fixed | the case failed on the unfixed system (≥1 of `k_red`), then passes **m of k** on the fixed one (`promote-regression.md`) | it passed once after the fix |
| Behavior is fine | fresh eval evidence | *"tests pass"* |
| **Green** | a baseline, then a held-out run that passes the gate-check | a green with no prior baseline, which is **unfounded** |
| **Not yet measured** | nothing. Say `unmeasured` | calling it red, or leaving it blank |

## The rule that closes the false GREEN

> **A task carrying a BEV obligation cannot be marked complete on TDD green alone.**

Deterministic tests prove the mechanism works. They say nothing about whether the model
behaves. Both, or neither.

## The gate-check: the agent doesn't certify itself

**The eval harness writes a machine-readable result. A deterministic checker reads it and
exits `0` or non-zero.** The exit code is the evidence Superpowers' `verification-before-
completion` already accepts: command output. An agent saying "the eval looks good" is not
evidence.

```bash
uv run <skill>/tools/gate_check.py eval-result.yaml          # human-readable verdict
uv run <skill>/tools/gate_check.py eval-result.yaml --json   # machine-readable verdict
uv run <skill>/tools/gate_check.py eval-result.yaml --contract 04-evaluation-spec.md --ledger runs.jsonl --traces traces.jsonl
```

**The gate computes every number itself; the result's numbers are only checked.** From the
per-case records of the candidate (`runs[]`) and the baseline (`baseline.records[]`), and, when
model-scored, the judge's labelled items, it derives the judge's TPR/TNR, each run's rate
(judge-corrected for `model`), the score, the noise floor, the 95% interval, the baseline
score, the regressions and the unacceptable failures (`tools/evidence_stats.py`, the same code
the adapter uses). A reported number that disagrees is invalid evidence (`F-RECOMPUTE`); the
verdict never uses it.
- **`--contract`** — the threshold and method are read from 04 §4.2 for this dimension and
  stage. Without it the gate uses `result.threshold` and warns (`W-THRESHOLD-UNPINNED`).
- **`--ledger`** — the harness's append-only run log: the baseline and every verification run
  were logged, and none was left out.
- **`--traces`** — a trace-store export: every claimed trace exists and every cited span
  belongs to it.

**Derived, not reported:**
- **Regressions** are cases that passed in every baseline run and now pass in fewer than
  half the runs.
- **Unacceptable failures** are cases whose records list `red_lines`, plus, on an `EVAL-T`
  dimension, any case with a failing verdict.
- **The interval** is a 95% percentile bootstrap (2,000 draws, fixed seed) over the cases, and
  over the judge labels when model-scored. The result can't change the draw count or seed.

```yaml
# eval-result.yaml — written by the harness, never by hand
obligation: ABS-B07
dimension: EVAL-D03
provenance: DISC-promoted            # DISC-promoted | spec-only | build-observed | production-derived
stage: build                          # build | release | production   (discovery is not gated)
split: held-out
method: model                         # deterministic | model | human   (04 §4.2 Method column)
case_set: {version: v4-heldout, n: 60}
versions: {model: ..., prompt: ..., retrieval: ..., tools: ..., control_policy: ..., judge: jp-v3, commit: abc123}   # commit pins the evidence to a code state
judge_validation:                     # required when method = model; the gate recomputes TPR/TNR from items
  labels: v2
  items: [{item_id: lab-0001, human: 1, judge: 1}, ...]   # the judge-calibration TEST split
  tpr: 0.91                           # reported (checked)
  tnr: 0.88
baseline:                             # the SAME held-out set, measured before any change
  case_set_version: v4-heldout
  method: model
  judge: jp-v3
  records: [...]                      # required: per-case records of the baseline runs, same shape as runs[]
  run_ids: [base-0917, ...]           # reported (checked): must be logged with purpose: baseline
  score: 0.71                         # reported (checked)
  runs: [0.69, 0.71, 0.73]            # reported (checked)
result:                               # every field reported (checked); the gate computes its own
  score: 0.92                         # judge-corrected
  runs: [0.91, 0.92, 0.93]
  noise_floor: 0.02
  ci95: [0.82, 0.96]
  threshold: 0.90                     # only used without --contract; with it, must equal 04 §4.2
unacceptable_failures: 0              # reported (checked)
regressions: 0                        # reported (checked)
evidence_state_before: red
safety_critical: false               # optional; true requires judgment review (C4)
new_series: false                    # optional; true on the first green after a case-set, method or judge change
runs:                                # one record per case per run; result.runs and score are recomputed from these
  - run_id: run-8421                 # must be in the run ledger
    cases:
      - test_case_id: pa-eligibility-014
        trace_id: trace-71ab         # must resolve in the trace store
        verdict: 0                   # binary; the rate is over verdicts, never a per-case score
        critique: Two claims were not supported by retrieved evidence.
        evidence_span_ids: [span-18, span-24]   # must belong to that trace
        red_lines: []                # optional: red lines this case tripped (any entry is an unacceptable failure)
```

```jsonl
# runs.jsonl — the run ledger: the harness appends one line per run, including runs nobody reports
{"run_id": "base-0917", "dimension": "EVAL-D03", "split": "held-out", "purpose": "baseline", "case_set_version": "v4-heldout", "commit": "9f00e1a"}
{"run_id": "run-8421", "dimension": "EVAL-D03", "split": "held-out", "case_set_version": "v4-heldout", "commit": "abc123"}
```

**`baseline.run_ids`** names the baseline's ledger runs (`purpose: baseline`, same dimension and
case set, an earlier commit). Without them the gate has only the result's word that a baseline
was run.

**The baseline is on the held-out set too.** Measure it once, before any change, looking only
at the aggregate, never at which held-out cases failed. Iteration then happens on dev.

**The checker's rules are mechanical.** Checks run in this order, and the first category
that fires decides the exit code.

| Exit | Verdict | Evidence state after | Fires when |
|---|---|---|---|
| **3** | not gated | unchanged | Input can't be read or parsed, it isn't a mapping, or `stage: discovery` (record the decision in `04-discovery` §8 instead) |
| **1** | **invalid evidence** | **unchanged** | A required field is missing. An enum value is unknown. Split isn't `held-out`. `evidence_state_before: unmeasured` (no baseline), or, with a ledger, `baseline.run_ids` that don't resolve to baseline runs at an earlier commit. A **measurement pin** differs from the baseline (case-set version, method, and judge when model-scored). **The contract** (with `--contract`): no readable 04 §4.2 row for this dimension and stage, a method that differs from it, or a reported threshold that differs from it (`F-CONTRACT`). A model-scored dimension lacks judge items, or its TPR or TNR (computed from them) is below `--min-judge-alignment` (default 0.8; values under 0.5 are raised to 0.5), or TPR + TNR − 1 < 0.05, or has fewer than 3 runs. `unacceptable_failures` or `regressions` isn't a non-negative integer. **Records:** `runs[]` or `baseline.records[]` missing; a case without `test_case_id`, `trace_id` or a 0/1 verdict; duplicate run or case IDs; runs over different cases; a baseline over different cases; a case count other than `case_set.n`. **Any reported number the records don't give** (`F-RECOMPUTE`): score, run rates, noise floor, interval, baseline score or runs, baseline run IDs, TPR/TNR, failure counts. **Ledger:** a run not logged as a held-out run of this candidate (dimension, case set, commit, not `purpose: baseline`); a held-out run of the same candidate (dimension, case-set version, commit) left out; no `versions.commit`. **Traces:** a trace ID the store doesn't have, or a cited span not in its trace. |
| **1** | **behavioral failure** | **red** | On the gate's own numbers: an unacceptable failure, a regression, or the score below threshold |
| **2** | inconclusive | inconclusive | The baseline was below threshold and the delta is within `noise_floor`. **Or** stage is release/production and the 95% lower bound is below threshold. |
| **0** | pass | **green-provisional** at build if the lower bound is below threshold (warning); otherwise **green** | Everything else. |

**A pass is not always "done".** On exit `0`, the JSON verdict carries `requires_human_review`
and `review_reasons`. It is `true` when any of these hold:
- stage is release or production
- it is the first green on a `spec-only` dimension
- the dimension is an `EVAL-T` (unacceptable-failure) dimension
- the result file sets `safety_critical: true`
- the result file sets `new_series: true` (first green after a case-set, method or judge change)
- the ledger shows the same held-out set run on earlier candidates, baseline runs excepted (it may have been used to choose a change)
- at release or production, no `--ledger`, `--traces` or `--contract` was given (at build these are warnings from this tool; the slice gate blocks on them)

**When it's true, the task is `awaiting-judgment-review`**: queue checkpoint C4 (`checkpoints.md`) and
don't mark it complete until a C4 entry for this obligation reads `status: done`.

**Don't hand-write the statistics.** `tools/judge_to_eval_result.py` takes the harness's
per-case verdicts for the baseline and the candidate (plus the judge's labelled items when
model-scored), computes every number with the gate's own code, and merges them and the records
into the result template (`baseline.md`). It works for deterministic and human-scored
dimensions too: leave out `judge_validation`.

**Only measurement pins must match the baseline.** System versions (model, prompt, retrieval,
tools, control policy) are expected to differ, because that difference *is* the candidate.
They're recorded for provenance.

**A baseline that already meets the threshold needs no delta.** The claim is "still holds",
backed by zero regressions. The noise-floor rule applies only to a claim that the threshold
was *crossed*.

**Invalid evidence never turns anything red.** A bad result file says nothing about the
system, so the state stays where it was until valid evidence exists.

## One obligation is not a slice

This gate answers one obligation. **The slice is answered by `tools/slice_gate.py`**, which reads the
verification manifest: every obligation verified on every required side, no open blocking checkpoint,
and evidence pinned to the current commit. Wire it into `finishing-a-development-branch` so a branch
can't merge on tests alone.

**Waiting obligations don't block a build slice.** A quality obligation with no earned evaluator sits
on the manifest's `unmeasured[]` list. At build the gate checks only that it has a tracing task. At
release each entry needs a signed decision: *no failures observed* (reviewer, and enough traces — 0 in
n bounds the rate only below 3/n), *deferred to production* (approver), or *promoted* (the BEV row
exists). **A signature is a closed checkpoint, not a name in the manifest:** the decision cites a C3
(no failures observed) or C4 (deferred) for that obligation, closed `done` by the same person with
`checkpoints.py close --by`. The agent can write the manifest; it can't close a checkpoint.

## Mechanical check vs. judgment review

| | Who | What |
|---|---|---|
| **Mechanical** | the gate-check | Fields present, splits clean, versions pinned, every number recomputed from the records, the threshold read from 04. **Automate all of it.** |
| **Judgment** | a human: the domain owner for cases and labels, the PM for the threshold | Are the cases credible and representative? Is the judge measuring the construct? Are the remaining failures acceptable? |

**Judgment review is required** at release, for any safety-critical or unacceptable-failure
dimension, for a `spec-only` dimension's first green, and after a case-set or judge change.
**It is not required** for routine reruns that the gate-check passes. Human attention goes
to judgment, not arithmetic.

## Report the evidence, not the conclusion

```
ABS-B07
  tdd: passed   — CONTRACT-021, INT-034
  bev: passed   — EVAL-D03, run 2026-09-02-04, held-out v4 (n=60)
                  92% (CI 82–96%) vs 71% baseline, noise floor ±2pp
                  judge jp-v3 TPR 0.91 / TNR 0.88
                  0 unacceptable failures, 0 regressions
                  gate-check: exit 0 (provisional at build: lower bound < 0.90)
  evidence_state: red → green-provisional
  overall: verified for build · not releasable
```

**"Should be fine now", "looks better", "obviously improved" are not evidence.** Run it.
