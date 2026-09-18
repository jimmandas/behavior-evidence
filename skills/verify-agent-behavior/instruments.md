# instruments

**BEV owns the loop and the gate. Measurement instruments do the measuring.** This file says which
instrument each BEV step calls, how it is called at each stage, and what BEV does with its output.

The instruments here are Hamel Husain and Shreya Shankar's **evals-skills** (`evals:*`, plugin
`evals`). **Reference them by name; never copy their content into this plugin or the spec set**
— the repository carries no license (checked at `11d3578`). Every step below has a manual
fallback, so BEV works without them installed.

---

## Which instrument, at which step

| BEV step | Instrument | What BEV takes from it | Fallback if not installed |
|---|---|---|---|
| discovery §4 cases, no traces yet | `evals:generate-synthetic-data` | test **inputs** only — BEV buckets and expected behavior still apply | write the tuples by hand, domain owner reviews 20 |
| discovery §7 failure analysis | `evals:error-discovery` in **Discover** mode | open codes → axial categories → `DISC-D` / `DISC-F` candidates | a spreadsheet of traces and free-text notes |
| `derive-evals` — an **evaluator** is warranted and the Method is `model` | `evals:write-judge-prompt` | one binary Pass/Fail judge per failure mode, critique before verdict | the judge rules in `derive-evals.md` |
| `baseline` — judge validation | `evals:validate-evaluator` | TPR / TNR on the **judge-calibration** test labels | label and count by hand |
| `baseline` / `verify` — the numbers | `tools/judge_to_eval_result.py` (this plugin) | corrected score, runs, noise floor, 95% CI → `eval-result.yaml` | — |
| `analyze-failures` at build | `evals:error-discovery` in **Diagnose** mode | clustered failures on one red dimension | read the failing traces directly |
| `analyze-failures`, suspected layer `retrieval` | `evals:evaluate-rag` | retrieval scored apart from generation | — |
| production learning event (06 §7) | `evals:error-discovery` in **Classify** mode | a class and a route per failure | manual triage against the taxonomy |
| Done / Good review of 04-disc or 04 | `evals:eval-audit` | findings: brainstormed criteria, unvalidated judges, Likert scales | the DoD critique |

**Never call `evals:evals-start` from BEV.** It routes someone with no taxonomy to discovery. Once
dimensions are promoted, that is the wrong answer — call the specific skill.

## Two splits — never confuse them

| | Judge-calibration split | System split |
|---|---|---|
| Splits | **human labels** | **cases** |
| Parts | train (few-shot) · dev (iterate the judge) · test (measure TPR/TNR once) | dev (iterate the system) · held-out (verify once) |
| Owned by | `evals:validate-evaluator` | BEV |
| Feeds | `judge_validation.items` in `eval-result.yaml` (the gate recomputes TPR/TNR from them) | `split`, the per-case records the gate recomputes `score` and `ci95` from |

**A judge test label is never a held-out case, and a held-out case is never a few-shot example.**

## `error-discovery` has three modes — BEV chooses by stage

The mode follows `04 §1.1 Stage`. The skill itself is unchanged; BEV controls **the data it is given,
the taxonomy it starts from, and where the output goes.**

| Mode | Stage | Traces in | Starting taxonomy | Output | Never |
|---|---|---|---|---|---|
| **Discover** | discovery | a diverse sample — cluster representatives plus random | **empty** — let axial coding emerge | `DISC-D` / `DISC-F` candidates (`provenance: DISC-promoted` at §9) | — |
| **Diagnose** | build · release | **only the failing dev cases** for **one** red dimension, plus a few near-miss passes | **pre-seeded** with that `EVAL-D` definition and its known clusters | rows for `analyze-failures.md`; any note that fits no dimension tagged **`uncovered`** | held-out traces · new taxonomy entries · `evals-start` |
| **Classify** | production | sampled traces behind a 06 signal — breach, drift, complaint | **pre-seeded** with 06 §7 classes and 04 §2 dimensions | a class and route per failure | treating an unclassified failure as a case |

**Pre-seeding.** The review app holds its taxonomy in `patterns.json`. Before the human starts,
write the starting taxonomy there — dimension name, definition, known clusters with example trace
IDs. The human's notes are then organized against the contract instead of rebuilding it.

**`uncovered` is not a new category.** In Diagnose mode it becomes a candidate for a `04` change
request (C5 in `checkpoints.md`), with its cost-benefit line (`analyze-failures.md`).

**When `uncovered` notes cluster — three or more pointing the same way — stop diagnosing.** That is
evidence about the requirement or the bet, not the implementation: reopen the `02` clause, or
return to discovery.

## Human-in-the-loop instruments are checkpoints

`error-discovery` is interactive and `validate-evaluator` needs human labels. **Neither runs inside an
unattended implementation loop.** Queue them (`checkpoints.md` C2, C3), prepare everything the human
needs, and continue with unblocked work. In a non-interactive session, `error-discovery` builds the
review app and stops — that is the ready-for-review state, not a failure.
