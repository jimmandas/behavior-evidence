# behavior-evidence (BEV) — evidence for agent-behavior claims

A Claude Code plugin. **The name says what it does:** a claim that an agent behaves
acceptably is done only when the evidence behind it holds. **It is not eval-driven
development.** Evaluators are earned from observed failures, not written first. **Superpowers' TDD proves deterministic mechanisms; BEV proves
probabilistic behavior.** A vertical slice of an agentic workflow holds both kinds of
ticket. This plugin covers the kind TDD can't prove: which tool the agent picks, whether
its answers are grounded, when it escalates.

**Status: 0.15.0, design-stage. Not yet behaviorally proven.**
- The tools are tested: 354 tests, plus deliberate-break checks.
- The skill has not been exercised in a live slice. The pilot that would have tested it
  was stopped.
- Design and rationale: `docs/design.md`.
- Evidence behind it: the author's Superpowers × Hamel evaluation (not published); the
  upstream issues it cites are named in `docs/design.md` and `ONE-PAGER.md`.

## What it does

| Piece | What it enforces | How |
|---|---|---|
| **Skill** `behavior-evidence:verify-agent-behavior` | The behavioral loop: baseline → analyze individual failures → one change → compare against the noise floor → verify once on held-out cases | Instructions, loaded when a change touches prompts, retrieval, orchestration, model or judge config, or a behavioral requirement |
| **`gate_check.py`** | Whether one behavioral claim holds | Deterministic, with no model in the loop. **Computes every number itself** from per-case records (score, interval, noise floor, baseline, regressions, judge TPR/TNR), reads the threshold from 04 §4.2, and checks the run ledger and the trace store. **Its exit code is the evidence** Superpowers' `verification-before-completion` accepts |
| **`slice_gate.py`** | Whether a vertical slice is done | Joins tasks, obligations, evidence and human checkpoints by ID. Wire it in before merge |
| **`judge_to_eval_result.py`** | Writes the result from the harness's per-case verdicts | Judge TPR/TNR against human labels, bias-corrected pass rate, noise floor, a bootstrap CI that includes judge uncertainty — with `evidence_stats.py`, the same code the gate recomputes with |

**Core rules the tools hold:**
- **The obligation is named up front; the evaluator is earned.** A quality dimension gets an
  evaluator only after error analysis shows it failing. Until then it waits on the
  manifest's `unmeasured[]` list, **outside the slice**. The build owes it only tracing.
  Red lines and controls are built first.
- **The harness records verdicts; it never decides pass.** The gate computes every number
  from `run_id` · `test_case_id` · `trace_id` · binary verdict · cited spans, and the threshold
  comes from 04, not from the result.
- **Nobody copies a state.** The slice gate derives each obligation's evidence state from its
  result.
- **Every held-out run counts.** A result that leaves out a run of the same candidate is
  invalid, which stops rerunning until you get a green.
- **Every claimed run must have a trace.** A trace ID the trace store doesn't hold is invalid
  evidence.
- **A pass is not always done.** These queue a human judgment review (C4): release or production, the first green on a `spec-only` dimension, an `EVAL-T` dimension, `safety_critical`, `new_series`, a held-out set run on earlier candidates, and — at release — a missing ledger, trace export or contract.

## What it does not do

- **It doesn't run your agent or your judge.** Your eval harness does, and it writes the files
  the gates read (`RUNBOOK.md` §2). `tools/bev_harness.py` does the logging and recording for it;
  `tools/export_traces.py` turns an OpenTelemetry export into the trace file.
- **It doesn't host traces.** Where traces live is your data-residency decision. The gate
  reads an export.
- **It doesn't hash-lock your eval artifacts** (dimension definitions, judge prompts,
  thresholds, held-out cases) during a slice. That's an open decision. Until it's made, pin
  them by review.
- **It ships one hook, and only for custody.** `hooks/protect_evidence.py` stops the agent from
  writing the evidence directories and the protected spec files (thresholds, judge prompts, held-out
  cases) named in the project's `.claude/bev.json`; without that file it does nothing. Routing goes in your project `CLAUDE.md` (the snippet below). Nothing is injected
  into every session.

## Requirements

- Claude Code (checked with 2.1.263)
- [`uv`](https://docs.astral.sh/uv/) and Python ≥ 3.9. Each tool declares PyYAML in its script
  header, and `uv run` installs it.
- **Recommended:** [obra/superpowers](https://github.com/obra/superpowers), checked against
  v6.3.0 (`b36e082`). BEV is written as its peer.
- **Optional:** Husain & Shankar's
  [evals-skills](https://github.com/ai-evals-course/evals-skills), used as measurement
  instruments (`skills/verify-agent-behavior/instruments.md`). **That repo has no LICENSE
  file; clear it with legal before use at work.** This plugin copies no code from it.
- The spec set these files cite (`01`–`07`, `ABS-B*`, `EVAL-D*`, `GAP-*`) is the author's spec
  template set, not published. Read those IDs as "your requirement" and "your dimension";
  `examples/slice/` shows the parts of the evaluation spec (`04`) the gates read.

## Install

**As an installed plugin, from GitHub.** Run these from the consuming project's root, at
project scope. The default scope is `user`, which would install it for every project.

```bash
claude plugin marketplace add jimmandas/behavior-evidence --scope project
```

```bash
claude plugin install behavior-evidence@jimmandas --scope project
```

**Per session, nothing installed:** clone the repo and point a session at it.

```bash
git clone https://github.com/jimmandas/behavior-evidence.git
```

```bash
claude --plugin-dir ./behavior-evidence
```

**Then in each project:** paste
`skills/verify-agent-behavior/claude-md-snippet.md` into the project's `CLAUDE.md`. It
resolves the known Superpowers conflicts:
- the brainstorming → plan lock
- unattended subagent-driven development versus human checkpoints
- trigger contention with `evals:*`

**Check it loaded:**

```bash
claude plugin validate ./behavior-evidence
```

Inside a session, the skill appears as `behavior-evidence:verify-agent-behavior`.

## Layout

```
behavior-evidence/
├── .claude-plugin/plugin.json
├── hooks/                        hooks.json · protect_evidence.py (custody; dormant without .claude/bev.json)
├── README.md                     this file
├── RUNBOOK.md                    how to run a slice with it
├── examples/slice/               a worked slice; RUNBOOK.md walks through it
└── skills/verify-agent-behavior/
    ├── SKILL.md                  the loop, evidence states, routing, rationalizations
    ├── derive-evals.md           routing at build; when an evaluator is earned; building one
    ├── baseline.md               measure before you change; pins; noise floor; CI
    ├── analyze-failures.md       individual failures → disposition (fix-only · code check · evaluator)
    ├── run-experiment.md         one change, same cases, compared
    ├── promote-regression.md     observed failure → behavioral regression test (m of k)
    ├── verify-before-completion.md  held-out run, result schema, gate exit table
    ├── checkpoints.md            C1–C5: the only reasons to pause for a human
    ├── instruments.md            which evals:* skill each step calls
    ├── claude-md-snippet.md      paste into the consuming project
    ├── templates/                verification-manifest.yaml · eval-result-template.yaml
    └── tools/                    gate_check · slice_gate · judge_to_eval_result · evidence_stats ·
                                  bev_harness (run log + records) · export_traces (OTLP → trace export) ·
                                  checkpoints (open / close the queue) · tests/
```

## Run the tests

```bash
cd "$BEV/skills/verify-agent-behavior"
uv run --with pytest --with pyyaml pytest tools/tests -q
```

## Known limits

- **Unproven in a live slice.** The skill's text is instructions, and upstream Superpowers
  issues show instructions get skipped (#2286, #1749, #1900). The gates are the enforcement,
  and they only bite if the slice gate runs before merge.
- **Garbage in, green out, within limits.** The gate checks that the records are consistent,
  complete and traceable. It can't check that the judge prompt, the cases or the labels
  are good. That's checkpoint C4, a human.
- **The ledger and the trace export are only as honest as their custody.** The hook blocks the
  agent's own edits and shell commands on the evidence directory; it can't stop a program the
  agent writes and runs elsewhere. For custody that holds against a determined agent, run evals
  in CI (05 §10.3, independent custody). The docs don't confirm hooks apply under
  `--dangerously-skip-permissions`; don't run BEV slices that way.
- **The slice gate needs a commit, the 04 contract, a run ledger and a trace export** for any
  slice with a BEV row. Run standalone, `gate_check.py` only warns about a missing ledger or trace export at
  build; at release it requires human review.
- **Cost.** An LLM-judged dimension needs about 100 human labels to validate its judge, and at
  least 3 held-out runs per verification.

## Version history

See `docs/design.md` (the *Changed in* entries).
