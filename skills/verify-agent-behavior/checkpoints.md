# checkpoints

**"Needs a human" does not mean "the agent stops."** Five named checkpoints are the only reasons
BEV pauses work. Each is queued; everything not blocked by it continues.

---

## The five checkpoints

| # | Checkpoint | Fires when | Human | Blocks | Typical effort |
|---|---|---|---|---|---|
| **C1** | Accept manifest DERIVE rows | once per slice, after the manifest is built and before `writing-plans` | spec owner | planning the affected obligations | 15–30 min |
| **C2** | Label traces to validate a judge | a model-scored dimension needs an evaluator (`derive-evals.md`) | domain owner | that dimension's baseline | 1–3 h, batched |
| **C3** | Error-discovery session | Discover mode: always · Diagnose mode: only when the agent's own analysis ends at `unknown` or `eval` · an `unmeasured[]` trigger, whose closing backs a *no failures observed* release decision | domain owner | that dimension's next experiment | 30–60 min |
| **C4** | Judgment review | the gate-check passes with `requires_human_review: true` — release/production, a spec-only dimension's first green, a safety-critical dimension, the first green of a new series · a *deferred to production* release decision on an `unmeasured[]` entry | domain owner + PM | marking that task complete | 20–40 min |
| **C5** | Accept a new dimension or evaluator | a `04` change request from `uncovered` notes, or a proposal to build an evaluator (`analyze-failures.md` disposition *evaluator*) | spec owner | building that evaluator | 10–20 min |

Efforts are estimates, not measurements. Record the actual minutes (below) so they become one.

**Nothing else pauses the loop.** Implementation through `subagent-driven-development`, eval runs,
comparisons, the gate-check, fix-only failures, and regression promotion all run unattended.

## The queue

The queue is `checkpoints.yaml` in the **evidence directory**, outside the repo, next to the
ledger. The agent opens entries with `tools/checkpoints.py open`; **a named human closes them**
with `checkpoints.py close --by <name> --status done|declined --decision "…"`, in their own
terminal. The custody hook blocks `close` from the agent's session. An entry looks like this:

```yaml
- id: CP-0007
  type: C3                         # C1–C5
  obligation: ABS-B07
  dimension: EVAL-D03
  opened: 2026-09-15T14:02Z
  needed: >
    Diagnose session on 9 failing dev cases (conflict recognition).
    Review app built; run: python3 review/server.py  → http://127.0.0.1:8765
  prepared: [review/traces.jsonl, review/error_discovery_data/patterns.json]   # pre-seeded
  estimate_min: 40
  blocks: [task-12, task-13]
  status: open                     # open | done | declined — anything else counts as open
  closed: null
  closed_by: null                  # written by `checkpoints.py close --by`; a C4 without it clears nothing
  actual_min: null
  decision: null                   # what the human decided, in one line
```

**The manifest points at open checkpoints** through each obligation's `blocked_by: [CP-0007]`, which
is what the slice gate reads. A C3 queued by an `unmeasured[]` trigger is referenced from that entry's
`error_analysis.checkpoint` instead, and **never blocks the build slice**.

**A C4 entry names its obligation** (`obligation: ABS-B07`), and it clears that obligation's review
only at `status: done`. A C4 closed for another obligation, or `declined`, clears nothing.

**Rules:**
1. **Open, prepare, continue.** Write the entry with everything the human needs already prepared —
   sample, pre-seeded taxonomy, review app, the exact question — then move to the next task that the
   entry does not block.
2. **Order the queue by what it unblocks.** Most blocked tasks first; ties by oldest. One sitting
   should clear several entries.
3. **Suggest, then confirm.** Where the instrument supports it (`error-discovery` suggestions), the
   agent pre-marks candidate instances; the human accepts or dismisses. Humans label only
   judgment-intensive and near-miss cases — code checks cover the rest.
4. **Resume from the record.** On resume, read closed entries and the files they name
   (`annotations.json`, labels, review decisions) before continuing the blocked tasks.
5. **A `declined` checkpoint is a decision.** Record why; the blocked obligation stays at its current
   evidence state, and the manifest shows it.

## What the checkpoint record is for

**Human minutes go to judgment, arithmetic goes to the gate-check, and every judgment is on record**
— who decided, what, when, against which evidence. That record is the audit trail a governed
workflow needs, and `actual_min` is how you learn what the method really costs.
