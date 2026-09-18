# derive-evals

Turn a behavioral obligation into evaluable cases — and, **only when earned**, an evaluator.
**Read first; the spec usually already answers most of this.**

---

Read the governing `ABS-B*` clause and its `verified_by` field (02 §3.3).

**If `verified_by` names an `EVAL-D*` or `EVAL-T*`, that dimension already exists.**
Go to `baseline.md`. Do not create a second one.

**If it reads `unverified` with a `GAP`**, the obligation is waiting for failure data. For a quality
dimension that is legitimate (`DOD-02-05`), and **it is not slice work**: list it on the manifest's
`unmeasured[]` with a **tracing task** (a TDD ticket that makes the behavior visible in traces), build
the system, and come back here when error analysis shows a failure.

**If it is empty with no `GAP`, stop.** Report it as a `02` defect. For a red line or a control,
resolve the verifier before writing code; for a quality clause, record `unverified` + `GAP`.

**If the dimension exists but has no cases**, continue below.

## What to build before any failure, by dimension type

**"Don't write evals before failures are observed" is a rule about quality evaluators, not about all
eval work.** Some things must exist before the first failure, or the failure either can't be seen or
is seen too late.

| Dimension type | Examples | **Build before any failure** | **Waits for observed failures** | Why |
|---|---|---|---|---|
| **Controls and mechanisms** (`GOV-C`) | approval gate · a tool that refuses a safety booking · a schema with no determination field | the mechanism **and its deterministic tests** (TDD) | nothing | crystal clear; TDD-shaped |
| **Red lines** (`EVAL-T`) | never mention competitors · never book an unapproved safety test · no fabricated citation | the check (code where possible, else a judge with explicit Pass/Fail) plus adversarial cases | refining a judge's wording as edge cases appear | the exception: the criterion is clear up front |
| **Quality** (`EVAL-D`) | grounding · tone · useful clarifying questions · right test chosen | named obligation (or `unverified` + `GAP`) · tracing · test inputs · a provisional `DISC-D` hypothesis · **a scheduled error analysis** (below) | **the evaluator**: judge, threshold, labels, gate | failure modes can't be enumerated; evaluators written first measure imagined failures |
| **RAI: hard constraints** | PII leakage · prohibited inputs (age, sex, disability, race) · no denial by software · AI disclosure · regulatory rules | **controls and red-line tests, as above** · probing cases (adversarial, injection) | nothing | high severity: waiting for failure data means waiting for harm. Canon: 02 §3.3 *At discovery* makes 01 §6 RAI obligations firm prohibitions from the start |
| **RAI: distributional** | fairness · subgroup disparity · uneven error rates across populations | **the measurement plan**: the attributes or proxies to stratify by, subgroup sample sizes, telemetry that records them, the disparity metric's definition | **the scorer and its threshold**, once stratified data exists | a disparity lives in the distribution, not in any single trace. **Unstratified error analysis will never find it** |
| **RAI: human reliance** | automation bias · rubber-stamping · over-trust · override quality | **instrumentation**: override rate, time on case, citations opened before acceptance; floors and alarms (06 §6) | thresholds tuned on real use; usability-tested dimensions (04-disc §2) | it only shows in how people use the system, and capture has to be designed in, not bolted on |
| **Operational** | latency · cost per case · abandonment | SLIs and telemetry (06 §5) | targets refined against the baseline | deterministic measurement |

### The rule underneath: severity × detectability

| | **Visible in trace review** | **Invisible in a single trace** |
|---|---|---|
| **High severity** | build the evaluator or control **first** | build the **measurement plan first**; the scorer follows the data |
| **Lower severity** | **earn the evaluator** from observed failures | monitor in production (06); periodic review |

### The waiting list is not a place to hide

Taking the obligation out of the slice removes its reminder, so the `unmeasured[]` entry carries one:
- **A trigger** — a trace count or a date — that queues a C3 error-analysis session. It never blocks the build.
- **Error analysis on roughly 100 traces before release**, sampled for diversity, reviewed by the domain owner.
- **A decision before release**, which the slice gate requires:

| Decision | Needs | Means |
|---|---|---|
| `no-failures-observed` | reviewer · `traces_reviewed` · a C3 the reviewer closed (`decision.checkpoint`, or the trigger's `error_analysis.checkpoint`) | 0 failures in n traces bounds the rate **only below 3/n** (rule of three). 100 clean traces supports "under 3%", not "zero" |
| `deferred-to-production` | approver · the `06` monitor that will watch it · a C4 the approver closed (`decision.checkpoint`) | accepted risk, on record |
| `promoted` | the new `EVAL-*` id, and its BEV row in the manifest | failures earned an evaluator (C5); it is slice work now |

## Is an evaluator earned yet?

**Name the obligation up front. Build the evaluator when it's earned.** Writing evaluators for
failures nobody has seen measures imagined failures — the practice Husain and Shankar argue against
in *"Should I practice eval-driven development?"*.

| Situation | Build an evaluator now? |
|---|---|
| A red line (`EVAL-T`) or a control (`GOV-C`) — the criterion is crystal clear | **Yes, first.** It's TDD-shaped |
| An RAI hard constraint | **Yes, first** — as a control and red-line tests |
| An RAI distributional dimension | **The measurement plan now**; the scorer when stratified data exists |
| A quality dimension, and error analysis has shown it failing in traces | **Yes** — if the cost-benefit line below says so |
| A quality dimension nobody has seen fail | **No.** List it on `unmeasured[]` with a tracing task; review traces as the system runs |
| A single failure that a fix and a regression case would settle | **No.** Fix it (`analyze-failures.md`, disposition *fix-only*) |

**Cost-benefit, one line, before any evaluator:** *how often it fails · what a failure costs · will
we iterate on it · cheapest check that would catch it.* If a code check catches it, write the code
check. A model judge is the most expensive option — about 100 human labels to validate — so it is the
last resort, and it needs a C2 checkpoint (`checkpoints.md`).

## Check provenance before anything else

**Where did this dimension come from?**

| Provenance | Treat as |
|---|---|
| Promoted from `DISC-D` (`04-discovery` §9), with failures observed in traces and a measured baseline | **Established.** Use it. |
| Written in `04` from spec text, and nobody has looked at traces | **Provisional.** Baseline it on real traces first. Expect to re-set the threshold, re-scope it, or split it. Record `provenance: spec-only` in the eval result. |
| Proposed by you, mid-task | **Not a dimension yet.** Route it by stage (`analyze-failures.md`): at discovery a `DISC-D`; at build a `04` change request for a new append-only ID; in production through `06` §7. Stop until it's accepted. |

**Criteria brainstormed before looking at outputs measure what someone imagined would go
wrong.** Failure modes observed in traces measure what actually does.

## Can a mechanism hold this instead?

Before deriving an eval, ask whether the behavior could be made unrepresentable: a schema
state, a hard block, a forced action, or a tool that refuses. **If yes, PROPOSE a control
to `05`**, routed to TDD, with human acceptance required. The eval then only measures
whether the model *attempts* the forbidden thing. That's the TDD-first rule for `both`,
applied one step earlier.

## Decide which kind

- **`EVAL-T`** — pass/fail. Something that must never happen, or must always hold.
- **`EVAL-D`** — scored. Something graded, with a threshold and a variance.

**A control that scores is a broken control.** If the clause names a `GOV-C*`, its
verification is a test, not a dimension.

**An `EVAL-D` score is the rate of a binary verdict** — the share of cases passing one Pass/Fail
criterion. **Never an average of 1–5 ratings**: reviewers disagree on a 3 versus a 4, and a judge
inherits the disagreement. One failure mode, one criterion, one verdict per case.

## Choose the cheapest check that works

| Method (04 §2) | Use when | Instrument |
|---|---|---|
| **deterministic** | the failure is checkable from output and fixture — schema, regex, value in range, ID exists | code, written test-first |
| **model** | the criterion needs interpretation — tone, grounding, whether a question is the right one | `evals:write-judge-prompt` (fallback below), then judge validation in `baseline.md` |
| **human** | neither, or the construct is still being learned | the domain owner, through a C3 session |

**Many failures that look subjective reduce to a code check once you understand the domain.** Try
that first.

**A model judge, if you write one without the instrument:** one failure mode per judge · explicit
Pass and Fail definitions drawn from observed failures · 2–4 few-shot examples from the
judge-calibration **train** labels only · a written critique **before** the verdict · structured output.

## Name the construct

State two things and the gap between them:

- what you want to know
- what you can actually score
- **where they differ**

*Want: is the brief truthful. Can score: does each claim trace to a supporting source.
Gap: a claim can be grounded and irrelevant.*

A dimension whose construct is unexamined measures its own proxy.

## Propose cases

**12–30 for a new dimension. Not hundreds.** Cover:

| Bucket | |
|---|---|
| clean | the common representative case |
| judgment-intensive | where reasonable reviewers could differ |
| adversarial | built to break it |
| **near-miss** | superficially similar but **must not** fire |

**The near-miss bucket is the one that gets skipped**, and without it a system that
flags everything scores perfectly.

For each case state: what it exercises, the expected behavior, whether a critical
failure is possible, and **who labeled the expected behavior**. Synthetic labels drift, so
a domain owner adjudicates the judgment-intensive and near-miss buckets.

## Split the cases before you use them

| Split | Used for | Rule |
|---|---|---|
| **dev** | baseline, analysis, experiments | Iterate freely |
| **held-out** | `verify-before-completion` only | **Never used to choose a change.** Looking at its failures to decide what to fix turns it into dev. |

**A set you tuned against can't verify the tuning.** That's the eval version of testing on
training data.

## Size the set for the gate, not just for discovery

12–30 cases is enough to *find* failures. **It is not enough to *prove* a threshold.**

| Cases | Best possible result | 95% lower bound (Wilson) |
|---|---|---|
| 24 | 24/24 | 0.86 |
| 30 | 30/30 | 0.89 |
| 60 | 59/60 | 0.91 |
| 100 | 96/100 | 0.90 |

With 30 cases, **no result can show a 0.90 threshold is met.** Either grow the held-out set
toward the gate's needs, or state the stage gate on the point estimate with its interval
reported, marked **provisional** (see `verify-before-completion.md`). Don't imply precision
the case count can't support.

**Repeated runs don't add cases.** Five runs of one case tell you about the model's
randomness on that case, not about the population of cases.

## For a detection requirement, recall is the metric

False positives are bounded by structure. **False negatives from model judgment are
invisible** — a missed case produces output that looks clean. Score recall against a
labelled set, or the miss rate is an assumption.

## Do not

- invent a dimension the spec did not ask for
- write cases from the implementation you are about to build
- set a threshold before you have a baseline and its noise floor
- treat a spec-only dimension as established before it has met real traces
- let the held-out split influence a change
- gate on an LLM judge whose TPR/TNR against human labels hasn't been measured
- build a quality evaluator before traces have shown the failure
- score with a Likert scale
- reach for a model judge where a code check would do
