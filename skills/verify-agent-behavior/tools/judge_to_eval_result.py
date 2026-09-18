#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml"]
# ///
"""Turn per-case verdicts (and, for a model judge, its labelled items) into an eval result.

    uv run <skill>/tools/judge_to_eval_result.py judge-run.yaml --template eval-result-template.yaml --out eval-result.yaml

Computes, with evidence_stats.py (the same code the gate-check re-derives with):
  - judge TPR / TNR on the judge-calibration TEST items (never the system split), when given
  - the pass rate per run, corrected for the judge's errors (Rogan–Gladen) when model-scored
  - score (mean corrected rate), noise_floor (half the run spread)
  - a 95% bootstrap interval resampling the cases and, when model-scored, the judge's labels
  - the baseline score from its records, the regressions and the unacceptable failures

and copies the records into the result, so the gate can recompute every number.

Input (judge-run.yaml) — written by your eval harness, keyed by ID, never by position:

    judge_validation:           # omit for a deterministic or human-scored dimension
      labels: v2                # label-set version
      items:                    # the judge TEST split: human and judge verdict per item (1 = Pass)
        - {item_id: lab-0001, human: 1, judge: 1}
    baseline_runs:              # the baseline, measured before any change; same case set
      - run_id: base-0917
        cases: [...]            # same shape as below
    runs:                       # one entry per run over the SYSTEM split (held-out at verification)
      - run_id: run-8421
        cases:
          - test_case_id: pa-eligibility-014
            trace_id: trace-71ab
            verdict: 0                         # binary, per case
            critique: Two claims not supported by retrieved evidence.
            evidence_span_ids: [span-18, span-24]
            red_lines: []                      # optional: red lines this case tripped
    threshold: 0.90             # optional; the gate reads the real one from 04 §4.2

The statistics are the published Rogan–Gladen estimator and a percentile bootstrap. This file
implements them independently; it copies no code or text from any third-party skill.

Exit codes: 0 written · 3 invalid input (the gate-check was never reached).
"""

from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence_stats as es  # noqa: E402
from evidence_stats import MIN_INFORMATIVENESS, StatsError, alignment, corrected_rate  # noqa: E402,F401

EXIT_OK, EXIT_INVALID = 0, 3
RECORD_KEYS = ("test_case_id", "trace_id", "verdict", "critique", "evidence_span_ids", "red_lines")


class AdapterError(ValueError):
    pass


def _records(runs: list, order: tuple) -> list[dict]:
    out = []
    for r in runs:
        by_id = {c["test_case_id"]: c for c in r["cases"]}
        out.append({"run_id": r["run_id"],
                    "cases": [{k: by_id[i][k] for k in RECORD_KEYS if k in by_id[i]} for i in order]})
    return out


def build(doc: dict) -> dict:
    runs, base_runs = doc.get("runs") or [], doc.get("baseline_runs") or []
    if any("verdicts" in (r or {}) for r in runs + base_runs):
        raise AdapterError("runs must list `cases` with test_case_id, trace_id and verdict — positional `verdicts` are not accepted")
    jv = doc.get("judge_validation")
    if jv is not None and ("human" in jv or "judge" in jv):
        raise AdapterError("judge_validation must list `items` with item_id, human and judge — positional arrays are not accepted")
    if not runs:
        raise AdapterError("at least one run is required")
    if not base_runs:
        raise AdapterError("baseline_runs are required: the gate recomputes the baseline and the regressions from them")
    try:
        ids, rows = es.aligned(runs, "runs")
        base_ids, base_rows = es.aligned(base_runs, "baseline_runs")
        if base_ids != ids:
            raise AdapterError("baseline_runs score different cases from runs")
        pairs = es.label_pairs(jv.get("items")) if jv is not None else None
        s = es.summarize(rows, pairs)
        base_rates = es.run_rates(base_rows, s.get("tpr"), s.get("tnr"))
    except StatsError as e:
        raise AdapterError(str(e)) from e

    r3 = lambda x: round(x, 3)  # noqa: E731
    result = {"score": r3(s["score"]), "runs": [r3(x) for x in s["runs"]],
              "noise_floor": r3(s["noise_floor"]), "ci95": [r3(x) for x in s["ci95"]]}
    if "threshold" in doc:
        result["threshold"] = doc["threshold"]
    out = {
        "result": result,
        "baseline": {"score": r3(sum(base_rates) / len(base_rates)), "runs": [r3(x) for x in base_rates],
                     "run_ids": [r["run_id"] for r in base_runs], "records": _records(base_runs, ids)},
        "runs": _records(runs, ids),
        "case_set_n": len(ids),
        "_aligned": (ids, rows, base_rows),
    }
    if pairs is not None:
        out["judge_validation"] = {"tpr": r3(s["tpr"]), "tnr": r3(s["tnr"]), "labels": jv.get("labels"),
                                   "test_n": len(pairs), "items": list(jv["items"])}
    return out


def merge(template: dict, built: dict) -> dict:
    out = copy.deepcopy(template)
    case_set = out.setdefault("case_set", {})
    if case_set.get("n") not in (None, built["case_set_n"]):
        raise AdapterError(f"template case_set.n={case_set['n']} but the runs scored {built['case_set_n']} cases")
    case_set["n"] = built["case_set_n"]
    if "judge_validation" in built:
        out["judge_validation"] = built["judge_validation"]
    out["result"] = {**(out.get("result") or {}), **built["result"]}
    out["baseline"] = {**(out.get("baseline") or {}), **built["baseline"]}
    out["runs"] = built["runs"]
    ids, rows, base_rows = built["_aligned"]
    out["regressions"] = len(es.regressions(ids, base_rows, rows))
    out["unacceptable_failures"] = len(es.unacceptable(out.get("dimension", ""), built["runs"], ids, rows))
    return out


def main(argv: list[str] | None = None) -> int:
    import yaml  # declared in the script header; `uv run` installs it

    ap = argparse.ArgumentParser(description="per-case verdicts (+ judge validation) -> eval-result fields")
    ap.add_argument("judge_run", type=Path)
    ap.add_argument("--template", type=Path, help="eval-result template holding the non-statistical fields")
    ap.add_argument("--out", type=Path, help="write here instead of stdout")
    args = ap.parse_args(argv)
    try:
        built = build(yaml.safe_load(args.judge_run.read_text()))
        out = merge(yaml.safe_load(args.template.read_text()), built) if args.template \
            else {k: v for k, v in built.items() if not k.startswith("_")}
    except (AdapterError, OSError, yaml.YAMLError, AttributeError, TypeError) as e:
        print(f"INVALID  {e}", file=sys.stderr)
        return EXIT_INVALID
    text = yaml.safe_dump(out, sort_keys=False)
    if args.out:
        args.out.write_text(text)
    else:
        print(text)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
