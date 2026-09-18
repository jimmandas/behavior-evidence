# behavior-evidence (BEV) Plugin — Design

**Status:** design, v0.15.0 (2026-09-18). **Not yet behaviorally proven.** The plugin is this repository (install and operation: `README.md` and `RUNBOOK.md`); the skill files in `skills/verify-agent-behavior/` implement §§5–8 and §10. The tools are built: gate-check (§10.7) at `skills/verify-agent-behavior/tools/gate_check.py`, the judge adapter at `skills/verify-agent-behavior/tools/judge_to_eval_result.py`, and the slice gate (§10.10) at `skills/verify-agent-behavior/tools/slice_gate.py`, with 354 tests.

**Changed in 0.15.0.** Release decisions on `unmeasured[]` are backed by a closed checkpoint. The reviewer or approver was a plain field in the agent-writable manifest, so an agent could sign its own release decision — the hole C4 closed for judgment review in 0.13.0. Now *no failures observed* must cite a C3 and *deferred to production* a C4, for that obligation, closed `done` by the same person (`closed_by`, case- and space-insensitive). No citation → awaiting (`S-DECISION-UNBACKED`); a checkpoint of the wrong type or obligation, declined, with no closer, or closed by someone else → not done. Checked only at release. **Limit:** `traces_reviewed` is still the manifest's word; the checkpoint proves who decided, not how many traces they read. *Promoted* is unchanged: it is anchored by the BEV row, which needs an accepted 04 row in the protected spec.

**Changed in 0.14.0.** The thresholds are protected, not just read. The gate already took the threshold from 04 §4.2, but the spec sat in the repo where the agent could lower it in the same commit — found by the blind engineer review of the one-pager. Jim approved closing it in two steps.
- **Step 1 (this):** `.claude/bev.json` gains `protected_files` — the eval spec, and optionally judge prompts and held-out cases. The hook blocks the agent's writes to them (file tools and shell), matching whole path components; reads stay open. Verified live: an agent told to lower 0.90 to 0.85 was blocked by Edit and by the shell, and the file was unchanged.
- **Step 2 (with CI, not built):** the slice gate compares thresholds with a hash recorded at spec acceptance; a change needs a named approver.

**Changed in 0.13.0.** Custody (Jim chose: evidence outside the repo, plus a hook).
- **`hooks/protect_evidence.py`** (PreToolUse on Write, Edit, MultiEdit, NotebookEdit, Bash; dormant without `.claude/bev.json`): the agent can't write the evidence directories or the config; Bash that touches them must be a single, uncomposed call of a plugin tool in an allowed mode. Exit 2 blocks. **Limit:** a program the agent writes elsewhere can still open the files — the hook makes tampering deliberate; CI custody is the strong form. Whether hooks apply under `--dangerously-skip-permissions` is not confirmed by the docs.
- **`tools/checkpoints.py`:** `open` / `list` from the session; `close --by <name>` is human-only (the hook blocks it). **A C4 clears a review only with `status: done` and a `closed_by`.**
- **Slice gate:** the manifest can name the `checkpoints` queue; `~` expands in manifest paths.
- **The earlier "no hooks" stance (0.8.0) is superseded** for custody only; routing still lives in the `CLAUDE.md` snippet.

**Changed in 0.12.0.** Review pass 3 of 3: docs agree with the code, and a starter kit.
- **Starter kit:** `templates/verification-manifest.yaml` and `templates/eval-result-template.yaml`; `tools/bev_harness.py` (logs each run to the ledger before any case runs, refuses a dirty tree, records cases, assembles the judge run; evidence can live outside the repo); `tools/export_traces.py` (OpenTelemetry OTLP JSON → the trace export). An end-to-end test drives all of it in a scratch git repo.
- **Slice gate:** reports `stale` as the derived state when evidence is pinned to another commit.
- **Docs:** §4 shows the manifest the slice gate reads (the classifier's fields marked as human-only); §10.1 names the template instead of a skill that never existed; `Must verify` → `verified_by`; `<skill>/tools/` paths; the SKILL loop table is whole and gains the starter kit; the trigger includes slice start; README and RUNBOOK use `$AI_SPECS`, list every finding code, and agree on review reasons; staleness claims match what the gate detects.

**Changed in 0.11.0.** Review pass 2 of 3: the gate computes its own numbers.
- **`tools/evidence_stats.py` (new):** the statistics, shared by the adapter and the gate — TPR/TNR from labelled items, corrected run rates, score, noise floor, a fixed-seed bootstrap interval, regressions, unacceptable failures.
- **Gate-check:** every number is computed from `runs[]`, `baseline.records[]` and `judge_validation.items`; reported numbers are checked (`F-RECOMPUTE`) and never used. `--contract` reads the threshold and method from 04 §4.2 (`F-CONTRACT`; without it `W-THRESHOLD-UNPINNED`). An `EVAL-T` pass queues review. The verdict carries a `computed` block.
- **Adapter:** takes `baseline_runs`; works without a judge for deterministic and human-scored dimensions; carries the records, the labels and the failure counts into the result.
- **Slice gate:** needs the 04 `contract` for a BEV slice (`S-NO-CONTRACT`); **derives each obligation's evidence state from its result** — a manifest `evidence_state` is optional and must match. Closes the hand-copying step.
- **Example slice:** baseline records, a 04 excerpt, no copied state.

**Changed in 0.10.0.** Review pass 1 of 3: an adversarial review ran false greens past both gates. The cheap ones are closed; the gates no longer trust the manifest or the result's say-so.
- **Slice gate:** a result must carry the row's obligation, dimension and stage, and serve one row; the manifest's `evidence_state` must equal the gate's verdict; `routing` must agree with the `required` flags (classifier routes accepted); a slice with a BEV row needs a `commit`, a `ledger` and a `traces` export, and span IDs when cases cite spans; a C4 clears only its own obligation and only at `status: done`; any checkpoint status but `done`/`declined` is open; a result that crashes the gate blocks. `S-PROVISIONAL-AT-RELEASE` is gone (a build result under a release slice is now a mismatch).
- **Gate-check:** the baseline must be logged runs (`baseline.run_ids`, ledger `purpose: baseline`, same series, earlier commit); a claimed run must be logged as a held-out run of this candidate; baseline runs don't count as held-out reuse; a judge no better than chance always fails, and `--min-judge-alignment` can't go below 0.5; failure counts must be non-negative integers; spans cited against a spanless export warn; a crash exits 3.
- **Still open:** the gate still trusts `ci95`, `noise_floor`, `threshold` and `baseline.score` (pass 2), and custody of the ledger and checkpoint queue (Jim's decision).

**Changed in 0.9.0.** Renamed from `edd` (eval-driven development) to **`behavior-evidence` (BEV)**; the skill is `verify-agent-behavior` (was `eval-driven-development`). Jim: the method is not eval-driven development. Mechanical: the manifest key `verification.edd` → `verification.bev`, the queue `edd/checkpoints.yaml` → `bev/checkpoints.yaml`, routes `EDD_ONLY` / `TDD_AND_EDD` → `BEV_ONLY` / `TDD_AND_BEV`, finding codes `S-EDD-*` → `S-BEV-*`. No behavior change. Earlier entries below use the new name.

**Changed in 0.8.0.** Packaged as an installable Claude Code plugin (Jim approved; hash-locking 04 artifacts left undecided).
- **Layout:** `.claude-plugin/plugin.json`; the skill moved to `skills/verify-agent-behavior/` with its `tools/` beside it, so the skill runs them relative to its base directory; a local marketplace in the author's spec repo (`behavior-evidence@ai-specs-local`)
- **`README.md`** (what it enforces, what it does not, install, limits) and **`RUNBOOK.md`** (one slice end to end, exit and finding codes → action)
- **`examples/slice/`:** a worked slice run through all three tools; `tools/tests/test_examples.py` keeps it working
- **No hooks:** routing stays in the project `CLAUDE.md` snippet

**Changed in 0.7.0.** One connected evaluation contract: dimension → evaluation → harness → trace, joined by IDs. Jim approved four changes after reviewing an outside write-up on syncing them; its per-case scores, harness-decided pass and up-front dimensions were rejected.
- **§10.7:** the result carries **per-case records** (`run_id` · `test_case_id` · `trace_id` · binary verdict · critique · `evidence_span_ids`), and the gate recomputes every rate from them
- **§10.7:** a **run ledger** (`--ledger`): a held-out run of the same candidate left out of the result is invalid evidence; held-out reuse across candidates needs review. This closes retry-until-green on verification
- **§10.7:** **trace resolution** (`--traces`): a claimed trace the store never saw, or a span not in its trace, is invalid evidence. This closes fabricated runs
- **Judge adapter:** input keyed by `item_id` and `test_case_id`; positional arrays rejected
- **§10.10:** the slice gate passes `ledger` and `traces` through
- **Proposed, not applied:** 04 §2.1 trace requirements and per-case §7.2 provenance (a proposal in the author's spec repo, not published)

**Changed in 0.6.0.** Jim: *if a dimension is waiting for failure data, why is it in the build slice at all?* It isn't any more. 0.5.0's slice gate blocked on `unmeasured`, which deadlocked Hamel's rule: failure data needs the running slice, and the slice couldn't finish without the evaluator.
- **§3.1, §3.2:** a quality obligation with no earned evaluator is not slice work. The build owes it a tracing task, nothing else
- **§4.2 (new):** the manifest's `unmeasured[]` list, and the release decision each entry needs
- **§10.10:** a BEV row needs an earned `EVAL-D`/`EVAL-T` id; waiting obligations never block a build slice; at release an undecided one awaits a human

**Changed in 0.5.0.** The join between two clocks. A Superpowers task finishes on command output in a session; an obligation finishes when the evidence lands, days later.
- **§4:** manifest join fields — `tasks[]`, `blocked_by[]`, `accepted`, `commit`, and `evidence.last_result`
- **§10.10:** the **slice gate** (`tools/slice_gate.py`), which is where a behavioral claim is blocked — not inside a task

**Changed in 0.4.0.** Two answers to Jim's questions on the BEV FAQ entry, both approved ("yes to both"):
- **§3.2:** what to build before any failure, **by dimension type**, including quality and three kinds of RAI; the severity × detectability rule; scheduled error analysis so `unmeasured` isn't a hiding place
- **§7.1:** the **behavioral regression test**, TDD for an observed failure. Red on the unfixed system, green at m of k runs, a flakiness policy, and what k-of-n can and cannot prove

**Changed in 0.3.0.** Jim accepted the integration with Husain & Shankar's evals-skills and three course corrections from their FAQ entry *"Should I practice eval-driven development?"* (their answer: generally no; start with error analysis):
- **§0:** what BEV is not
- **§3.1:** the obligation is named up front, the evaluator is earned
- **§6.1:** every failure cluster gets a disposition (fix-only · code check · evaluator), with a cost-benefit line
- **§10.7:** the gate-check emits `requires_human_review`; the judge adapter is added
- **§10.8:** instruments (`evals:*`) and the three `error-discovery` modes
- **§10.9:** checkpoints C1–C5 and the queue
- **§11.1:** the pilot measures no longer reward evals-first behavior

Record: the author's Superpowers × Hamel evaluation notes (not published).

**Changed in 0.2.0.** Jim accepted the recommendations from the Superpowers × Hamel evaluation (the author's evaluation notes, not published):
- **Evidence state**, separate from lifecycle status (§4.1)
- **Dimension provenance**: discovery on real traces comes first (§1.1), and new failure modes route by stage (§1.2)
- **"Make it deterministic first"** before any BEV-only route (§3)
- **Dev/held-out splits and a statistical gate** (§8.1)
- **Inputs** aligned with the full canon (§1)
- **Known Superpowers conflicts** and their overrides (§10.6)
- **Deterministic gate-check** (§10.7)
- **Stage tiering** (§8.2)
- **How to prove the plugin works** (§11.1)
## 0. What BEV is not

**Not eval-driven development — "write the evals before the feature."** Husain and Shankar argue
against that practice. An LLM system's failures can't be enumerated in advance, so evaluators written first
measure imagined failures. **This plugin agrees.** BEV here means three things:
- **measure before you change:** a baseline on the running system, one change, a comparison
- **claim only what the evidence supports:** the gate, the interval, the held-out run
- **build evaluators for observed failures**, except where the criterion is crystal clear: red lines (`EVAL-T`) and controls (`GOV-C`)

**Naming (resolved in 0.9.0).** This was "EDD, eval-driven development" through 0.8.0. Jim renamed it:
the method is not eval-driven development. It is **behavior evidence (BEV)** — the plugin
`behavior-evidence`, the skill `verify-agent-behavior`. The canon spec text (set rules §8, author guide
§4) still says "EDD"; changing it is a template bump, not done here.

**Revised against Superpowers.** It already has an execution engine — planning
(`writing-plans`), per-task subagent dispatch and review (`subagent-driven-development`),
worktrees, code review, and `verification-before-completion`. **BEV rebuilds none of it.**
What Superpowers lacks is a first-class loop for probabilistic behaviour, and there is
external evidence of the gap: prompt-heavy work can return a **false GREEN** when tests
validate output *structure* rather than content *quality*. That is this plugin's problem
statement.

**What it is.** The behavioral-evidence half of the development loop. TDD proves
deterministic mechanisms; BEV proves probabilistic behaviour. They are peers, and a
consequential requirement needs both.

**The unit of work is a dimension, not a test.** That single difference drives most of
the design below.

**What BEV does not own:** planning, task decomposition, subagent dispatch, code review,
worktrees, deterministic test execution, commits. All Superpowers. BEV contributes
**classification, the behavioural loop, and a completion gate** — and hands every code
change back to Superpowers to implement.

---

## 1. Inputs

Read-only. The plugin never authors a spec.

| Source | What it takes |
|---|---|
| `02` §3.3 | behavioural clauses · `verified_by` · `enforced_by` (or `prompt-level only`) |
| `04` §2 | the dimension register — what is measured, construct, scope |
| `04` §4.2 | the stage contract — threshold, method, case set, **variance** |
| `04` §4.1 | case sets and their provenance |
| `04` §3.1 | known unacceptable failures |
| `05` §4 | controls, class, strength — **this is what routes** |
| `04-discovery` | at discovery stage: `DISC-D*`, `DISC-F*`, `CASE-*`. At build stage: **the promotion record**, which is where a dimension's provenance comes from |
| `01` §3 | commitments, `Kind`, `Category` |
| `03` | tool contract properties (idempotency · auth scope · side-effect class). They route to TDD (classifier R11) |
| `06` | `MEAS-nn` rows. These route to `MEASUREMENT_ONLY` (R1), not to development; also where regression promotion meets production signal |
| `07` (optional) | technical design. **If absent, anything architectural the plugin says is a PROPOSE, never a DERIVE** |

### 1.1 Dimension provenance: discovery on real traces comes first

**Contracts written from spec text before any traces exist produce invented criteria.**
They look good on paper and miss real failures, which is the central warning of
trace-first error analysis (Husain & Shankar).

The canon already has the remedy, and the plugin now enforces it:

| Provenance | How the plugin treats the dimension |
|---|---|
| **`DISC-promoted`** — observed in traces during discovery, baselined, promoted through `04-discovery` §9 | Established. Its threshold was set against an observed baseline. |
| **`spec-only`** — written in `04` without trace evidence | **Provisional.** Baseline on real traces before building against it; expect to re-set the threshold, re-scope, or split. The manifest carries `provenance: spec-only` so the count is visible at release review. |
| **`build-observed`** — a new mode found during build, accepted through a `04` change request | Established once accepted: a new append-only `EVAL-*` ID with trace evidence. **The coding agent proposes; it never mints.** |
| **`production-derived`** — classified through `06` §7, promoted via `04` §6.2 | Established once classified and accepted |

### 1.2 New failure modes route by stage

**The same observation is handled differently at each stage**, because the IDs, the authority
and the labeling differ.

| Stage | New failure mode (no dimension covers it) | Covered by an existing dimension | Classification | ID rule |
|---|---|---|---|---|
| **prototype · discovery** | Open code → axial category → new `DISC-D` / `DISC-F` (`04-discovery` §2–3, §7) | a new `CASE-nn` | **Yes.** Axial coding by the domain owner; this is discovery's job | `DISC-*` are temporary; renumber freely; they convert at §9 and stop existing |
| **build** | **A `04` change request:** propose a new `EVAL-D` / `EVAL-T` with trace evidence and case IDs; human acceptance | **`04` §6.1 regression capture** | **No.** Already labeled by the eval or test that found it | `04` §2 is append-only. **A new mode is a new ID; a changed definition is a new ID.** Never back into `DISC-*` |
| **production** | **`06` §7 learning loop:** classify, then route: behavior → `02` clause → `04` case · control → `05` · measurement → rubric · bet → **back to discovery** | **`04` §6.2 production-derived promotion** | **Yes.** It arrives unlabeled; needs the failure taxonomy | New `EVAL-*` IDs through `04`; learning events recorded in `06` |

**At every stage, a cluster of new modes pointing the same way is evidence about the
requirement or the bet, not the implementation.** At build, that means reopening `02`,
or returning to discovery, before minting more dimensions (§6).

---

## 2. Requirement classification

Three authority levels, **visibly separated in every output**. The plugin must not
become an unaccountable seventh spec author.

| Level | May | Must not |
|---|---|---|
| **EXTRACT** | restate what a spec explicitly says, with its ID | infer |
| **DERIVE** | state the obligations that logically follow | choose a mechanism |
| **PROPOSE** | suggest an implementation approach, **flagged as a proposal** | apply it, or record it as derived |

*"Conflicting evidence must be escalated"* → EXTRACT the clause · DERIVE that it needs a
workflow disposition and probably a runtime control · **PROPOSE** a mechanism. Choosing
Redis and a 0.72 threshold is a PROPOSE that requires human acceptance, never a DERIVE.

---

## 3. Routing — BEV, TDD, or both

**Mechanical, from what the specs already carry.** No judgment.

| Condition | Routes to |
|---|---|
| Control class `SCHEMA · HARD-BLOCK · LOAD-PIN · CRYPTO` | **TDD** — the mechanism is deterministic |
| Control class `CONFIG · PROMPT`, or `Enforced by: prompt-level only` | **BEV only** — and **flag it**: no test can prove a prompt holds |
| A behavioural clause with a control | **both** — TDD proves the mechanism, BEV proves the behaviour |
| `01` commitment, `Kind: behavioral` | both, via its control |
| `01` commitment, `Kind: policy · commercial` | neither — a gate criterion |
| `01` commitment, `Category: operational` | TDD for the instrument, `06` for the signal |
| An unacceptable failure (`EVAL-T`) | both — adversarial cases **and** a structural test |
| A governance decision, manual review obligation, or currently unenforceable commitment | **`NO_EXECUTABLE_VERIFICATION`** |

**The fourth disposition is not a failure state.** Forcing a governance decision into TDD
or BEV produces fake coverage. It routes to a gate criterion and is counted separately.
**A low-confidence classification is flagged, never silently resolved.**

**The flag is the point.** A requirement routed to BEV *only* is one whose enforcement is
a request to a model. The plugin surfaces that at routing time, not at release.

**Make it deterministic first.** Before any `BEV_ONLY` route is accepted, the plugin asks
whether a mechanism could hold the behavior: a schema state, a hard block, a forced
action, a tool that refuses. **If one could, it PROPOSEs a `05` control** routed to TDD. The
proposal needs human acceptance under §2, and `05` is where the control gets authored. The
eval then measures only whether the model *attempts* the forbidden thing.

**This shrinks the most expensive and least certain part of verification.** In the
Superpowers × Hamel pilot, an unguided coding agent's most effective fixes were exactly
these conversions: a hook forcing a terminal action, and a tool refusing to book a
safety-critical test.

### 3.1 The obligation is named up front; the evaluator is earned

Routing says **what kind of verification** an obligation needs. It does not mean the evaluator exists yet.

| | Red lines (`EVAL-T`) · controls (`GOV-C`) | Quality dimensions (`EVAL-D`) |
|---|---|---|
| Verification obligation | named before implementation | named before implementation, **or `unverified` + a `GAP`** (`DOD-02-05` permits it) |
| Evaluator | **written first**: the criterion is clear and TDD-shaped | **built after error analysis shows the failure**; until then the obligation is not slice work — it waits on `unmeasured[]` (§4.2) |
| Empty `verified_by`, no `GAP` | **not implementation-ready** | record `unverified` + `GAP`, then proceed |

**The cheapest check that works.**
- **deterministic** code where the failure is checkable from output and fixture
- a **model** judge only where interpretation is needed (about 100 human labels to validate)
- **human** review where the construct is still being learned

**An `EVAL-D` score is the rate of a binary verdict**, never an average of 1–5 ratings.

### 3.2 What to build before any failure, by dimension type

**"Don't write evals before failures" is a rule about quality evaluators, not all eval work.**

| Dimension type | Build before any failure | Waits for observed failures |
|---|---|---|
| Controls (`GOV-C`) · red lines (`EVAL-T`) | the mechanism or check, with its tests | nothing |
| **Quality** (`EVAL-D`) | named obligation (on `unmeasured[]`, §4.2) · **tracing, as a TDD task** · test inputs · a scheduled error analysis (~100 traces before release) | the evaluator — and with it, the obligation's place in a slice |
| **RAI: hard constraints** (PII, prohibited inputs, no automated denial, disclosure, regulation) | controls and red-line tests; probing cases | nothing — **waiting for failure data means waiting for harm** |
| **RAI: distributional** (fairness, subgroup disparity) | **the measurement plan**: stratification, subgroup sample sizes, telemetry, metric definition | the scorer and threshold |
| **RAI: human reliance** (automation bias, rubber-stamping) | instrumentation: override rate, time on case, citations opened | thresholds tuned on real use |
| Operational | SLIs and telemetry | targets refined against the baseline |

- **The rule underneath is severity × detectability.**
  - **Severe, or invisible in a single trace:** act before failures.
  - **Visible and recoverable:** earn the evaluator.
- **Unstratified error analysis cannot find a disparity**, because the disparity lives in the distribution.
- **This agrees with the canon:** 02 §3.3 *At discovery* already makes 01 §6 RAI obligations firm prohibitions.
- **Full table with examples:** `behavior-evidence/skills/verify-agent-behavior/derive-evals.md`.

---

## 4. Traceability & verification manifest

Generated, then **reviewed**. Not authoritative until a human accepts the DERIVE rows.
Template: `behavior-evidence/skills/verify-agent-behavior/templates/verification-manifest.yaml`.

**What the slice gate reads** (0.11.0) — the file as a whole:

```yaml
slice: SLICE-03
stage: build                     # build | release | production
commit: abc123                   # the code state the evidence must be pinned to
contract: 04-evaluation-spec.md  # thresholds (04 §4.2)
ledger: runs.jsonl               # the harness's run log
traces: traces.jsonl             # the trace-store export
obligations:
  - requirement: ABS-B07
    routing: both                # tdd · bev · both (or TDD_ONLY · BEV_ONLY · TDD_AND_BEV) · MANUAL_GOVERNANCE · MEASUREMENT_ONLY · UNRESOLVED
    tasks: [plan-2026-09-16/task-4]
    accepted: true               # C1
    blocked_by: [CP-0007]
    verification:
      tdd: {required: true, refs: [CONTRACT-021, UNIT-088], state: green}
      bev: {required: true, dimension: EVAL-D03, last_result: results/EVAL-D03.yaml}   # the state is derived from the result
unmeasured: [...]                # §4.2
```

**What a human reads at C1** — each obligation can also carry the classifier's reasoning. The
gate ignores these fields:

```yaml
requirement: ABS-B07
source: 02-agent-behavior-spec §3.3
statement: Ambiguity MUST be surfaced with its unresolved basis
extract:
  enforced_by: GOV-C12
  verified_by: that no ambiguous output lacks a basis
derive:
  classification: [behavioural, structural]
  implementation_obligations:
    - agent output schema admits an explicit ambiguity state
    - runtime rejects ambiguous result with empty basis
  routing: both
verification:
  tdd:
    required: true
    types: [contract, unit]
    refs: [CONTRACT-021, UNIT-088]        # codebase IDs; the set does not own them
  bev:
    required: true
    dimension: EVAL-D03
    case_bucket: judgment-intensive
propose:                                   # requires human acceptance
    - ambiguity_basis[] required when status = ambiguous
tasks: [plan-2026-09-16/task-4]            # the plan tasks that implement it — the dev-tool join
blocked_by: [CP-0007]                      # open checkpoints from bev/checkpoints.yaml
accepted: true                             # a human accepted the DERIVE rows (C1)
status: derived            # extracted | derived | accepted | implemented | verified
unresolved:
    - exact ambiguity schema not yet defined
```

**Completeness is countable from the manifest** — the release-review number: *n binding ·
n classified · n with an implementation target · n needing BEV · n with it · n
prompt-only · n unresolved.* **Also count:** *n `unmeasured` · n `spec-only` · n
`green-provisional` · n `stale`.* These are the numbers that say how much of "verified" is
actually known.

### 4.1 Evidence state is not lifecycle status

`status` says where the requirement is in the workflow. **`evidence_state` says what has
been measured.** Conflating them creates a false signal in both directions:
- a derived-but-unbaselined obligation shows as "not done", which looks like `red`
- an implemented one shows as "done", which looks like `green`

| `evidence_state` | Means |
|---|---|
| **`unmeasured`** | Routed to BEV, no baseline. **The honest starting state; not red.** |
| **`red`** | Baseline or rerun below threshold, or an unacceptable failure fired |
| **`inconclusive`** | Delta or threshold gap inside the noise floor or CI |
| **`green-provisional`** | Build-stage pass on held-out, but the CI lower bound is below threshold (§8.1) |
| **`green`** | Stage gate passed on held-out, gate-check exit `0` |
| **`stale`** | Was green; a pinned version changed since |

**Transitions only through recorded runs.** **`unmeasured → green` with no baseline is an
unfounded claim.** The gate-check rejects it, and any evaluation of the plugin scores it as
a false green (§11.1).

### 4.2 Obligations waiting for failure data: `unmeasured[]`

A quality obligation with no earned evaluator is **not a BEV row**. It sits in a separate list:

```yaml
unmeasured:                  # §4.2 — quality obligations still waiting for failure data. Not slice work.
  - requirement: ABS-B09
    gap: GAP-02-04
    tracing_task: plan-2026-09-16/task-9   # the one thing the build owes it: the behavior shows up in traces
    error_analysis: {trigger: "100 traces or 2026-10-15", checkpoint: CP-0012}   # a queued C3, never a blocker
    decision: null             # release needs one: no-failures-observed · deferred-to-production · promoted
```

- **At build it never blocks.** The only check is that `tracing_task` exists: without traces the failure can't be seen, and the evaluator can't be earned.
- **A BEV row needs an earned id** (`EVAL-D*`, `EVAL-T*`). A `GAP` or a `DISC-*` id in a BEV row is misrouted.
- **Promotion mid-build:** error analysis shows a failure → a `04` change request (C5) → the new id gets a BEV row, and the entry records `decision: {outcome: promoted, dimension: EVAL-Dnn}`. From then on it is slice work, with its baseline owed.
- **At release every entry needs a signed decision:** `no-failures-observed` (reviewer, `traces_reviewed`; 0 in n bounds the rate only below 3/n, and the gate expects 100 unless a human accepts the bound) · `deferred-to-production` (approver) · `promoted`.

**Why a separate list and not a state.** An evidence state is something a slice can be blocked on. A dimension that can't be measured until the slice runs is not.

---

## 5. The loop — seven stages

**`SELECT → BASELINE → ANALYZE → HYPOTHESIZE → CHANGE → COMPARE → PROMOTE`.**

Seven stages rather than a three-word analogy to red-green-refactor. Forcing the analogy
costs more than it buys: **`HYPOTHESIZE` has no TDD equivalent and is the stage that
separates BEV from prompt tinkering.**

| Step | Requires | Produces |
|---|---|---|
| **SELECT** | the cases relevant to *this* requirement, **split into dev and held-out** | a named, versioned subset per split |
| **BASELINE** | model · prompt · retrieval · tool · **`control_policy_version`** · case-set version | scores, outputs, traces, **and variance** |
| **ANALYZE** | failures inspected individually, not in aggregate | clusters with a **suspected layer** |
| **HYPOTHESIZE** | an explicit, falsifiable statement | *"recognition fails when the authoritative source appears second, because the prompt prioritises first-found evidence"* — never *"improve the prompt"* |
| **CHANGE** | **a change request handed to Superpowers** (§10.4) | an implementation, built by their engine |
| **COMPARE** | the **same** case set version and method | `improved · unchanged · regressed · **inconclusive**` |
| **PROMOTE** | a validated failure | a permanent regression case (§7) |

**The gate is not "did it improve."** It is **did it improve by more than the noise
floor**. A +0.02 delta on a metric that swings ±0.04 is not an improvement, and treating
it as one is how eval-driven work becomes eval-flavoured guessing.

**One change per cycle.** Two changes and the delta is unattributable — the same reason
TDD writes one failing test at a time.

**A method or case-set change ends the series.** Record the discontinuity; do not
re-baseline silently.

**`inconclusive` is the honest fourth value**, and it is what red/green has no equivalent
for. A delta inside the noise floor is not `unchanged` — it is *not yet known*, and it
resolves by running more cases or making a larger change, never by declaring completion.

**BASELINE through COMPARE run on dev. Verification runs held-out, once.** A held-out case
whose failure was read to choose a change has become dev. **A set you tuned against can't
verify the tuning.**

---

## 6. Failure analysis

Reuses `04-discovery` §7 rather than inventing a second scheme.

| Failure cluster | Cases | **Suspected layer** | Hypothesis | Next experiment |
|---|---|---|---|---|

**The suspected layer routes the fix**: `prompt · orchestration` → 02 · `retrieval ·
tool` → 03 · `control` → 05 · `UX` → 01 §4.1 · `data` → the corpus · `eval` → the rubric
here.

**`eval` is the row that stops wasted cycles.** If the rubric was wrong, no amount of
system change will move the score.

### Failures route beyond code — and may reopen the requirement

| Classification | Routes to |
|---|---|
| Product assumption is wrong | **01**, or back to discovery |
| The behavioural contract is wrong | **02** — reopen the clause |
| Tool capability is insufficient | **03** |
| The eval is defective | **04** — fix the rubric |
| Enforcement is missing or too loose | **05** |
| Production reality disagrees | **06** |

> **If several failures reveal the requirement itself is wrong, the correct response is
> not to keep coding until the eval passes. It is to reopen the requirement.** Without
> this route, BEV optimises the system against a bad spec — and does it efficiently.

That route exists *because* the six specs do. A plugin with nowhere to send a wrong
requirement has only one move, and it is the wrong one.

### 6.1 Every cluster gets a disposition

**Most failures found in error analysis are bugs. Fix them.** An evaluator per failure is how a
suite fills with metrics that don't move quality.

| Disposition | When | Produces |
|---|---|---|
| **fix-only** | clear cause and fix, unlikely to recur | the fix + a regression case (§7). No dimension |
| **code check** | checkable from output and fixture, could recur | a deterministic check, test-first |
| **evaluator** | persists, costs enough to matter, or will be iterated, **and** needs interpretation | a judge or human review. **Cost-benefit line required** (frequency · cost · iterate? · why no cheaper check). C5 if a new dimension, C2 for labels (§10.9) |

---

## 7. Regression promotion

Every failure becomes a permanent case. Sources differ by stage (`04` §6):

| Stage | Source | Classification needed? |
|---|---|---|
| discovery · build | discovery failures · adversarial · test failures | **no** — the failure is already labelled by the test that found it |
| production | production traces | **yes** — it arrives unlabelled |

Promotion writes: the case, its bucket, its provenance, and **a link back to the failure
cluster that produced it.**

### 7.1 The behavioral regression test: TDD for an observed failure

**A pass rate can't go red → green. An observed failure can.** This is where probabilistic behavior
joins TDD without writing an evaluator for an imagined failure: **the red comes from a real one.**

| Step | Rule |
|---|---|
| **Red** | the observed case fails at least once in `k_red` = 10 runs on the unfixed system. If it never fails, it isn't a case yet |
| **Green** | on the fixed system it passes **m of k**: k = m = 10 for red lines, controls and RAI hard constraints · k = m = 5 for quality |

**A tripwire, not a measurement.** 10 of 10 passes still allows a true failure rate up to 26% at 95%
confidence, and 5 of 5 allows up to 45%. **The regression test catches a failure coming back; the
dimension gate measures the rate.**

**Flakiness policy:**
- never retry until green
- below m of k counts as a `regression` in the gate-check
- quarantine only as a recorded C4 decision with an expiry
- keep pass history per case
- a pinned-version change reruns everything

**A ticket carrying behavioral regression tests is red until they pass**, together with its
deterministic tests and, where a dimension is warranted, its gate-check. Full rules: `behavior-evidence/skills/verify-agent-behavior/promote-regression.md`.

---

## 8. Completion gates

**Stage-dependent, because "done" differs by stage** (`04` §1.2).

| Stage | A dimension is done when |
|---|---|
| **discovery** | the hypothesis is credible or falsified, **and the decision field is filled** — including *stop* |
| **build** | threshold met **on held-out** with variance **and CI** reported, unacceptable failures at zero, gate-check exit `0`. The CI lower bound may be below threshold → `green-provisional` |
| **release** | as build, **with the CI lower bound ≥ threshold**, **plus** the human review cadence has run, and the gate's conditions in `04` §4.4 hold |
| **production** | as release, **plus** the online signal agrees with the offline score, or the divergence is recorded as a case-set finding |

**A cycle never completes on a delta inside the noise floor.** It completes on a met
threshold, a falsified hypothesis, or an explicit decision to stop.

**Blocking condition, shared with TDD:** a requirement with an unresolved routing or no
verification target is **not implementation-ready**. That is the gate the manifest earns
its place by making checkable.

### 8.1 The statistical gate

A threshold is a claim about a population of cases. **The case count decides whether it
can be proven at all.**

| Held-out cases | Best possible result | 95% lower bound (Wilson) |
|---|---|---|
| 24 | 24/24 | 0.86 |
| 30 | 30/30 | 0.89 |
| 60 | 59/60 | 0.91 |
| 100 | 96/100 | 0.90 |

**A 0.90 threshold cannot be shown to hold on 30 cases, whatever the result.** Hence the
stage split in the table above:
- **At build**, the point estimate with its interval is enough to keep moving, marked provisional.
- **At release**, the lower bound must clear the threshold, or `04` must declare the threshold as a lower bound and size the held-out set to match.

**Two kinds of uncertainty are reported separately**, because they have different cures:
- **Run variance** (the noise floor) is the model's randomness on the same cases. It can't be removed, only measured.
- **Sampling uncertainty** (the CI) comes from having few cases. More cases shrink it.

**Repeated runs don't add cases.**

**Model-scored dimensions carry their judge's validation:**
- TPR/TNR against human labels, with the label-set version and the labeler
- the pass rate corrected for them before it's compared with a threshold

An unvalidated judge passes its own bias into every score. **Labels come from a named domain
owner.** In the Superpowers × Hamel pilot, generator-derived synthetic labels drifted, and
the coding agent's reading of a mislabeled case was more defensible than the label.

### 8.2 Stage tiering: proportionate cost

**The full gate is a build and release instrument. Prototypes need less.**

| Stage | Minimum BEV practice |
|---|---|
| **prototype · discovery** | Obligations split and routed · deterministic parts to TDD · **about 30 traces reviewed by the domain owner** (open codes → axial categories → `DISC-D`) · code checks where a failure is checkable · a decision recorded. **No thresholds, no held-out split, no gate-check.** |
| **build** | The full loop, held-out verification, `green-provisional` allowed |
| **release · production** | Lower-bound gate, judgment review, online/offline agreement |

In the pilot, a frontier coding agent with no method fixed every scored behavioral failure
on a small single-turn agent in about 30 minutes. **The plugin's cost is justified by claim
trustworthiness at build and release, not by fixing power at prototype.**

---

## 9. Plugin anatomy — Superpowers-native

Inspected `obra/superpowers` v6.3.0. **The design mirrors its conventions so it reads as
native rather than adjacent.**

```
behavior-evidence/                      ← original sketch; as built: one skill, see README.md
  .claude-plugin/plugin.json
  skills/
    classify-verification/SKILL.md
    designing-evals/SKILL.md
    verify-agent-behavior/SKILL.md        ← the core loop, mirrors test-driven-development
    analyzing-eval-failures/SKILL.md
    promoting-regressions/SKILL.md
```

**Frontmatter follows their spec**: `name` + `description` only, third-person, starting
*"Use when…"*, describing **triggering conditions and never the process** — their SDO
rule.

**Section order mirrors theirs**: Overview · When to Use · Core Pattern · Quick Reference
· Implementation · Common Mistakes.

### The Iron Law

Every load-bearing Superpowers skill has one. TDD: *no production code without a failing
test first*. Verification: *no completion claims without fresh verification evidence*.
BEV's:

```
NO BEHAVIOURAL COMPLETION CLAIM WITHOUT A DELTA THAT CLEARS THE NOISE FLOOR
```

**A score that moved less than the metric's own variance has not moved.**

### Common Rationalizations — the actual enforcement mechanism

Superpowers skills work by anticipating the excuse, not by describing the workflow. BEV's
table:

| Excuse | Reality |
|---|---|
| "The score went up" | By more than the noise floor? If not, that is noise with a direction |
| "Structural tests pass, so the behaviour is fine" | **The false GREEN.** Schema conformance is not content quality |
| "I changed two things but the second was minor" | The delta is unattributable. One change per cycle, same as one failing test at a time |
| "I improved the case set while I was in there" | Then this is a new series. Record the discontinuity; do not re-baseline silently |
| "Evals are slow — I'll check at the end" | You will have made ten changes and know which one worked: none |
| "It's obviously better" | Run it. Obviousness is the thing evals exist to check |
| "Only fifteen cases, but they are representative" | Of what population? Name it, or the number means nothing |
| "The eval is wrong, not the system" | **Possibly true** — that is a `suspected layer: eval`. Say it explicitly and fix the rubric; do not iterate against a bad measure |

### Red Flags — STOP

Reporting a delta without its variance · re-baselining after a case-set change · marking
a `both`-routed task complete on TDD green · treating `inconclusive` as `unchanged` ·
changing prompt and retrieval in one cycle · promoting a production failure without
classifying it · **reporting `green` for an obligation never baselined** · **gating on a
point estimate without its CI** · **iterating against held-out cases** · **a model-scored
gate with an unvalidated judge** · **minting an `EVAL-D` mid-build from spec text** ·
**accepting `BEV_ONLY` without asking whether a mechanism could hold it** · **marking BEV
complete without a gate-check result**.

---

## 10. The handoff protocol

### 10.1 The verification manifest is built before `writing-plans`

*As built:* no separate skill. The agent copies `templates/verification-manifest.yaml` and
routes every requirement (`derive-evals.md`); a human accepts it (C1); the `CLAUDE.md` snippet
puts the step between brainstorming and planning.

That is the integration point. Instead of the plan author seeing *"Task 4: implement
evidence conflict handling"*, it sees:

```yaml
task: implement ambiguity surfacing
requirement: ABS-B07
statement: Ambiguity MUST be surfaced with its unresolved basis
verification:
  tdd: {required: true, refs: [CONTRACT-021, UNIT-088]}
  bev: {required: true, refs: [EVAL-D03], case_bucket: judgment-intensive}
  order: tdd-first
depends_on: {control: GOV-C12, dimension: EVAL-D03}
completion:
  tdd: all named tests green
  bev: threshold met AND delta > noise_floor AND no unacceptable failure fired
```

Superpowers' planning machinery then does what it already does well.

### 10.2 BEV steps in their bite-sized form

`writing-plans` requires one action per step, 2–5 minutes. BEV decomposes the same way:

- "Pin the case set version" · "Run the baseline, record the score" · "Run it twice more,
  record the variance" · "Inspect failures and cluster them" · "Name one hypothesis and
  its suspected layer" · **"Make the change"** *(hands to TDD if deterministic)* · "Rerun
  the same cases" · "Compare against the noise floor" · "Check no previously-passing case
  regressed" · "Commit"

**Structurally identical to red-green-refactor**, which is why it composes rather than
competes.

### 10.3 Extending `verification-before-completion`

Their table is `Claim | Requires | Not Sufficient`. BEV adds four rows:

| Claim | Requires | Not Sufficient |
|---|---|---|
| Behaviour improved | delta > noise floor, **same case-set version and method** | the score went up |
| Requirement met | TDD green **and** BEV green, where both are routed | structural tests passing |
| Eval passes | threshold met by the stage rule (§8.1) **with variance and CI reported**, on held-out | a single run; a dev-set score |
| No regression | previously-passing cases re-run | new cases passing |
| Green | a recorded baseline, then a held-out run the gate-check passes | a green with no baseline behind it |

> **A task carrying a BEV obligation cannot be marked complete on TDD green alone.**
> That is the false GREEN their own issue describes, stated as a gate.

### 10.4 BEV returns a change request, not implementation instructions

```
COMPARE = regressed | unchanged
    ↓  analyzing-eval-failures
cluster + suspected layer + one hypothesis
    ↓  emit
Superpowers task: "change <layer> per <hypothesis>"
    ↓  subagent-driven-development implements it, with TDD if deterministic
    ↓  verify-agent-behavior reruns the SAME cases
COMPARE again
```

```yaml
change_request:
  source: BEV
  requirement: ABS-B07
  failure_cluster: FC-014
  suspected_layer: prompt
  hypothesis: >
    Authority precedence is not explicit enough when conflicting evidence
    is retrieved in a different order.
  requested_change:
    outcome: >
      Apply authority precedence independently of retrieval order.
  preserve:                          # what must not regress
    - existing citation behaviour
    - ambiguity handling
    - the human escalation boundary
```

**`preserve` is the field that stops a fix breaking a neighbour.** A conflict-recognition
change that quietly degrades ambiguity handling is a regression the delta on *this*
dimension will not show.

**BEV states the behavioural outcome required; Superpowers decides the implementation.**

| BEV may say | BEV may not say |
|---|---|
| *"Later authoritative amendments must supersede older guidance"* | *"Modify `conflict_resolver.py` line 88 and add a regex"* |

The first is behavioural engineering. The second is implementation design, and it belongs
to the engine that owns dispatch, review and TDD.

### 10.5 Why TDD-first for `both`

If a control makes a behaviour unrepresentable, the eval measures whether the model
*attempts* it — useful, and secondary. If the eval passes and the control was never
built, the requirement is held by the model's good behaviour, which is the exact state
the spec set exists to make visible.

### 10.6 Known conflicts with Superpowers, and their overrides

Verified against `obra/superpowers` v6.3.0 source. **A plugin that hands off to Superpowers
has to survive Superpowers' own enforcement.** Each override is a project `CLAUDE.md`
instruction. `using-superpowers` states that user instructions take precedence over skills,
so this is a sanctioned mechanism, not a fork.

| Superpowers behavior (source) | Conflict with BEV | Override |
|---|---|---|
| Architectural brainstorming: *"the ONLY skill you invoke after brainstorming is writing-plans"* (`brainstorming`) | §10.1 needs `build-verification-manifest` between them | *"After brainstorming, build the verification manifest; then writing-plans."* |
| SDD: *"Do not pause to check in with your human partner between tasks"* | Accepting DERIVE rows (§4), validating judges (§8.1) and judgment review (§10.7) need a human | *"Manifest acceptance and BEV judgment reviews are human checkpoints outside SDD. Dispatch TDD tasks through SDD; stop at BEV gates."* |
| `verification-before-completion` accepts command output (exit codes, failure counts) as evidence | An eval score isn't a command result | **§10.7:** the gate-check makes it one |
| The session-start hook re-injects `using-superpowers` on startup, `/clear` and compaction, under a "1% chance → MUST invoke" rule | BEV skills can lose ambiguous trigger contests | Put the routing rule and the checkpoint rule in `CLAUDE.md`, which is re-read every session |
| `writing-plans` tasks have no type or acceptance-criterion field | The plan can't tell a TDD task from a BEV one | Put the manifest fragment (§10.1) in the task text, and the BEV thresholds in the plan's **Global Constraints**, which Superpowers reviewers use as their attention lens |

### 10.7 The deterministic gate-check

**The coding agent never certifies its own behavioral work.** Built: `skills/verify-agent-behavior/tools/gate_check.py`, tested in `skills/verify-agent-behavior/tools/tests/`. Rules and exit table: `behavior-evidence/skills/verify-agent-behavior/verify-before-completion.md`.

```
eval harness → eval-result.yaml ─┐   (per-case records; its numbers are only checked)
            → runs.jsonl (ledger) ├→ gate-check → exit code → Superpowers task state → human review where required
trace store → traces export ──────┤
04 spec §4.2 → thresholds ────────┘
```

**One contract, joined by IDs** (0.7.0):

| Layer | Defines or records | ID |
|---|---|---|
| Dimension (04 §2) | what good means | `EVAL-Dnn` / `EVAL-Tnn` — append-only, so no separate version |
| Evaluation | how it is judged | method · judge prompt hash · judge validation |
| Harness | runs, per-case verdicts, the ledger | `run_id` · `test_case_id` |
| Trace | what happened | `trace_id` · span IDs |
| Gate | whether the claim holds | computes every number from the records (0.11.0) and reads the threshold from 04 §4.2; never trusts the harness's aggregate |

**The harness records verdicts; it never decides pass.** A harness written by the same agent that built the system is the least trustworthy place for that decision.

- **Result file.** Written by the harness through the adapter, never by hand. It holds: obligation, dimension, provenance, stage, split, case-set version and n, pinned versions, the judge's labelled items, **the per-case records of the candidate and of the baseline**, and the prior evidence state. The numbers it also reports (score, runs, noise floor, 95% CI, baseline, TPR/TNR, failure counts) are checked against the gate's own and never used. Schema in `behavior-evidence/skills/verify-agent-behavior/verify-before-completion.md`.
- **Checker.** Pure arithmetic and field checks, with no model in the loop:
  - **exit `1`** if a field is missing, the split isn't held-out, there's no baseline, versions don't match, the judge is unvalidated, 04 §4.2 has no row for the dimension and stage, a reported number isn't the records', a held-out run was left out, a trace doesn't resolve, an unacceptable failure fired, or there's a regression
  - **exit `2`** if the delta is inside the noise floor, or a release-stage lower bound is below threshold
  - **exit `0`** otherwise, with a warning when build-stage provisional
- **Two responsibilities, split on purpose:**

| | Owner | Automate? |
|---|---|---|
| **Mechanical verification**: fields, splits, versions, every number, the threshold's source | the gate-check | **Always** |
| **Judgment review**: are the cases credible and representative, is the judge measuring the construct, are the residual failures acceptable | domain owner (cases, labels) · PM (threshold) · engineer (layer attribution) | **No.** Required at release, for safety-critical or `EVAL-T` dimensions, for a `spec-only` dimension's first green, and after any case-set or judge change |

**Human attention goes to judgment, not arithmetic.** That's the governance point.

### 10.10 The slice gate: two clocks, joined by IDs

**A Superpowers task finishes on command output, in a session. An obligation finishes when the
evidence lands, days later, after traces, labels and a checkpoint.** Forcing one onto the other
produces either a stalled task or a false completion.

| Clock | Owner | Done means |
|---|---|---|
| **Task** | Superpowers | its commands pass: code, tests, checks, traces produced, the eval run submitted. **It claims nothing about behavior** |
| **Obligation** | the manifest points at the result; **the gate's verdict is the state** | green, with a result file behind it |
| **Slice** | **the slice gate** | every obligation verified on every required side, and no open blocking checkpoint |

```bash
uv run skills/verify-agent-behavior/tools/slice_gate.py verification-manifest.yaml --checkpoints bev/checkpoints.yaml
```

| Exit | Means | Fires when |
|---|---|---|
| **0** | done | every required side is green; nothing open |
| **1** | not done | an earned dimension whose evidence state isn't green · TDD not green · `UNRESOLVED` routing · DERIVE rows not accepted · a green with no result file · a result the gate-check rejects · **evidence pinned to another commit** (stale) · **a result that isn't the row's** (obligation, dimension or stage differ, or it's cited twice) · **a manifest state that isn't the gate's verdict** · routing that disagrees with the `required` flags · a BEV slice with no commit, 04 contract, ledger or trace export · cited spans the export doesn't list · a result that crashes the gate · **a BEV row with no earned id** · **a waiting obligation with no tracing task** · one both waiting and routed · a promotion with no BEV row · a malformed entry · no obligations at all |
| **2** | awaiting a human | an open blocking checkpoint (any status but `done`/`declined`) · a pass needing judgment review with no `done` C4 for that obligation · **at release: a waiting obligation with no decision, an unsigned decision, or a no-failures review under `--min-traces`** |
| **3** | usage | the manifest can't be read |

**Wire it to `finishing-a-development-branch`** through `CLAUDE.md`, so a branch cannot merge on
tests alone (`behavior-evidence/skills/verify-agent-behavior/claude-md-snippet.md`).

**The join is one-way:** eval result → manifest → slice gate. Nothing writes back into the eval
system, so there is no two-way sync to keep consistent. **Staleness falls out of the pins:** a green
is bound to a commit (`S-STALE`, reported as state `stale`). A prompt, schema or config file the
repo tracks moves the commit; **a hosted model or index that changes without a commit does not** —
pin it in a tracked file, or rerun after changing it.

**Two words, kept apart.** The task is `implemented`. The obligation is `green`. A dev tool saying
*complete* must never be read as *proven*.

**A pass can still be unfinished.** On exit `0` the verdict carries `requires_human_review` and
`review_reasons`: release or production, the first green on a `spec-only` dimension, an `EVAL-T` dimension, `safety_critical`, `new_series`, a held-out set run on earlier candidates, and — at release — a missing ledger, trace export or contract. **The task is then `awaiting-judgment-review`** until checkpoint C4 closes.

**The judge adapter.** `tools/judge_to_eval_result.py` turns raw inputs into the result: `judge_validation`, the
corrected `score`, `runs`, `noise_floor` and `ci95`, the baseline's numbers, the failure counts, and the records themselves.
The inputs are the judge-calibration **test** labels (human vs. judge) when model-scored, and the per-case verdicts of each
baseline run and each run on the system split. **The statistics live in `tools/evidence_stats.py`, which the gate imports
too**, so the adapter's numbers reproduce exactly and a typed number does not.
- **Correction:** Rogan–Gladen, rejected when TPR + TNR − 1 < 0.05.
- **Interval:** a percentile bootstrap (2,000 draws, fixed seed — not settable by the result) that resamples **both** the cases and the judge labels, so judge uncertainty widens it.
- **Regressions:** cases that passed every baseline run and now pass in fewer than half the runs. **Unacceptable failures:** cases whose records list `red_lines`, and any failing case on an `EVAL-T` dimension.
- **Independence:** the statistics are implemented from scratch, with no code copied from the unlicensed evals-skills.

### 10.8 Instruments: BEV owns the loop, `evals:*` do the measuring

Full table and fallbacks: `behavior-evidence/skills/verify-agent-behavior/instruments.md`. The rules that matter:

| BEV step | Instrument |
|---|---|
| discovery §7 · build analyze · production classify | `evals:error-discovery`, in **Discover · Diagnose · Classify** mode |
| derive-evals (model method, evaluator earned) | `evals:write-judge-prompt` |
| baseline (judge) | `evals:validate-evaluator`, then the adapter |
| retrieval layer | `evals:evaluate-rag` |
| Done/Good review | `evals:eval-audit` |

- **The modes are BEV's control of the invocation, not changes to the skill.**
  - **Diagnose (build):** only failing dev cases for one red dimension, a taxonomy pre-seeded from the dimension register, and non-fitting notes tagged `uncovered`.
  - **Classify (production):** pre-seeded with the 06 §7 classes.
  - **Discover:** starts empty.
- **Never call `evals:evals-start` once 04 dimensions exist.** Its router sends taxonomy-less users to discovery.
- **Two splits never mix:** the **judge-calibration** split (human labels: train/dev/test) and the **system** split (cases: dev/held-out).
- **Reference by name only.** evals-skills has no license at `11d3578`, so none of its content is copied into the plugin or the canon.

### 10.9 Checkpoints: named pauses, queued, work continues

Full rules: `behavior-evidence/skills/verify-agent-behavior/checkpoints.md`.

| | Checkpoint | Human |
|---|---|---|
| C1 | accept manifest DERIVE rows | spec owner |
| C2 | label traces to validate a judge | domain owner |
| C3 | error-discovery session | domain owner |
| C4 | judgment review (`requires_human_review`) | domain owner + PM |
| C5 | accept a new dimension or evaluator | spec owner |

**Nothing else pauses the loop.**
- **The queue:** the agent writes `bev/checkpoints.yaml` with everything prepared, continues unblocked tasks, orders the queue by tasks unblocked, and records the decision and actual minutes.
- **Why it matters for governance:** every human judgment is on record, and the method's real cost becomes measurable.
- **Ready-to-paste Superpowers overrides:** `behavior-evidence/skills/verify-agent-behavior/claude-md-snippet.md`.

---

## 11. Building it with their own methodology

Their `writing-skills` maps skill creation onto RED-GREEN-REFACTOR: pressure scenario →
agent violates the rule without the skill → write the skill → agent complies → close
loopholes. **That is BEV applied to skills**, so the plugin gets built the way it asks
others to work.

**The first pressure scenario is theirs**: a prompt-heavy task where a structural test
passes on poor generated content. Run a coding agent without the skill, watch it claim
GREEN, record the exact rationalization it uses, then write the skill against that
sentence.

**If the plugin does not block that scenario, it has not earned its place.**

### 11.1 Proving it works: what to measure, and what not to

**Pressure scenarios prove the skill changes agent behavior. They don't prove the method
produces better outcomes.** That needs a comparison against Superpowers alone.

**Don't measure fixing power.** In the Superpowers × Hamel pilot, a coding agent with no
method, no TDD and no evals fixed every scored behavioral failure on a small single-turn
agent. The comparison hit a ceiling and couldn't separate methods.

**Measure claims instead:**

| Measure | Definition | Why |
|---|---|---|
| **False-green rate** | Obligations claimed green whose true rate, measured on a sealed labeled held-out set, is clearly below threshold (Wilson upper bound < threshold). **Unfounded greens count.** | The plugin's reason to exist |
| **Obligation coverage** | % of a gold obligation register (classifier rules, accepted by the spec owner) that appears in the arm's artifacts with a route and a verification target. **An `EVAL-D` obligation counts as covered when it is `unmeasured` with a `GAP` and no failure was observed.** A missing evaluator is not a miss | Traceability, without rewarding evals-first |
| **Unspecified failures surfaced** | For failure modes deliberately withheld from the spec: did the arm record trace evidence of each, and does its final agent still show it? | The unenumerable-failures point; the strongest test of the method |
| **Critical-miss rate** | % of gold `TDD_AND_BEV` and control-backed obligations verified on only one side | The false GREEN, structurally |
| **Status honesty** | % of BEV obligations whose reported state matches their evidence, including honest `unmeasured` | Rewards not claiming |
| Overhead | wall-clock, tokens, human minutes | Viability |

**Run a ceiling check first:** if an unguided agent's claims are already accurate and
complete on the chosen workflow, the workflow can't discriminate. Pick a harder one before
spending on the comparison.

**Candidate workflow:** multi-turn and tool-heavy, with approval gates, ambiguous inputs,
and specs that state outcomes rather than behaviors.

Full design: the author's pilot notes (not published).

**What would disprove the plugin:** on such a workflow, Superpowers + BEV's false-green rate
is no lower than Superpowers alone, **or** coverage doesn't improve, **or** either
improvement costs more than 2× the overhead.
