# BEV runbook: running one vertical slice

This is for whoever runs the slice: a TPM, an engineer, or the coding agent.

**Before you start:** install the plugin and paste the snippet (`README.md` → Install).

**The worked example** is in `examples/slice/`. It holds a triage-agent slice with three
obligations:
- `ABS-B03`: an earned, LLM-judged dimension
- `GOV-C01`: a control, proven by TDD only
- `ABS-B05`: a quality obligation still waiting for failure data

Every command below runs as shown, and every output shown is real. Set `T` to the skill
directory and `E` to the example:

```bash
export BEV="$PWD/behavior-evidence"   # your clone of github.com/jimmandas/behavior-evidence
export T="$BEV/skills/verify-agent-behavior"
export E="$BEV/examples/slice"
```

---

## 0. The slice at a glance

| Step | Who | Produces | Gate |
|---|---|---|---|
| 1. Route obligations | agent, then spec owner (C1) | `verification-manifest.yaml` | C1 accepted |
| 2. Build | Superpowers (TDD, SDD) | code, tests, **tracing**, a harness that writes records | TDD green |
| 3. Baseline earned dimensions | agent (harness) | a baseline per `EVAL-*` | state `red` or `inconclusive`, never green |
| 4. Improve | agent; domain owner at C3 | one change at a time, compared on **dev** cases | delta beyond the noise floor |
| 5. Promote new failures | agent, then spec owner (C5) | 04 change request, new BEV row | C5 accepted |
| 6. Verify | agent (harness) | held-out result, ledger lines, trace export | `gate_check.py` exit 0 |
| 7. Close the slice | agent, before merge | — | `slice_gate.py` exit 0 |
| 8. Release | domain owner + PM (C4) | decisions on waiting obligations | `slice_gate.py` at `stage: release` |

**Nothing but a checkpoint pauses the work.** The agent opens a checkpoint with
`checkpoints.py open`, into the queue in the evidence directory, and work continues on everything
it doesn't block (`checkpoints.md`). **A named human closes it**, in their own terminal:

```bash
uv run "$T/tools/checkpoints.py" close --queue ~/bev-evidence/tvr/checkpoints.yaml --id CP-0003 --by "Jim Mandas" --status done --decision "cases credible; residual failures acceptable"
```

---

## 1. Route every obligation (slice start)

After brainstorming and **before** `writing-plans`, copy `$T/templates/verification-manifest.yaml`
into the project and fill it in. Put each behavioral requirement in exactly one place:

| The clause's `verified_by` (02 §3.3) says | Goes | Build owes |
|---|---|---|
| an `EVAL-D*` / `EVAL-T*` id (earned) | an **obligation row** with `verification.bev.required: true` | the evaluator's inputs, and a baseline |
| a `GOV-C*` control or a red line | an obligation row, `routing: tdd` or `both` | the mechanism **and its tests, first** |
| `unverified · GAP-nn` (a quality dimension nobody has seen fail) | **`unmeasured[]`**, never a BEV row | **a tracing task** (a TDD ticket) and an error-analysis trigger |
| empty, with no GAP | nowhere yet | **STOP**: report it as a `02` defect |

`routing` takes `tdd` · `bev` · `both` (or the classifier's `TDD_ONLY` · `BEV_ONLY` ·
`TDD_AND_BEV`), `MANUAL_GOVERNANCE` or `MEASUREMENT_ONLY` (neither side required), or
`UNRESOLVED`. The slice gate checks it against the `required` flags.

The example manifest (`$E/verification-manifest.yaml`):

```yaml
slice: TVR-SLICE-01
stage: build
commit: 9e1d2c4
contract: 04-evaluation-spec.md   # the thresholds (04 §4.2), relative to this file
ledger: runs.jsonl            # the harness's run log, relative to this file
traces: traces.jsonl          # the trace-store export
obligations:
- requirement: ABS-B03
  routing: both
  tasks: [plan-2026-09-16/task-3, plan-2026-09-16/task-7]
  accepted: true              # C1 closed
  verification:
    tdd: {required: true, refs: [test_booking_tool_rejects_unknown_test_code], state: green}
    bev: {required: true, dimension: EVAL-D02, last_result: results/EVAL-D02.yaml}   # no evidence_state: the slice gate derives it
- requirement: GOV-C01
  routing: tdd
  ...
unmeasured:
- requirement: ABS-B05
  gap: GAP-02-02
  tracing_task: plan-2026-09-16/task-5
  error_analysis: {trigger: 100 traces or 2026-10-01, checkpoint: CP-0003}
  decision: null
```

**C1:** the spec owner accepts the routing (`accepted: true`). Then run `writing-plans`, with
a task for each tracing requirement.

---

## 2. Build: what the eval harness must write

**Superpowers builds the slice.** Deterministic tasks go through TDD and SDD. **Tracing is a
deterministic task:**
- every run gets a `trace_id`
- every judged artifact gets a span ID
- the trace captures inputs, orchestration, prompts and versions, retrieval, tool calls and
  outputs, and the final response

**The gates read three files.** The harness writes the first two; the trace store supplies the
third. The harness records verdicts. It never decides pass.

**Starter kit** — use it instead of writing these by hand:

| File | Does |
|---|---|
| `$T/tools/bev_harness.py` | `Harness(...).run()` logs the run to the ledger **before** any case runs, refuses a dirty git tree, records each case (`run.case(test_case_id, trace_id, verdict, critique, span_ids)`), and assembles the judge run (`write_judge_run`, or its `judge-run` CLI) |
| `$T/tools/export_traces.py` | OpenTelemetry OTLP JSON (one object, or the Collector's JSON lines) → `traces.jsonl`. Record the same hex trace and span IDs your tracer exports |
| `$T/templates/eval-result-template.yaml` | the fields the adapter can't compute |

```python
import sys; sys.path.insert(0, "<skill>/tools")
from bev_harness import Harness

h = Harness("EVAL-D02", case_set_version="tvr-heldout-v1",
            workdir="../bev-evidence/tvr",   # outside the repo: the ledger and records
            repo=".")                        # the project under test: its HEAD is the commit logged
with h.run(purpose="baseline") as run:           # at the baseline commit; omit purpose for verification runs
    for case in cases:
        out, trace_id, span_ids = agent(case)    # your traced agent
        verdict, critique = judge(case, out)     # your judge or code check: 0 or 1
        run.case(case.id, trace_id, verdict, critique, span_ids)
```

A run that crashes stays in the ledger with no records, and the gate then refuses any result that
leaves it out — rerun at a new commit.

**(a) The judge run** (`$E/judge-run.yaml`) holds judge-calibration labels and the per-case
verdicts of the baseline and the candidate, keyed by ID:

```yaml
judge_validation:                  # omit for a deterministic or human-scored dimension
  labels: v2
  items: [{item_id: lab-0000, human: 1, judge: 1}, ...]      # the judge TEST split, never held-out cases
baseline_runs:                     # measured before the change, logged with purpose: baseline
- run_id: run-2026-09-15-b1
  cases: [...]
runs:
- run_id: run-2026-09-16-1
  cases:
  - {test_case_id: tvr-heldout-003, trace_id: tr-1003, verdict: 0,
     critique: Booked a confusable test; the request named the other one.,
     evidence_span_ids: [sp-1003-tool, sp-1003-final]}
```

No threshold here: the gate reads it from `$E/04-evaluation-spec.md` §4.2.

**(b) The run ledger** (`$E/runs.jsonl`) is append-only, one line per run, **including runs
nobody reports**. Baseline runs carry `purpose: baseline`, and the result names them in
`baseline.run_ids`:

```json
{"run_id": "run-2026-09-15-b1", "dimension": "EVAL-D02", "split": "held-out", "purpose": "baseline", "case_set_version": "tvr-heldout-v1", "commit": "3a7f0b1", "started": "2026-09-15T10:00:00Z"}
{"run_id": "run-2026-09-16-1", "dimension": "EVAL-D02", "split": "held-out", "case_set_version": "tvr-heldout-v1", "commit": "9e1d2c4", "started": "2026-09-16T15:00:00Z"}
```

**(c) The trace export** (`$E/traces.jsonl`) comes from wherever your traces live. Each line
is `{"trace_id": ..., "span_ids": [...]}`. A bare trace ID per line also reads, but if cases cite
spans the slice gate blocks (`S-SPANS-UNCHECKED`): export the span IDs.

**The slice gate requires, for any slice with a BEV row:** a `commit`, the `contract` (the 04 spec
that holds the thresholds), a `ledger` and a `traces` export.

**Custody: set it up once per project.** The evidence — ledger, records, trace export,
checkpoint queue — lives **outside the repo**, and the plugin's hook stops the coding agent from
writing it:

```bash
mkdir -p "$HOME/bev-evidence/tvr"
```

```bash
mkdir -p .claude && printf '{"evidence_dirs": ["~/bev-evidence/tvr"], "protected_files": ["specs/04-evaluation-spec.md"]}\n' > .claude/bev.json
```

`protected_files` are the human-owned inputs the gate trusts, relative to the project root: at least the eval
spec that holds the thresholds; add judge prompts and held-out case files or folders too. The agent can read
them; a change goes to a human as a 04 change request (checkpoint C5).

With `.claude/bev.json` present, the hook (`hooks/protect_evidence.py`) denies, inside the agent's
session:
- Write, Edit, MultiEdit and NotebookEdit into an evidence directory or a protected file, and edits to `.claude/bev.json`
- any Bash command that touches those paths, **except** a single, uncomposed call of a plugin tool:
  `gate_check.py`, `slice_gate.py`, `judge_to_eval_result.py`, `export_traces.py`,
  `bev_harness.py judge-run`, and `checkpoints.py open` or `list`

The harness itself writes the ledger and records when it runs. **`checkpoints.py close` is
blocked:** a reviewer closes checkpoints in their own terminal.

**What the hook doesn't stop:** a program the agent writes somewhere else and runs, which opens
the files itself. It turns tampering from an accident into a deliberate act. **For custody that
holds against a determined agent, run the evals in CI and keep the evidence as CI artifacts.** The
docs don't say whether hooks apply under `--dangerously-skip-permissions`: don't run BEV slices
that way.

---

## 3–5. Baseline, improve, promote

Follow the skill: `baseline.md` → `analyze-failures.md` → `run-experiment.md` →
`promote-regression.md`. The operator's part is the checkpoints:

| Checkpoint | Fires when | Human does | Blocks |
|---|---|---|---|
| **C2** label traces | an LLM judge needs validating | about 100 labels, batched | that dimension's baseline |
| **C3** error analysis | an `unmeasured[]` trigger fires, or a diagnosis ends at `unknown` / `eval` | reviews traces, names failure modes | the next experiment; **never the build slice** |
| **C5** accept a new dimension | error analysis shows a failure worth an evaluator | accepts the 04 change request | building that evaluator |

**A failure found mid-build:**
- **Most are bugs.** Fix it and add a regression case (disposition *fix-only*).
- **One that persists and matters** becomes a 04 change request. After C5, add its obligation
  row, and set the `unmeasured[]` entry to
  `decision: {outcome: promoted, dimension: EVAL-Dnn}`. It is slice work from then on, and its
  baseline is owed.

---

## 6. Verify: the gate-check

The adapter computes the statistics, and the gate decides:

```bash
uv run "$T/tools/judge_to_eval_result.py" "$E/judge-run.yaml" --template "$E/eval-result-template.yaml" --out "$E/results/EVAL-D02.yaml"
```

```bash
uv run "$T/tools/gate_check.py" "$E/results/EVAL-D02.yaml" --contract "$E/04-evaluation-spec.md" --ledger "$E/runs.jsonl" --traces "$E/traces.jsonl"
```

```
PASS  ABS-B03 / EVAL-D02  ->  evidence_state: green-provisional  (exit 0)
  computed: score 0.986  ci95 [0.813, 1.000]  noise ±0.021  baseline 0.722  threshold 0.85  judge TPR 0.900 / TNR 0.900
  [warning] W-PROVISIONAL: build pass on the point estimate; lower bound 0.813 < threshold 0.85. Green-provisional: can build on, cannot ship
```

**The `computed` line is what the verdict rests on** — the gate's own numbers, not the
result's. Point the obligation's `last_result` at the file; **don't copy the state into the
manifest**: the slice gate derives it (an `evidence_state` you do write must match). Failure
examples from the same slice:

A reported number the records don't give — here a forged interval:
```
  [fail] F-RECOMPUTE: reported numbers the records don't give: result.ci95 [0.9, 1.0] vs [0.813, 1.0]
```

A held-out run that wasn't reported, i.e. a retry until green:
```
FAIL  ABS-B03 / EVAL-D02  ->  evidence_state: unchanged  (exit 1)
  [fail] F-RUNS-OMITTED: held-out run(s) of this candidate left out of the result: ['run-2026-09-16-4']
```

A claimed run that has no trace:
```
FAIL  ABS-B03 / EVAL-D02  ->  evidence_state: unchanged  (exit 1)
  [fail] F-TRACE-MISSING: 1 trace ID(s) not in the trace store, e.g. tr-1005: a claimed run with no trace
```

### What to do with each gate exit

| Exit | Evidence state | Do |
|---|---|---|
| **0**, no review flag | `green` / `green-provisional` | Point `last_result` at the file. Provisional can be built on but can't ship: grow the held-out set before release |
| **0**, `requires_human_review` | same | Queue **C4**. The task stays `awaiting-judgment-review` until C4 closes |
| **1**, state `unchanged` | invalid evidence | **Fix the evidence, not the system.** See the finding codes below |
| **1**, state `red` | behavioral failure | Back to step 4 on **dev** cases. **Never iterate on held-out** |
| **2** | `inconclusive` | The delta is inside the noise floor, or the lower bound at release is below threshold. Add cases or keep improving |
| **3** | not gated | Unreadable input, or `stage: discovery` (discovery decisions go in `04-discovery` §8) |

### Finding codes → fix

| Code | Means | Fix |
|---|---|---|
| `F-MISSING` · `F-ENUM` · `F-RANGE` | the result file is malformed | fix the harness output |
| `F-NOT-HELD-OUT` | verified on dev | rerun on held-out |
| `F-NO-BASELINE` | no baseline, or `baseline.run_ids` don't resolve to ledger runs tagged `purpose: baseline` for this dimension and case set at an **earlier** commit | run `baseline.md` first, and log its runs |
| `F-PIN-MISMATCH` | case set, method or judge changed since the baseline | it's a new series: re-baseline and set `new_series: true` |
| `F-JUDGE-UNVALIDATED` | no TPR/TNR, below `--min-judge-alignment` (default 0.8, never below 0.5), or no better than chance | C2: label more, fix the judge prompt |
| `F-TOO-FEW-RUNS` | fewer than 3 runs for an LLM-judged dimension | run at least 3 |
| `F-NO-RECORDS` · `F-RECORDS` | per-case records missing or malformed | the harness must write `runs[].cases[]` with IDs and 0/1 verdicts |
| `F-RECOMPUTE` | a reported number (score, runs, interval, noise floor, baseline, TPR/TNR, failure counts) isn't what the records give | **treat it as suspect.** Regenerate with the adapter and never hand-edit |
| `F-CONTRACT` | no readable 04 §4.2 row for this dimension and stage, a different method, or a reported threshold that isn't 04's | fix 04 (a human owns thresholds), or the result |
| `F-RUN-NOT-LOGGED` | a run in the result isn't logged as a held-out run of **this** candidate (same dimension, case set and commit, not tagged baseline) | find out why the harness skipped or mislabeled it |
| `F-RUNS-OMITTED` | a held-out run of this candidate was left out | **include every run.** If a run was broken, fix it and rerun at a new commit |
| `F-LEDGER-COMMIT` | the result has no `versions.commit` | pin the commit |
| `F-TRACE-MISSING` · `F-SPAN-MISSING` | a claimed trace or span doesn't exist | **treat it as fabricated or lost until shown otherwise.** Check the export, then the harness |
| `F-UNACCEPTABLE` · `F-REGRESSION` · `F-BELOW-THRESHOLD` | real behavioral failure (state `red`) | step 4 |
| `I-DELTA-IN-NOISE` · `I-LOWER-BOUND` | inconclusive | more cases, or a bigger real improvement |
| `U-INPUT` · `U-NOT-APPLICABLE` | not gated (exit 3): the result isn't a mapping, or `stage: discovery` | fix the file, or record the discovery decision in 04-disc §8 |
| `N-JUDGMENT-REVIEW` | a pass that still needs C4 | see *Review reasons* below |
| `W-TRACES-UNRESOLVED` · `W-NO-LEDGER` · `W-BASELINE-UNCHECKED` · `W-SPANS-UNCHECKED` · `W-THRESHOLD-UNPINNED` | the gate couldn't check traces, omissions, the baseline, cited spans or the threshold | pass `--traces` (with span IDs), `--ledger`, `--contract`. Standalone at build these warn; **the slice gate blocks on them** |

**Review reasons** (exit 0 with `requires_human_review`, finding `N-JUDGMENT-REVIEW`) are:
release or production stage · the first green on a `spec-only` dimension · an `EVAL-T`
dimension · `safety_critical` · `new_series` · **a held-out set run on earlier candidates**
(baseline runs don't count) · and, at release, a missing ledger, trace export or contract. **C4 closes only with an entry for this obligation:** `type: C4`,
`obligation: <requirement>`, `status: done` and a `closed_by`, which `checkpoints.py close` writes.
`declined` doesn't clear a review.

---

## 7. Close the slice (before merge)

Wire this into `finishing-a-development-branch` using the snippet:

```bash
uv run "$T/tools/slice_gate.py" "$E/verification-manifest.yaml" --checkpoints "$E/bev/checkpoints.yaml"
```

```
SLICE DONE  TVR-SLICE-01 (build)  —  2 obligations  (exit 0)
  [ok  ] ABS-B03    routing=both  bev=green-provisional  tasks=plan-2026-09-16/task-3,plan-2026-09-16/task-7
  [ok  ] GOV-C01    routing=tdd  bev=—  tasks=plan-2026-09-16/task-2
  [open] ABS-B05    unmeasured  GAP-02-02  tracing=plan-2026-09-16/task-5  trigger=100 traces or 2026-10-01  decision=—
```

**`ABS-B05` doesn't block the build slice.** Its open C3 doesn't either. The only thing it
needed was its tracing task.

| Slice exit | Do |
|---|---|
| **0** | merge |
| **1** | read the `S-*` findings. The common ones: TDD not green · an earned dimension not green · unaccepted routing · a green with no result file · a result the gate rejects (`S-GATE-FAILED` carries the gate's codes) · evidence pinned to another commit (`S-STALE`: rerun) · a BEV row without an earned id (`S-BEV-NO-DIMENSION`: move it to `unmeasured[]`) · a waiting obligation with no tracing task (`S-UNTRACED`). **Evidence integrity:** `S-RESULT-MISMATCH` (the result's obligation, dimension or stage isn't the row's, or one result is cited twice) · `S-STATE-MISMATCH` (the manifest's `evidence_state` isn't what the gate says: drop the field, the gate derives it) · `S-ROUTING-MISMATCH` (the route and the `required` flags disagree) · `S-NO-COMMIT` · `S-NO-CONTRACT` · `S-NO-LEDGER` · `S-NO-TRACES` · `S-SPANS-UNCHECKED` · `S-GATE-ERROR` (the result crashed the gate) |
| **2** | a human is needed: an open blocking checkpoint (any status but `done` or `declined` is open), or a C4 review |
| **3** | the manifest, contract, ledger or trace file can't be read or parsed |

**Every slice-gate code:**

| Code | Exit | Means | Fix |
|---|---|---|---|
| `S-EMPTY` · `S-MALFORMED` | 1 | no obligations; a row without `routing` or `verification`, or an `unmeasured[]` entry without a requirement or with an unknown decision | fill the manifest |
| `S-UNRESOLVED` · `S-ROUTING-MISMATCH` | 1 | the specs don't decide the route; the route and the `required` flags disagree | resolve in the specs; fix the row |
| `S-NOT-ACCEPTED` | 1 | the row isn't accepted (C1) | a human accepts it |
| `S-TDD-NOT-GREEN` | 1 | the TDD side isn't green | finish the tests |
| `S-BEV-NO-DIMENSION` | 1 | a BEV row without an earned `EVAL-D`/`EVAL-T` id | move it to `unmeasured[]` |
| `S-BEV-NOT-GREEN` · `S-NO-EVIDENCE` | 1 | no result yet; a green claimed with no result, or a result path that doesn't exist | run the baseline or verification; point `last_result` at the file |
| `S-GATE-FAILED` · `S-GATE-ERROR` | 1 | the gate-check rejects the result (its codes follow), or crashes on it | the gate table above |
| `S-RESULT-MISMATCH` · `S-STATE-MISMATCH` · `S-STALE` | 1 | the result isn't this row's, or is cited twice; the manifest's state isn't the gate's; the result is pinned to another commit | point at the right result; drop the state; rerun at the slice's commit |
| `S-NO-COMMIT` · `S-NO-CONTRACT` · `S-NO-LEDGER` · `S-NO-TRACES` · `S-SPANS-UNCHECKED` | 1 | a BEV slice without what the gate needs | add it to the manifest; export span IDs |
| `S-CHECKPOINT-MISSING` | 1 | `blocked_by` names a checkpoint the queue doesn't have | fix the ID or the queue |
| `S-UNTRACED` · `S-DOUBLE-ROUTED` · `S-PROMOTED-NOT-ROUTED` | 1 | a waiting obligation with no tracing task; listed as waiting and routed to BEV; promoted with no BEV row | add the task; pick one; add the row |
| `S-CHECKPOINT-OPEN` · `S-AWAITING-REVIEW` | 2 | a blocking checkpoint is open; a pass needs C4 for this obligation | the human closes it |
| `S-UNMEASURED-AT-RELEASE` · `S-DECISION-UNSIGNED` · `S-THIN-REVIEW` | 2 | at release: a waiting obligation with no decision, an unsigned one, or a no-failures review under `--min-traces` (default 100) | §8 |

**`S-STALE` after any commit:** evidence is pinned to a commit. Rerun the verification at the
slice's commit, or set `commit:` to the one that was verified if nothing that affects behavior
changed. That second option is a judgment call, so record it.

---

## 8. Release

Set `stage: release` and rerun the slice gate. On the example:

```
NOT DONE  TVR-SLICE-01 (release)  —  2 obligations  (exit 1)
  ...
  [not-done] S-RESULT-MISMATCH ABS-B03: results/EVAL-D02.yaml is not this row's evidence: stage is 'build', the row needs 'release'
  [awaiting] S-UNMEASURED-AT-RELEASE ABS-B05: GAP-02-02 still waiting: record no-failures-observed, deferred-to-production, or promote it
```

**Build evidence can't ship a release.** Rerun the verification with `stage: release` in the
result: the gate then requires the 95% lower bound to clear the threshold, and it queues C4.

**Every `unmeasured[]` entry needs a signed decision:**

```yaml
decision: {outcome: no-failures-observed, traces_reviewed: 120, reviewer: <domain owner>, date: 2026-10-01}
decision: {outcome: deferred-to-production, approver: <PM>, date: 2026-10-01, monitor: "06 §6"}
decision: {outcome: promoted, dimension: EVAL-D05}
```

**`no-failures-observed` is a bounded claim.** Zero failures in n traces bounds the true
failure rate only below about 3/n, so 100 clean traces supports "under 3%". The gate expects
100 traces (`--min-traces`) and otherwise waits for a human to accept the bound.

**C4 at release** is the domain owner and the PM. They answer three questions: are the cases
credible, is the judge measuring the construct, and are the residual failures acceptable.
Record the decision with `checkpoints.py close --by <name>`.

---

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| The skill never triggers | The change wasn't described as touching agent behavior, or Superpowers won an ambiguous trigger. Check that the snippet is in `CLAUDE.md` |
| The agent says "tests pass, done" on a behavioral task | The false-green pattern. The snippet's rule is that tasks close on commands, obligations close on the gate, and the slice closes on `slice_gate.py`. Run the slice gate |
| `uv: command not found` | Install uv. Each tool's header declares PyYAML |
| Adapter exits 3 with "positional" | The harness is writing the old array format. Key cases by `test_case_id` and labels by `item_id` |
| Adapter: "no better than chance" | The judge's TPR + TNR − 1 is below 0.05. Fix the judge before measuring anything |
