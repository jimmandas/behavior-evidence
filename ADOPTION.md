# Adopting behavior-evidence without a pilot

**Decision (Jim, 2026-09-17): adopt. The controlled pilot is cancelled**.
Evidence comes from real builds instead: use the plugin on the next agentic workflow, gates first.

This is what "adopt" means in practice, what to watch, and what would make you drop it.

## What you are adopting, and what is unproven

| Piece | State |
|---|---|
| `gate_check.py`, `slice_gate.py`, `evidence_stats.py`, `bev_harness.py`, `export_traces.py`, `checkpoints.py` | **Built and tested:** 354 tests; every deliberate break of a rule caught. Deterministic, no model in the loop |
| The custody hook | **Verified in a live headless session** (2026-09-17): a Write into the evidence directory and a shell append were blocked, `checkpoints.py close` was blocked, the project's own files stayed writable |
| The skill (`verify-agent-behavior`) and the checkpoints | **Unproven.** Instructions an agent may skip — the failure mode the upstream Superpowers issues document (#2286, #1749, #2292). Nothing has run a slice through them |
| The claim that BEV beats Superpowers alone | **Not measured.** Pilot 1 showed a frontier agent fixes what it can see with no method at all; the argument for BEV is trustworthy claims, not fixing power |

## How to start: gates before instructions

1. **Pick a real slice** with at least one behavioral obligation that a test can't settle.
2. **Set up custody first** (RUNBOOK §2): an evidence directory outside the repo, `.claude/bev.json` naming it
   and the spec file that holds the thresholds, and the plugin loaded so the hook is live. Without custody the gates check evidence the agent could have written.
3. **Write the 04 §4.2 row** for each earned dimension — the threshold lives in the spec, not in a result.
4. **Have the harness use `bev_harness.py`** so every run is logged before it runs, and `export_traces.py`
   for the trace export from the trace store.
5. **Run `gate_check.py` on each behavioral claim, and `slice_gate.py` before the merge.** That is the whole
   mechanism. If you adopt nothing else, adopt this.
6. **Add the skill and the `CLAUDE.md` snippet second**, once the gates are habitual. Then the routing,
   `unmeasured[]` list and checkpoints have something to gate against.

**Stage tiering (design §8.2) still applies:** at prototype stage, obligations split and routed, a domain
owner reading ~30 traces, code checks where a failure is checkable — no thresholds, no held-out split, no
gate. The full loop is a build and release instrument.

## What to watch, and the numbers behind it

**The discovery run of 2026-09-17** (TVR v2 multi-turn triage agent, Haiku 4.5, 100 synthetic cases × 3 runs;
instrument kept in the author's sandbox, not published) is the only behavioral data we have. It
was collected to test whether a realistic slice produces judgment failures near threshold. It does:

| Result | Number |
|---|---|
| Correct outcome | 229 of 300 |
| Case types with a mixed (neither 0% nor 100%) rate | 10 of 13 |
| **Wrong outcomes that escalated instead of asking the requester** | **57 of 71** |
| Runs that ended with no outcome at all | 13 |
| Booked a test after the requester refused the only available date | 1 |
| Bookings with the wrong test, or with values the requester never gave | **0** |

**Read that carefully, because it is the case for the plugin and the case against over-building it.**
- **Every ticket it created was correct.** Code checks — the schema, the ranges, the approval gate — caught
  everything they can catch, and the agent never invented a value or booked the wrong test.
- **The failures are all in behavior that no test can see:** escalating instead of asking a question it could
  have asked, going quiet, and once booking against the requester's express refusal. A passing test suite
  would have called that slice done.
- **So:** deterministic controls are worth building first and they work. **What they can't see is what BEV is
  for.** A judgment dimension like "asks rather than escalating" would have started `unmeasured`, earned an
  evaluator from these clusters, and gated the claim.

## What would make you drop it

- **The gates never fail a claim you would have shipped.** After two or three real slices, if nothing was
  caught, the machinery isn't paying for itself — keep the harness and the trace discipline, drop the rest.
- **The agent routinely ignores the skill** and you end up running the gates by hand. Then keep the gates as
  CI, drop the skill.
- **The label cost doesn't clear.** A release-grade lower bound needs roughly 200 judge labels and 120 cases
  per dimension (inferred from the fixtures, not measured on real data). If nobody can spend that, stay at
  build-stage provisional greens and say so out loud.
- **Custody can't hold.** The hook stops casual tampering, not a program the agent writes and runs. If the
  evidence has to be trustworthy against a determined agent, move the runs to CI.

## Open items carried from the reviews

- **Protecting the 04 artifacts — decided (Jim, 2026-09-18), step 1 done.** The hook blocks the agent's edits to
  the files listed as `protected_files` (the spec with its thresholds; add judge prompts and held-out cases).
  Step 2, with CI: the slice gate compares thresholds against a hash recorded when the spec was accepted, so any
  change needs a named approver.
- Three spec follow-ups: spec 04 has no home for its "deliberately unmeasured" list; 02 §2 wording on how
  `DISC-D` dimensions arise; the author guide's routing table lacks the earned/provisional step.
- The 04 trace-requirements proposal, drafted in the author's spec repo, not applied.
- No `claude plugin eval` suite for the plugin itself.
