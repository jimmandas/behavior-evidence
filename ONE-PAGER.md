# Behavior-evidence plugin — partner one-pager

**2026-09-18 · Jim Mandas.** A one-page summary for partners and reviewers.

## 1. The goal

**A PM builds a working agentic workflow with AI agents — and can prove what is actually done.**

The toolchain: Claude Code with the Superpowers skill set, Python, and a spec set that states what the workflow
must do. Superpowers gives a coding agent real discipline — brainstorm, plan, write the failing test, make it
pass, review, merge. For deterministic work (a tool wrapper, a schema, a state transition, an approval gate)
that cycle is enough: a test passes or it doesn't.

A vertical slice (a thin end-to-end piece of the workflow, built and merged as a unit) holds a second kind of work: **agent behavior.** Which tool the agent picks. Whether it asks
the requester or escalates. Whether it holds its ground when someone says "just book it." That varies run to
run, so one pass/fail test cannot settle it. It needs a rate over many runs, and where a model does the scoring,
a judge whose agreement with human labels has been measured.

**The goal, narrowly:** move at agent speed on the deterministic half, without the behavioral half shipping on an
unproven claim.

## 2. The problem

**Some behavioral dimensions have no failure data yet. The spec names the obligation; nothing can measure it.**

An LLM's failure surface can't be listed in advance. Husain and Shankar put it plainly: write evaluators for
failures you have observed, not failures you imagine. So at the start of a slice, each obligation (a requirement the slice must meet) splits
three ways:

| Kind | Example | Can it be measured now? |
|---|---|---|
| Deterministic | The booking schema rejects an unknown test id | Yes — a test |
| Behavioral, **earned** | "Picks the right one of two similar tests" — failures already seen in traces | Yes — a rate with a threshold |
| Behavioral, **no failure data** | "Asks rather than escalating" — nobody has seen it fail yet | **No** |

The third kind is smaller than it looks. Most behavioral dimensions are earned before the slice, in discovery: run
the agent on synthetic cases and read the failures. One that first fails mid-build is promoted into the slice
through a change a human accepts. What is left is the obligations that haven't failed anywhere yet. For those,
the slice has two honest options, and one dishonest one:

1. **Carry it in the slice as unmeasured.** The obligation is visible, but the slice can never finish: the failure
   data needs the slice running, and the slice waits on the data. A deadlock.
2. **Leave it out of the slice.** Keep it on a named list with one build obligation attached — emit the traces
   that would show the failure — and earn the evaluator later, from real clusters.
3. **Write an evaluator up front anyway.** It looks rigorous and measures imagined failures. This is the common
   failure and the one to avoid.

Superpowers has no answer here, and its maintainers say so: it has nothing like eval-driven development, and its
test-first skill is explicitly binary pass/fail (obra/superpowers issue #1671, closed as out of scope for the
core). Related open issues show the consequence: a check on a prompt's output format counts as done (#1900), and
agents followed a skill's process without ever running the model to see whether the fix worked (#2292).

## 3. The plugin: behavior-evidence

**A Claude Code plugin that sits beside Superpowers and decides when a behavioral claim may be called done.**
Superpowers proves mechanisms with tests; this proves behavior with evidence. Same slice, two kinds of proof.

What it does:

1. **Routes every obligation at slice start.** Deterministic work goes to test-first. An earned behavioral
   dimension gets a measured claim. An obligation with no failure data leaves the slice onto an `unmeasured`
   list, carrying one build task: emit the traces that would show the failure, plus a trigger to look at them.
   **That is option 2 above, enforced.**
2. **Computes the numbers itself.** The eval harness records one result per case per run — case id, trace id,
   pass or fail, the judge's reasoning, the trace spans it cites. The gate recomputes the pass rate, the
   run-to-run noise, the confidence interval, the judge's agreement with human labels, and the regressions.
   Numbers the harness reports are only checked. A forged interval is rejected. The interval resamples by case,
   not by run, so repeat runs of one case aren't counted as independent evidence; judge agreement is measured as
   its true-positive and true-negative rates on human labels; the pass rate is corrected for those error rates
   (Rogan–Gladen), and the bootstrap resamples the judge's labels too, so the interval carries the judge's own
   uncertainty.
   What recomputing can't catch is forged per-case records — that is custody (item 6, risk 3).
3. **Reads the threshold from the spec, not the result.** The number lives in the eval spec a human owns, and
   the hook stops the agent editing that file — a threshold change goes to a person.
4. **Checks that the runs happened.** Every run is logged before it runs; a result that omits a failing run of
   the same candidate is invalid. Every claimed run must resolve to a real trace in the trace store. So rerunning
   the same commit until green fails, and so does a run with no trace behind it. Two limits: runs made outside
   the harness aren't seen, and rerunning across commits until one passes is flagged, not blocked.
5. **Blocks the merge, not the task.** A coding task finishes on its command output; the *slice* finishes only
   when every obligation is green with evidence pinned to the current commit.
6. **Keeps the evidence out of the agent's casual reach.** The run log, traces and the human review queue live outside
   the repo; a hook stops the agent writing them. The agent can open a review request; only a named person can
   close one.

**Benefits, tied to the goal:**

- **A PM can say "done" and show why.** Every behavioral claim resolves to cases, traces and a threshold someone
  owns — or the gate refuses it.
- **Speed is kept where it's safe.** Deterministic work keeps running at agent speed under Superpowers; only
  behavioral claims pay the measurement cost.
- **No false greens from the easy half.** A slice with a green test suite and unproven behavior cannot merge.
- **An audit trail falls out of the work.** Who decided, on what evidence, at which commit — which is what a
  governed workflow needs, and what a PM is usually asked for after the fact.

### How it works: the skill, and when it fires

The plugin is **one skill, seven small tools, one hook, and two templates.** The skill is the method a coding
agent follows; the tools are the part that doesn't depend on the agent cooperating.

**What Claude Code loads, and when.** At session start it reads only the skill's one-paragraph description — a
few hundred characters. The model loads the body when it judges the work fits that description, so the method
costs nothing until it applies. That is a judgment, not a trigger. The description names:

- **slice start** — after brainstorming, before planning
- **any change that affects behavior** — prompt, retrieval, orchestration, model or judge configuration
- **implementing a behavioral requirement** from the behavior spec
- **deterministic tests passing while behavioral quality is unproven**
- **someone claiming a change improved things without measuring**, or a score moving without anyone checking the
  run-to-run noise

Because the model may not invoke it, a short block pasted into the project's own instructions
(`claude-md-snippet.md`) makes the routing explicit and survives session restarts. Neither is enforcement: the
gates are.

**Where it sits in the Superpowers cycle:**

1. **Brainstorm** (Superpowers) — unchanged.
2. **Route the obligations** (this skill, `derive-evals.md` + the manifest template) — every requirement goes to
   test-first, to a measured behavioral claim, or onto the `unmeasured[]` list with a tracing task. **A human
   accepts that routing** (checkpoint C1) before any planning.
3. **Plan and build** (Superpowers: `writing-plans`, `subagent-driven-development`, TDD, review) — unchanged,
   including the tracing tasks the routing added.
4. **Baseline** (`baseline.md`) — measure the behavior before changing anything, on cases the harness logs as it
   runs.
5. **Analyze, change, compare** (`analyze-failures.md`, `run-experiment.md`, `promote-regression.md`) — read
   individual failures, not the average; one change per hypothesis; rerun the same cases; most failures turn out
   to be plain bugs that get a fix and a regression case rather than a new metric.
6. **Verify and merge** (`verify-before-completion.md`) — the gate decides each behavioral claim; the slice gate
   decides the merge.

**The tools, and when each runs:**

| Tool | Runs |
|---|---|
| `bev_harness.py` | While the harness runs: logs each run before it happens, records every case |
| `export_traces.py` | After runs: turns the trace store's OTLP export into the file the gates check against |
| `judge_to_eval_result.py` | After a run: computes the statistics (`evidence_stats.py`) and writes the result |
| `gate_check.py` | On each behavioral claim: recomputes every number, reads the threshold from the eval spec, exits pass / fail / inconclusive. **That exit code is the evidence Superpowers already accepts** (its `verification-before-completion` skill takes command output as proof) |
| `slice_gate.py` | Before the merge, from `finishing-a-development-branch`: every obligation, on every required side, pinned to the current commit |
| `checkpoints.py` | Whenever a human is needed: the agent opens a request, a named person closes it |
| `protect_evidence.py` (hook) | On every file write and shell command: refuses the agent's writes to the evidence and to the spec files that hold the thresholds |

**What you need to use it:** an eval harness you run on your own cases, a trace store that exports OpenTelemetry
(OTLP JSON), a domain expert to label traces, and CI to make the gate unavoidable (planned). Install steps are in
`README.md` and `RUNBOOK.md`; `examples/slice/` is a worked example — spec, runs, traces and a result to run the gate on.

**Five human checkpoints (C1–C5), and nothing else stops the work:** accept the routing · label traces to
validate a judge · sit with the failures · review a pass before it counts as done · accept a new dimension.
Each is queued with what the person needs already prepared; unblocked work continues meanwhile.

## 4. Evidence so far

**Built and tested: 354 automated tests, and the custody hook verified blocking in a live session** — including
an agent told to lower a threshold from 0.90 to 0.85, which it could not do. Not yet
proven: that the plugin beats Superpowers alone — that comparison was designed, then deliberately not run.

The one piece of behavioral data comes from a multi-turn test-request triage agent (synthetic data, 100 cases ×
3 runs, 2026-09-17):

| Result | Count |
|---|---|
| Correct outcome | 229 of 300 |
| Bookings with the wrong test, or a value the requester never gave | **0** |
| Wrong outcomes that escalated instead of asking the requester | **57 of 71** |
| Runs that ended with no outcome at all | 13 |
| Booked a test after the requester refused the only available date | 1 |

**Read it both ways.** The agent never tried to book a wrong test or an invented value, and every approval was
present. The code controls blocked 9 booking attempts — all formatting ("PV build" for `PV`), each corrected on
the next try — so this run shows the agent got the checkable part right, not that the controls rescued it. Every
remaining failure was behavior that varies run to run — escalating instead of asking,
going silent, and once overriding a refusal. Each was scored by code against the case's known answer, and each
needs a rate over runs: **a one-run test would have passed or failed it by chance.** The refusal override is
different — it is a gap in the agent's controls: a code check on the conversation's state should have blocked
that booking. That is
the case for the plugin, and the case against over-building it: write the deterministic controls first — they are
cheap and they are what stops the checkable failures when an agent does make them.

## 5. Top three challenges and risks

**1. The agent may not follow the method.** The gates are deterministic code and hold. The skill that tells the
agent to route obligations, baseline before changing, and analyze failures is *instructions*, and upstream
Superpowers issues show agents skipping instructions under pressure: claiming done on evidence they generated
themselves (#2286), and fabricating subagent work (#1749). **Mitigation (planned, not built):** the gate in
continuous integration (CI) on the merge, so compliance is not required — the merge simply fails. We have no CI
yet (risk 3); until then the gate runs only when the agent or a person runs it. **Open:** the skill's own behavior has
never been measured; a plugin eval suite would do it.

**2. Measurement costs human time, and there is no way around it.** A judge that scores behavior must be checked
against human labels, and a release-grade number needs roughly 200 labels and 120 cases per dimension (estimated
from the fixtures, not measured on real data). The person who can label is the domain expert, whose time is the
scarce resource. **Mitigation:** build-stage provisional claims need far less, and the method says which
dimensions deserve a judge at all — most failures are plain bugs and just need a fix plus a regression case.
**Open:** at scale, who labels, and against which rubric.

**3. The evidence is only as good as its custody, and the comparison is unproven.** The hook stops the agent
editing the run log, traces, review queue and threshold spec casually; it cannot stop a program the agent writes
and runs itself, and the gates cannot see runs made outside the harness. Full custody means running evals in continuous integration, which we do not have yet. Separately, the
claim that this beats Superpowers alone rests on design reasoning and one uncontrolled run, not a comparison.
**Mitigation:** adopt on a real slice and watch one number — did the gate ever refuse a claim we would otherwise
have shipped? Two or three slices with no refusal means the machinery is not paying for itself.
