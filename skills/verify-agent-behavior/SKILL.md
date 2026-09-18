---
name: verify-agent-behavior
description: Use when starting a vertical slice of an agentic workflow (after brainstorming, before writing-plans), or when changing anything that affects agent behavior — prompts, retrieval, orchestration, model or judge config — or when implementing a behavioral requirement (ABS-B*). Also when deterministic tests pass but behavioral quality is unproven, when someone claims a behavior change made things better without measuring, or when an eval score moved and nobody checked the noise floor.
---

# Verify Agent Behavior

## Overview

**Behavior evidence (BEV):** a completion claim about agent behavior needs evidence that
survives an auditor. Superpowers TDD proves deterministic mechanisms. **BEV proves
probabilistic behavior.**
They are peers, and a consequential requirement needs both.

**Core principle:** If you didn't measure before you changed it, you don't know whether
you improved it.

**Violating the letter of the rules is violating the spirit of the rules.**

## What BEV Is Not

**BEV is not eval-driven development — "write the evals before the feature."** Husain and Shankar
argue against that practice (*AI Evals FAQ*, "Should I practice eval-driven development?", 2025):
an LLM system's failure surface can't be anticipated, so evaluators written in advance measure
imagined failures. **They are right, and this plugin agrees.**

| BEV here means | BEV here does not mean |
|---|---|
| **Measure before you change** — a baseline on the running system, then one change, then a comparison | Building evaluators before the system exists |
| **Claim only what the evidence supports** — the gate, the interval, the held-out run | Treating a spec-derived metric as proof |
| **Evaluators for observed failures** — error analysis first, then a judge or code check for what actually recurs | An evaluator for every clause, up front |
| **Evaluators first only where the criterion is crystal clear** — red lines (`EVAL-T`) and controls (`GOV-C`) | Guessing quality thresholds before seeing outputs |

**The obligation is named up front; the evaluator is earned.** A clause says *what* must hold. An
evaluator is built when traces show it failing, or when the criterion is a hard line.

**What gets built before any failure depends on the dimension type** (full table: `derive-evals.md`):

| Dimension type | Build before any failure | Waits for observed failures |
|---|---|---|
| Controls (`GOV-C`) · red lines (`EVAL-T`) | the mechanism or check, with its tests | nothing |
| **Quality** (`EVAL-D`) | named obligation · tracing · test inputs · a **scheduled** error analysis | the evaluator: judge, threshold, labels |
| **RAI: hard constraints** (PII, prohibited inputs, no automated denial, disclosure, regulation) | **controls and red-line tests**. Waiting for failure data means waiting for harm | nothing |
| **RAI: distributional** (fairness, subgroup disparity) | **the measurement plan**: stratification, subgroup sample sizes, telemetry | the scorer and threshold |
| **RAI: human reliance** (automation bias, rubber-stamping) | instrumentation: override rate, time on case, citations opened | thresholds tuned on real use |

**Severity × whether trace review can see it decides.** Severe, or invisible in a single trace → act
before failures. Visible and recoverable → earn the evaluator.

## The Iron Law

```
NO BEHAVIORAL COMPLETION CLAIM WITHOUT A DELTA THAT CLEARS THE NOISE FLOOR
```

A score that moved less than the metric's own variance has not moved.

## Evidence State: Separate From Task Status

Every BEV obligation carries an **evidence state**. It is not the task's lifecycle status
(`extracted · derived · accepted · implemented · verified`). It records what has actually
been measured.

| State | Means |
|---|---|
| **`unmeasured`** | An earned dimension, routed to BEV, no baseline yet. **The honest starting state. It is not red.** A quality obligation with no evaluator yet has no state here at all: it is on the manifest's `unmeasured[]` list, outside the slice |
| **`red`** | A baseline exists and is below threshold, or an unacceptable failure fired |
| **`inconclusive`** | The delta, or the gap to the threshold, is inside the noise floor or the confidence interval |
| **`green-provisional`** | Build-stage pass on held-out cases, but the 95% lower bound is below threshold. **Fine to build on. Can't ship.** |
| **`green`** | The stage gate passed on held-out cases (see `verify-before-completion.md`) |
| **`stale`** | It was green, but the code moved on: the result is pinned to another commit than the slice's. The slice gate reports it. **A change outside the repo** — a hosted model, an index — **doesn't move the commit**; keep those pinned in files the repo tracks, or rerun after changing them |

**Legal transitions:** `unmeasured → red | inconclusive` through a baseline run. Only a held-out verification run moves anything to `green-provisional` or `green`.

**`unmeasured → green` without a recorded baseline is forbidden.** A green that has no baseline behind it is an **unfounded claim**, and it counts as a false green.

## When to Use

**Always, when the change touches:**
- prompts, system instructions, few-shot examples
- retrieval — index, chunking, ranking, `top_k`
- orchestration — step order, routing, handoffs
- model or judge version, temperature, snapshot
- anything implementing an `ABS-B*` clause

**Not for:** schema changes, control mechanisms, tool contracts, state transitions,
idempotency. **Those are TDD.** Superpowers already handles them.

**Both, when a behavioral clause has a control behind it** — TDD proves the mechanism
cannot be violated, BEV proves the model doesn't try. **TDD first:** a passing eval on a
mechanism that was never built means the requirement is held by the model's good
behavior.

**Make it deterministic first.** Before accepting a `BEV_ONLY` route, ask whether a mechanism could hold the behavior instead: a schema, a hard block, a forced action, a tool-level refusal. If one could, **PROPOSE** a control to `05` (human acceptance required) and route the mechanism to TDD. **Every behavior moved into a mechanism is one fewer thing held by a model's good judgment.**

## The Governing Rule

For any change affecting agent behavior:

1. Identify the governing `ABS-B*` requirement.
2. Identify its verification obligation — the clause's **`verified_by`** field in `02`.
3. **Check the dimension's provenance.** It should come from observed failures: promoted from `DISC-D` (`04-discovery` §9), with a baseline measured on real traces. A dimension written from spec text alone is **provisional**. Say so.
4. Establish a behavioral **baseline** before modifying anything. That moves the evidence state out of `unmeasured`.
5. Inspect **individual** failures. Not the aggregate.
6. State a **falsifiable hypothesis** before touching the system.
7. Make the **smallest change** that tests that hypothesis.
8. Rerun the affected evals on the **dev** cases — **same cases, same method**.
9. Compare candidate against baseline, **against the noise floor**.
10. Check for regressions in previously-passing cases.
11. Promote important discovered failures into permanent coverage.
12. **Verify once on held-out cases** you did not iterate against, and attach the gate-check result.
13. **Do not claim behavioral completion without fresh evaluation evidence.**

## Routing — read the spec, don't infer

```
ABS-B07
verified_by: EVAL-D03        → BEV knows exactly where to go
```

```
ABS-B08
verified_by: unverified · GAP-02-04   → not a BEV row. List it on `unmeasured[]` with a tracing task;
                                        build the system; error analysis earns the evaluator later
```

```
ABS-B09  (a red line, or backed by a GOV-C control)
verified_by: (empty)         → STOP
```

**The obligation and the evaluator are two different things, and they are due at different times.**

| | Red lines (`EVAL-T`) and controls (`GOV-C`) | Quality dimensions (`EVAL-D`) |
|---|---|---|
| **Verification obligation** — *what* must hold | named before implementation | named before implementation, or `unverified` + a `GAP` (the canon permits this: `DOD-02-05`) |
| **Evaluator** — the test, judge or code check | **written first** — the criterion is crystal clear, and it is TDD-shaped | **built after error analysis shows the failure** — until then the obligation waits on `unmeasured[]`, outside the slice |
| Empty `verified_by` with no `GAP` | **STOP** — not implementation-ready | STOP — record `unverified` + `GAP` in `02`, then proceed |

Do not guess which eval applies, and do not invent one mid-task.

**Contracts written from spec text before any traces exist produce invented criteria.**
They look good on paper and miss real failures.
- **Dimensions and thresholds come from discovery on real traces.** Where the spec
  pre-dates the traces, the dimension is provisional and its threshold is re-set against
  the observed baseline.
- **A new failure mode is never minted into a dimension on the spot. Route it by stage**
  (`analyze-failures.md`):
  - **prototype / discovery:** a new `DISC-D` or `DISC-F`. Temporary IDs, axial coding by the domain owner.
  - **build:** a `04` change request for a new append-only `EVAL-*` ID, with trace evidence and human acceptance. **Not back into `DISC-*`**; those IDs ended at promotion.
  - **production:** classify it through the `06` §7 learning loop, then promote via `04` §6.2.

## The Loop

| Step | File | Produces |
|---|---|---|
| Derive evals | `derive-evals.md` | cases, and an evaluator **only when earned** |
| **Baseline** | `baseline.md` | a score, its variance, and every version pinned |
| **Analyze** | `analyze-failures.md` | clusters, suspected layer, one hypothesis — and a **disposition**: fix-only · code check · evaluator |
| **Experiment** | `run-experiment.md` | one change, rerun on dev, compared |
| Promote | `promote-regression.md` | a discovered failure made permanent — a **behavioral regression test**: red on the unfixed system, green at m of k runs |
| **Verify** | `verify-before-completion.md` | the held-out run, a machine-readable result, and the gate-check exit code |
| *Slice gate* | `tools/slice_gate.py` | the whole slice: every obligation, its tasks, its evidence, its open checkpoints |
| *Instruments* | `instruments.md` | which `evals:*` skill each step calls, in which mode |
| *Checkpoints* | `checkpoints.md` | the five reasons to pause for a human, and the queue |
| *Starter kit* | `templates/` · `tools/bev_harness.py` · `tools/export_traces.py` · `tools/checkpoints.py` | the manifest and result templates, the harness helper (run log and records), the OTLP trace exporter, the checkpoint queue (the agent opens; a human closes) |

**The tools live in `tools/` next to this file; the templates in `templates/`.** Throughout these
files, `<skill>` means this skill's base directory. Run tools from the project root as
`uv run <skill>/tools/gate_check.py …`, so result, ledger and manifest paths resolve against the
project. They need `uv` (it installs PyYAML from each script's header). No model is in the loop:
**their exit code is the evidence.**

**At slice start**, after brainstorming and before `writing-plans`: copy
`<skill>/templates/verification-manifest.yaml` into the project and route every behavioral
requirement (*Routing* above; `derive-evals.md` → *Is an evaluator earned yet?*). A human accepts it (C1).

**Most failures don't need an evaluator.** A failure found in error analysis that is a plain bug
gets fixed and a regression case — not a new dimension. Evaluators are for failures that persist,
cost enough to matter, or will be iterated on (`analyze-failures.md`).

**An `EVAL-D` score is a rate of binary verdicts** — the share of cases that pass one Pass/Fail
criterion. Never an average of 1–5 ratings.

## Common Rationalizations

| Excuse | Reality |
|---|---|
| "The score went up" | By more than the noise floor? If not, that's noise with a direction |
| "Tests pass, so the behavior is fine" | Structural tests bound false positives. **A missed case produces output that looks clean** |
| "I changed two things but the second was minor" | The delta is unattributable. One change, same as one failing test |
| "I improved the case set while I was in there" | Then this is a new series. Record the discontinuity; never re-baseline silently |
| "Evals are slow — I'll check at the end" | You'll have made ten changes and know which one worked: none |
| "It's obviously better" | Run it. Obviousness is what evals exist to check |
| "Fifteen cases, but they're representative" | Of what population? Name it, or the number means nothing |
| "The eval is wrong, not the system" | **Possibly true.** That's `suspected layer: eval`. Say it and fix the rubric — don't iterate against a bad measure |
| "I'll baseline after I make the change" | Then you have one number and no comparison |
| "It was red and now it's green" | Was it red, or `unmeasured`? **No baseline, no red, and no earned green** |
| "The score is above the threshold" | The point estimate is. **91% on 24 cases has a 95% lower bound of 74%.** Report the interval |
| "Three runs with a tight spread, so it's precise" | Run variance measures the model's randomness. **It says nothing about how few cases you have.** Both count |
| "I tuned it on the eval set and it passes" | Then that set is your dev set. **Verify on cases you never iterated against** |
| "The judge is an LLM, it's consistent" | Consistent isn't correct. **Without TPR/TNR against human labels, the judge's errors are baked into the score** |
| "The spec says 90%, so the dimension is defined" | Defined on paper. **Has anyone looked at traces?** If not, it's provisional |
| "Only the model can decide this, so BEV only" | Could a mechanism hold it instead? Ask before you accept a route held by a prompt |
| "Every behavioral clause needs its eval before we build" | Not for quality dimensions. **Name the obligation, build the system, look at traces, then earn the evaluator** |
| "We found a failure, so we need a new dimension" | Most failures are bugs. **Fix it, add a regression case.** A dimension is for what persists |
| "Rate it 1 to 5" | Annotators can't agree on a 3 versus a 4, and judges inherit that noise. **Pass or fail, per criterion** |
| "We'll look at fairness when failures show up" | A disparity never shows up in a single trace. **Design the stratified measurement now, or you'll never see it** |
| "It passed after the fix" | Once? A case failing 20% of the time passes 5 of 5 a third of the time. **m of k, and the dimension gate for the rate** |
| "That test is just flaky, rerun it" | Below m of k is a regression. **Retry-until-green hides the failure you promoted it to catch** |
| "It passed the gate-check, so it's done" | Not if `requires_human_review` is true. **It's `awaiting-judgment-review` until C4 closes** |

## Red Flags — STOP

- Reporting a delta without its variance
- Re-baselining after changing the case set or the method
- Marking a `both`-routed task complete on TDD green alone
- Treating a delta inside the noise floor as an improvement
- Changing prompt and retrieval in one cycle
- Optimizing the aggregate before reading individual failures
- Promoting a production failure without classifying it
- Implementing a red line or control whose `verified_by` is empty — or a quality clause with neither a verifier nor `unverified` + `GAP`
- Building a quality evaluator before any trace has shown the failure
- Creating a dimension for a failure that a fix and a regression case would settle
- Invoking `evals:evals-start` once 04 dimensions exist
- Deferring an RAI hard constraint until failure data exists
- Relying on unstratified error analysis to find a subgroup disparity
- Retrying a behavioral regression test until it passes
- Stopping all work for a human instead of queueing the checkpoint and continuing unblocked tasks
- Reporting `green` for an obligation that was never baselined
- Gating on a point estimate without its confidence interval
- Iterating against the held-out cases, or looking at their failures to choose the next change
- A model-scored gate whose judge has no recorded TPR/TNR against human labels
- Writing a new `EVAL-D` mid-build from spec text, with no trace evidence
- Accepting `BEV_ONLY` without asking whether a mechanism could hold the behavior
- Marking a BEV obligation complete with no gate-check result attached, **on the agent's own say-so**
- Reading a dev tool's *task complete* as *behavior proven* — the task is `implemented`, the obligation is `green`
- Merging a slice on tests alone, without the slice gate

## Superpowers Integration: Known Conflicts

Checked against `obra/superpowers` v6.3.0. **Resolve these with project `CLAUDE.md`
instructions.** Superpowers' own `using-superpowers` says user instructions take
precedence over skills.

| Superpowers behavior | Conflict | Override |
|---|---|---|
| Architectural brainstorming allows **only** `writing-plans` next | The verification manifest must run between them | *"After brainstorming, build the verification manifest before writing-plans."* |
| `subagent-driven-development` runs tasks with **no check-ins** | Accepting DERIVE rows, validating judges, and judgment review all need a human | *"BEV judgment reviews and manifest acceptance are human checkpoints outside SDD. Run TDD tasks through SDD; pause at BEV gates."* |
| `verification-before-completion` accepts **command output** as evidence | Eval scores aren't pass/fail command output | **Make the gate a command:** the gate-check exits `0` or non-zero (`verify-before-completion.md`), and that exit code is the evidence |
| The session hook re-injects Superpowers on start, `/clear` and compaction | BEV triggers can lose ambiguous matches | Put the routing rule in `CLAUDE.md` so it survives the re-injection |

**Ready-to-paste overrides:** `claude-md-snippet.md`. The same snippet settles `evals:*` trigger
contention — BEV owns the loop; the instruments are called by step (`instruments.md`).

## When the Failure Isn't Code

Failures route beyond the implementation. Before assuming a coding fix:

| Classification | Routes to |
|---|---|
| Product assumption wrong | `01`, or back to discovery |
| Behavioral contract wrong | `02` — **reopen the clause** |
| Tool capability insufficient | `03` |
| Eval defective | `04` — fix the rubric |
| Enforcement missing | `05` |
| Production disagrees | `06` |

**If several failures reveal the requirement itself is wrong, the answer is not to keep
coding until the eval passes. It is to reopen the requirement.** Otherwise you optimize
the system against a bad spec — efficiently.
