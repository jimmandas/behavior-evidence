# analyze-failures

Read the failed cases. **Do not modify the implementation yet.**

---

**Do not optimize the aggregate score before examining individual failures.** The
aggregate tells you something is wrong. It never tells you what.

## Read each failure

For every failed case, read the actual output and trace. Not the score. Not a summary.

**At build and release, use the Diagnose mode of `evals:error-discovery`** (`instruments.md`):
- **Traces in:** only this dimension's failing **dev** cases, plus a few near-miss passes.
- **Taxonomy:** pre-seeded with the dimension's definition and known clusters.
- **Notes that fit no dimension:** tagged `uncovered`.
- **Human:** only if your own reading ends at `unknown` or `eval`. Then queue C3.

**Never Diagnose on held-out traces.**

## Cluster by observed failure mode

Group failures that share a mechanism, not a symptom. Two cases failing for different
reasons are two clusters.

## For each cluster

| | |
|---|---|
| Affected behavioral requirement | `ABS-B*` |
| Affected eval dimension | `EVAL-D*` / `EVAL-T*` |
| **Suspected layer** | `prompt · retrieval · tool · orchestration · control · UX · data · eval · unknown` |
| **Evidence** for that classification | what in the trace supports it |
| **One falsifiable hypothesis** | |
| Smallest experiment that would test it | |
| **Disposition** | `fix-only · code check · evaluator` — see below |

## Decide the disposition before building anything

**Most failures found in error analysis are bugs. Fix them.** Building an evaluator for every
failure is how teams drown in metrics that don't move quality.

| Disposition | When | What you produce |
|---|---|---|
| **fix-only** | clear cause, clear fix, unlikely to recur once fixed | the fix, **plus a regression case** (`promote-regression.md`). No new dimension, no judge |
| **code check** | the failure is checkable from output and fixture, and could recur | a deterministic check written test-first; it runs with the suite |
| **evaluator** | the failure persists, costs enough to matter, or will be iterated on — **and** needs interpretation | a model judge or human review; **cost-benefit line required**; a C5 checkpoint if it's a new dimension, C2 for the labels |

**Cost-benefit line** (required for *evaluator*): *frequency · cost of a failure · will we iterate ·
why no cheaper check catches it.*

## The hypothesis must be falsifiable

**Good:** *"Conflict recognition fails when the authoritative source appears second,
because the prompt prioritises first-found evidence."*

**Not a hypothesis:** *"Improve the prompt."* *"The model is weak here."* *"Needs better
retrieval."*

If you cannot state what would prove it wrong, keep reading failures.

## `unknown` is a valid answer

Forcing a layer produces false confidence and wastes the next cycle. If the evidence
doesn't support a classification, say `unknown` and propose an experiment that would
discriminate.

## `eval` is a real layer

If the rubric was wrong, the expected behavior was mis-specified, or the case was badly
chosen — **the defect is in the eval, not the system.** No amount of implementation
change will move the score. Say so explicitly; it is one of the more valuable findings
and the one teams are least willing to reach for.

## A failure no dimension covers

You'll find failures the spec never anticipated. **That's the point of reading traces.** Don't
invent an `EVAL-D` for one mid-task. **Where it goes depends on the stage**, because the IDs and
authority differ:

| Stage | A new failure mode (no dimension covers it) | A failure an existing dimension already covers | Classify first? |
|---|---|---|---|
| **prototype · discovery** | **Open code → axial category → new `DISC-D` or `DISC-F`** in `04-discovery`. These IDs are temporary; renumber freely. This *is* discovery's job. | Add a `CASE-nn` to the `DISC-D` | Yes. That's the axial coding, done by the domain owner |
| **build** | **A `04` change request.** Propose a new `EVAL-D` or `EVAL-T` with trace evidence and case IDs. `04` is append-only: **a new mode is a new ID, and a changed definition is a new ID**. Human acceptance required. **Never back into `DISC-*`**: those IDs stopped existing at promotion. | **`04` §6.1 regression capture.** Promote the case (`promote-regression.md`). | No. The eval or test that found it already labels it |
| **production** | **`06` §7 learning loop.** Classify against the failure taxonomy, then route: behavior wrong → `02` clause change → `04` case; control missing → `05`; measurement wrong → the rubric; **bet wrong → back to discovery** | **`04` §6.2 production-derived promotion** | **Yes. It arrives unlabeled.** |

**At any stage, a cluster of new modes pointing the same way is a signal about the requirement,
not the implementation.** At build that means reopening `02`, or going back to discovery
if the product bet is wrong, before minting more dimensions.

**Failure modes observed in traces are the dimensions worth having.** The routing is what
keeps them from becoming one-off, unreviewed criteria.

## Before recommending a code change

Ask whether the failure routes beyond the implementation — to `01`, `02`, `03`, `04`,
`05` or `06`. **Several failures revealing a wrong requirement means reopen the
requirement**, not keep coding until the eval passes.
