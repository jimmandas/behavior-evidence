#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml"]
# ///
"""BEV gate-check: decide whether an eval result may move a behavioral obligation to green.

    uv run <skill>/tools/gate_check.py eval-result.yaml [--contract 04-evaluation-spec.md]
        [--ledger runs.jsonl] [--traces traces.jsonl] [--json] [--min-judge-alignment 0.8]

Deterministic. No model in the loop. The exit code is the evidence Superpowers'
verification-before-completion accepts; an agent's say-so is not.

Exit codes
    0  pass          -> green, or green-provisional at build (warning printed);
                        if requires_human_review is true the task is awaiting-judgment-review, not done
    1  fail          -> invalid evidence (state unchanged) or behavioral failure (red)
    2  inconclusive  -> delta inside the noise floor, or release/production lower bound below threshold
    3  usage         -> unreadable input, or a stage the gate does not apply to (discovery)

**The gate computes every number itself.** From the per-case records (`runs[]` and
`baseline.records[]`) and, when model-scored, the judge's labelled items, it derives the judge's
TPR/TNR, the run rates, the score, the noise floor, the 95% interval, the baseline score, the
regressions and the unacceptable failures (evidence_stats.py, shared with the judge adapter).
Numbers the result reports are checked against those, and a mismatch is invalid evidence; the
verdict never uses them. With --contract the threshold and method are read from 04 §4.2, never
from the result. With --ledger it checks that the baseline and every verification run were
logged and none was left out. With --traces it checks that every claimed run happened.

Rules: ../verify-before-completion.md. Design: docs/design.md §8.1, §10.7.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence_stats as es  # noqa: E402

EXIT_PASS, EXIT_FAIL, EXIT_INCONCLUSIVE, EXIT_USAGE = 0, 1, 2, 3

STAGES = {"discovery", "build", "release", "production"}
SPLITS = {"dev", "held-out"}
METHODS = {"deterministic", "model", "human"}
PROVENANCE = {"DISC-promoted", "spec-only", "build-observed", "production-derived"}
STATES_BEFORE = {"unmeasured", "red", "inconclusive", "green-provisional", "green", "stale"}

REQUIRED = [
    ("obligation",), ("dimension",), ("provenance",), ("stage",), ("split",), ("method",),
    ("case_set", "version"), ("case_set", "n"), ("versions",),
    ("baseline", "case_set_version"), ("baseline", "method"), ("evidence_state_before",),
]

# Findings whose presence means the evidence itself cannot be trusted: the state stays unchanged.
INVALID_EVIDENCE = {"F-MISSING", "F-ENUM", "F-NOT-HELD-OUT", "F-NO-BASELINE", "F-PIN-MISMATCH",
                    "F-JUDGE-UNVALIDATED", "F-TOO-FEW-RUNS", "F-RANGE", "F-CONTRACT",
                    "F-NO-RECORDS", "F-RECORDS", "F-RECOMPUTE", "F-TRACE-MISSING", "F-SPAN-MISSING",
                    "F-RUN-NOT-LOGGED", "F-RUNS-OMITTED", "F-LEDGER-COMMIT"}

MIN_ALIGNMENT_FLOOR = 0.5   # --min-judge-alignment can't go below this
TOLERANCE = 0.002           # a reported number vs. the gate's (3-decimal rounding)


@dataclass
class Finding:
    code: str
    severity: str  # fail | inconclusive | warning | note | usage
    message: str


@dataclass
class Verdict:
    exit_code: int
    evidence_state_after: str
    findings: list[Finding] = field(default_factory=list)
    obligation: str | None = None
    dimension: str | None = None
    requires_human_review: bool = False  # checkpoint C4: a pass that is not yet "done"
    review_reasons: list[str] = field(default_factory=list)
    computed: dict = field(default_factory=dict)  # the numbers the verdict rests on

    def to_dict(self) -> dict:
        return asdict(self)


_MISSING = object()


def _get(doc: dict, path: tuple[str, ...]) -> Any:
    cur: Any = doc
    for key in path:
        if not isinstance(cur, dict) or key not in cur or cur[key] is None:
            return _MISSING
        cur = cur[key]
    return cur


def _num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _close(a: Any, b: float) -> bool:
    return _num(a) and abs(a - b) <= TOLERANCE


# --------------------------------------------------------------------------- the contract

def parse_threshold(cell: str, dimension: str) -> float | None:
    """`≥ 0.92` · `>= 0.92` · `0.92` · `92%` → 0.92; `violations = 0` (or any EVAL-T zero) → 1.0."""
    text = (cell or "").strip().strip("`")
    if not text:
        return None
    if "violation" in text.lower() or (dimension.startswith("EVAL-T") and re.fullmatch(r"[=\s]*0", text)):
        return 1.0
    m = re.search(r"(\d+(?:\.\d+)?)\s*(%?)", text)
    if not m:
        return None
    value = float(m.group(1)) / (100 if m.group(2) else 1)
    return value if 0 <= value <= 1 else None


def load_contract(path: Path) -> dict:
    """04 §4.2 *Offline contract* → {(dimension, stage): {"threshold", "method"}}."""
    lines = path.read_text().splitlines()
    start = next((i for i, l in enumerate(lines) if re.match(r"^#+\s*4\.2\b", l)), None)
    if start is None:
        raise ValueError(f"{path}: no '4.2' section")
    header, rows = None, {}
    for line in lines[start + 1:]:
        if line.startswith("#"):
            break
        if not line.strip().startswith("|"):
            if header is not None and rows:
                break
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None:
            header = [c.strip("`").lower() for c in cells]
            continue
        if all(set(c) <= set("-: ") for c in cells):
            continue
        row = dict(zip(header, cells))
        dim = cells[0].strip("`").strip()
        stage = row.get("stage", "").strip("`").strip().lower()
        if not dim.startswith("EVAL-") or not stage:
            continue
        rows[(dim, stage)] = {"threshold": parse_threshold(row.get("threshold", ""), dim),
                              "method": row.get("method", "").strip("`").strip().lower() or None}
    if header is None:
        raise ValueError(f"{path}: §4.2 has no table")
    return rows


# --------------------------------------------------------------------------- checks

def _check_traces(doc: dict, record_sets: list, trace_index: dict | None, add, reasons: list[str]) -> None:
    if trace_index is None:
        if doc["stage"] in ("release", "production"):
            reasons.append("trace IDs not resolved against the trace store")
        else:
            add("W-TRACES-UNRESOLVED", "warning", "no --traces index: the runs' trace IDs were not checked against the trace store")
        return
    missing, spans, unchecked = [], [], 0
    for runs in record_sets:
        for r in runs:
            for c in r["cases"]:
                known = trace_index.get(c["trace_id"], _MISSING)
                if known is _MISSING:
                    missing.append(c["trace_id"])
                elif known is not None:
                    spans += [f"{c['trace_id']}/{s}" for s in c.get("evidence_span_ids") or [] if s not in known]
                elif c.get("evidence_span_ids"):
                    unchecked += 1
    if missing:
        add("F-TRACE-MISSING", "fail", f"{len(missing)} trace ID(s) not in the trace store, e.g. {missing[0]}: a claimed run with no trace")
    if spans:
        add("F-SPAN-MISSING", "fail", f"{len(spans)} cited span(s) not in their trace, e.g. {spans[0]}")
    if unchecked:
        add("W-SPANS-UNCHECKED", "warning", f"{unchecked} case(s) cite spans but the trace export lists none for their trace: the citations were not checked")


def _check_ledger(doc: dict, base_ids: list[str], ledger: list | None, add, reasons: list[str]) -> None:
    if ledger is None:
        if doc["stage"] in ("release", "production"):
            reasons.append("no run ledger: nothing shows these are all the held-out runs, or that the baseline was run")
        else:
            add("W-NO-LEDGER", "warning", "no --ledger: a failing held-out run left out of this result would go unseen")
            add("W-BASELINE-UNCHECKED", "warning", "no --ledger: nothing shows the baseline was actually run")
        return
    commit = (doc.get("versions") or {}).get("commit")
    if not commit:
        add("F-LEDGER-COMMIT", "fail", "versions.commit is required to match the result against the run ledger")
        return
    entries = [e for e in ledger if isinstance(e, dict)]

    # The baseline: logged runs, tagged `purpose: baseline`, on the same series at an earlier commit.
    base = doc["baseline"]
    ok_base = {e.get("run_id") for e in entries if e.get("purpose") == "baseline"
               and e.get("dimension") == doc["dimension"] and e.get("split") == "held-out"
               and e.get("case_set_version") == base.get("case_set_version") and e.get("commit") != commit}
    if set(base_ids) - ok_base:
        add("F-NO-BASELINE", "fail", "baseline runs must be logged held-out runs with `purpose: baseline` for this "
            f"dimension and case set at an earlier commit; unresolved: {sorted(set(base_ids) - ok_base)}")

    # The verification runs: logged, held-out, this series, this commit, not tagged as baseline.
    series = [e for e in entries if e.get("dimension") == doc["dimension"] and e.get("split") == "held-out"
              and e.get("case_set_version") == doc["case_set"]["version"] and e.get("purpose") != "baseline"]
    logged = {e.get("run_id") for e in series if e.get("commit") == commit}
    claimed = {r["run_id"] for r in doc["runs"]}
    if claimed - logged:
        add("F-RUN-NOT-LOGGED", "fail", f"run(s) not logged as held-out runs of this candidate "
            f"({doc['dimension']}, {doc['case_set']['version']}, {commit}): {sorted(claimed - logged)}")
    omitted = sorted(logged - claimed)
    if omitted:
        add("F-RUNS-OMITTED", "fail", f"held-out run(s) of this candidate left out of the result: {omitted}")
    earlier = {e.get("commit") for e in series if e.get("commit") != commit}
    if earlier:
        reasons.append(f"held-out set {doc['case_set']['version']} was run on {len(earlier)} earlier candidate(s): "
                       "check it was not used to choose a change")


def _check_reported(doc: dict, got: dict, add) -> None:
    """Every number the result reports must be the one the records give."""
    res, base, jv = doc.get("result") or {}, doc["baseline"], doc.get("judge_validation") or {}
    wrong = []
    for name, reported, value in (("result.score", res.get("score"), got["score"]),
                                  ("result.noise_floor", res.get("noise_floor"), got["noise_floor"]),
                                  ("baseline.score", base.get("score"), got["baseline_score"]),
                                  ("judge_validation.tpr", jv.get("tpr"), got.get("tpr")),
                                  ("judge_validation.tnr", jv.get("tnr"), got.get("tnr"))):
        if reported is not None and value is not None and not _close(reported, value):
            wrong.append(f"{name} {reported!r} vs {value:.3f}")
    for name, reported, values in (("result.runs", res.get("runs"), got["runs"]),
                                   ("result.ci95", res.get("ci95"), got["ci95"]),
                                   ("baseline.runs", base.get("runs"), got["baseline_runs"])):
        if reported is not None and not (isinstance(reported, list) and len(reported) == len(values)
                                         and all(_close(a, b) for a, b in zip(reported, values))):
            wrong.append(f"{name} {reported!r} vs {[round(v, 3) for v in values]}")
    for name, value in (("unacceptable_failures", len(got["unacceptable"])), ("regressions", len(got["regressions"]))):
        reported = doc.get(name)
        if reported is None:
            continue
        if not isinstance(reported, int) or isinstance(reported, bool) or reported < 0:
            add("F-RANGE", "fail", f"{name}={reported!r} must be a non-negative integer")
        elif reported != value:
            wrong.append(f"{name} {reported} vs {value}")
    if base.get("run_ids") is not None and list(base["run_ids"]) != got["baseline_run_ids"]:
        wrong.append(f"baseline.run_ids {base['run_ids']!r} vs the records' {got['baseline_run_ids']}")
    if wrong:
        add("F-RECOMPUTE", "fail", "reported numbers the records don't give: " + "; ".join(wrong))


def _threshold(doc: dict, contract: dict | None, add, reasons: list[str]) -> float | None:
    reported = (doc.get("result") or {}).get("threshold")
    dim, stage = doc["dimension"], doc["stage"]
    if contract is None:
        if not _num(reported) or not 0 <= reported <= 1:
            add("F-MISSING", "fail", "no --contract and no numeric result.threshold: nothing to gate against")
            return None
        if stage in ("release", "production"):
            reasons.append("threshold taken from the result, not read from 04 §4.2")
        else:
            add("W-THRESHOLD-UNPINNED", "warning", "no --contract: the threshold came from the result, not from 04 §4.2")
        return float(reported)
    row = contract.get((dim, stage))
    if row is None:
        add("F-CONTRACT", "fail", f"04 §4.2 has no row for {dim} at stage {stage!r}: the threshold lives there and nowhere else")
        return None
    if row["threshold"] is None:
        add("F-CONTRACT", "fail", f"04 §4.2's threshold for {dim} at {stage} can't be read")
        return None
    if row["method"] and row["method"] != doc["method"]:
        add("F-CONTRACT", "fail", f"04 §4.2 says {dim} is scored by {row['method']!r}, the result says {doc['method']!r}")
    if reported is not None and not _close(reported, row["threshold"]):
        add("F-CONTRACT", "fail", f"result.threshold {reported!r} is not 04 §4.2's {row['threshold']}")
    return row["threshold"]


# --------------------------------------------------------------------------- the verdict

def evaluate(doc: Any, min_judge_alignment: float = 0.8, ledger: list | None = None,
             trace_index: dict | None = None, contract: dict | None = None) -> Verdict:
    min_judge_alignment = max(min_judge_alignment, MIN_ALIGNMENT_FLOOR)
    if not isinstance(doc, dict):
        return Verdict(EXIT_USAGE, "unchanged", [Finding("U-INPUT", "usage", "eval result must be a mapping")])

    f: list[Finding] = []
    add = lambda code, sev, msg: f.append(Finding(code, sev, msg))  # noqa: E731
    got: dict = {}

    def verdict(code: int, state: str) -> Verdict:
        return Verdict(code, state, f, doc.get("obligation"), doc.get("dimension"), computed=got)

    if doc.get("stage") == "discovery":
        add("U-NOT-APPLICABLE", "usage", "discovery is not threshold-gated: record the decision in 04-discovery §8 instead")
        return verdict(EXIT_USAGE, "unchanged")

    # --- structure ---
    missing = [".".join(p) for p in REQUIRED if _get(doc, p) is _MISSING]
    if missing:
        add("F-MISSING", "fail", "missing required fields: " + ", ".join(missing))
    for key, allowed in (("stage", STAGES), ("split", SPLITS), ("method", METHODS),
                         ("provenance", PROVENANCE), ("evidence_state_before", STATES_BEFORE)):
        val = doc.get(key)
        if val is not None and val not in allowed:
            add("F-ENUM", "fail", f"{key}={val!r} not in {sorted(allowed)}")
    if missing or any(x.code == "F-ENUM" for x in f):
        return verdict(EXIT_FAIL, "unchanged")

    method, stage, base = doc["method"], doc["stage"], doc["baseline"]

    if doc["split"] != "held-out":
        add("F-NOT-HELD-OUT", "fail", f"split is {doc['split']!r}: verification must run on held-out cases never used to choose a change")
    if doc["evidence_state_before"] == "unmeasured":
        add("F-NO-BASELINE", "fail", "evidence_state_before is 'unmeasured': there is no baseline, so no green can be earned")

    pins = [("case_set_version", doc["case_set"]["version"], base.get("case_set_version")),
            ("method", method, base.get("method"))]
    if method == "model":
        pins.append(("judge", doc["versions"].get("judge"), base.get("judge")))
    for name, now, then in pins:
        if now != then:
            add("F-PIN-MISMATCH", "fail", f"measurement pin {name!r} differs from baseline ({then!r} -> {now!r}): this is a new series, not a comparison")

    # --- the records ---
    runs, base_runs = doc.get("runs"), base.get("records")
    if not isinstance(runs, list) or not runs or not isinstance(base_runs, list) or not base_runs:
        add("F-NO-RECORDS", "fail", "per-case records are required for the result (`runs[]`) and the baseline "
            "(`baseline.records[]`): every number is computed from them")
        return verdict(EXIT_FAIL, "unchanged")
    try:
        ids, rows = es.aligned(runs, "runs")
        base_ids_cases, base_rows = es.aligned(base_runs, "baseline")
    except es.StatsError as e:
        add("F-RECORDS", "fail", f"per-case records malformed: {e}")
        return verdict(EXIT_FAIL, "unchanged")
    if base_ids_cases != ids:
        add("F-RECORDS", "fail", "the baseline records score different cases from the result's")
    if len(ids) != doc["case_set"]["n"]:
        add("F-RECORDS", "fail", f"records cover {len(ids)} cases, case_set.n is {doc['case_set']['n']}")

    pairs = None
    if method == "model":
        if len(rows) < 3:
            add("F-TOO-FEW-RUNS", "fail", "model-scored dimension needs at least 3 runs to establish a noise floor")
        try:
            pairs = es.label_pairs((doc.get("judge_validation") or {}).get("items"))
            tpr, tnr = es.alignment(pairs)
        except es.StatsError as e:
            add("F-JUDGE-UNVALIDATED", "fail", f"model-scored dimension without a usable judge validation: {e}")
            return verdict(EXIT_FAIL, "unchanged")
        got.update(tpr=tpr, tnr=tnr)
        if tpr + tnr - 1 < es.MIN_INFORMATIVENESS:
            add("F-JUDGE-UNVALIDATED", "fail", f"judge is no better than chance (TPR {tpr:.3f} + TNR {tnr:.3f} - 1 < {es.MIN_INFORMATIVENESS})")
        elif tpr < min_judge_alignment or tnr < min_judge_alignment:
            add("F-JUDGE-UNVALIDATED", "fail", f"judge alignment TPR {tpr:.3f} / TNR {tnr:.3f} below minimum {min_judge_alignment}")
    if any(x.code in INVALID_EVIDENCE for x in f):
        return verdict(EXIT_FAIL, "unchanged")

    try:
        s = es.summarize(rows, pairs)
    except es.StatsError as e:
        add("F-JUDGE-UNVALIDATED", "fail", str(e))
        return verdict(EXIT_FAIL, "unchanged")
    base_rates = es.run_rates(base_rows, got.get("tpr"), got.get("tnr"))
    got.update(score=s["score"], runs=s["runs"], noise_floor=s["noise_floor"], ci95=s["ci95"],
               baseline_score=sum(base_rates) / len(base_rates), baseline_runs=base_rates,
               baseline_run_ids=[r["run_id"] for r in base_runs],
               regressions=es.regressions(ids, base_rows, rows),
               unacceptable=es.unacceptable(doc["dimension"], runs, ids, rows))

    reasons: list[str] = []
    threshold = _threshold(doc, contract, add, reasons)
    got["threshold"] = threshold
    _check_reported(doc, got, add)
    _check_traces(doc, [runs, base_runs], trace_index, add, reasons)
    _check_ledger(doc, got["baseline_run_ids"], ledger, add, reasons)
    if any(x.code in INVALID_EVIDENCE for x in f):
        return verdict(EXIT_FAIL, "unchanged")

    # --- behavioral outcome, on the gate's own numbers ---
    score, noise, (low, _high), base_score = got["score"], got["noise_floor"], got["ci95"], got["baseline_score"]
    if got["unacceptable"]:
        add("F-UNACCEPTABLE", "fail", f"{len(got['unacceptable'])} case(s) tripped a red line, e.g. {got['unacceptable'][0]}: must be zero")
    if got["regressions"]:
        add("F-REGRESSION", "fail", f"{len(got['regressions'])} case(s) that passed every baseline run now mostly fail, e.g. {got['regressions'][0]}")
    if score < threshold:
        add("F-BELOW-THRESHOLD", "fail", f"score {score:.3f} below threshold {threshold}")
    if any(x.severity == "fail" for x in f):
        return verdict(EXIT_FAIL, "red")

    delta = score - base_score
    if base_score < threshold and delta <= noise:
        add("I-DELTA-IN-NOISE", "inconclusive", f"crossed threshold by a delta of {delta:+.3f}, inside the noise floor ±{noise:.3f}")

    provisional = False
    if low < threshold:
        if stage in ("release", "production"):
            add("I-LOWER-BOUND", "inconclusive", f"{stage} requires the 95% lower bound ({low:.3f}) >= threshold ({threshold}); grow the held-out set or keep improving")
        else:
            provisional = True
            add("W-PROVISIONAL", "warning", f"build pass on the point estimate; lower bound {low:.3f} < threshold {threshold}. Green-provisional: can build on, cannot ship")

    if any(x.severity == "inconclusive" for x in f):
        return verdict(EXIT_INCONCLUSIVE, "inconclusive")

    if stage in ("release", "production"):
        reasons.insert(0, f"{stage} stage")
    if doc["provenance"] == "spec-only" and doc["evidence_state_before"] not in ("green", "green-provisional"):
        reasons.append("first green on a spec-only dimension")
    if str(doc["dimension"]).startswith("EVAL-T"):
        reasons.append("unacceptable-failure dimension (EVAL-T)")
    if doc.get("safety_critical") is True:
        reasons.append("safety-critical dimension")
    if doc.get("new_series") is True:
        reasons.append("first green of a new series (case set, method or judge changed)")
    if reasons:
        add("N-JUDGMENT-REVIEW", "note", "human judgment review required (" + "; ".join(reasons) + "): are the cases credible, is the judge measuring the construct, are residual failures acceptable. Task state: awaiting-judgment-review")

    v = verdict(EXIT_PASS, "green-provisional" if provisional else "green")
    v.requires_human_review = bool(reasons)
    v.review_reasons = reasons
    return v


# --------------------------------------------------------------------------- I/O

def load(path: Path) -> Any:
    text = path.read_text()
    if path.suffix == ".json":
        return json.loads(text)
    import yaml  # declared in the script header; `uv run` installs it

    return yaml.safe_load(text)


def load_ledger(path: Path) -> list[dict]:
    """The harness's append-only run log: one JSON object per line."""
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def load_trace_index(path: Path) -> dict:
    """trace_id -> set of span IDs, or None where the export lists no spans.

    Accepts JSON lines ({"trace_id": ..., "span_ids": [...]}) or one bare trace ID per line."""
    index: dict = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("{"):
            rec = json.loads(line)
            spans = rec.get("span_ids")
            index[rec["trace_id"]] = set(spans) if spans is not None else None
        else:
            index[line] = None
    return index


def render(v: Verdict) -> str:
    label = {EXIT_PASS: "PASS", EXIT_FAIL: "FAIL", EXIT_INCONCLUSIVE: "INCONCLUSIVE", EXIT_USAGE: "NOT GATED"}[v.exit_code]
    lines = [f"{label}  {v.obligation or '?'} / {v.dimension or '?'}  ->  evidence_state: {v.evidence_state_after}  (exit {v.exit_code})"]
    c = v.computed
    if "score" in c:
        lines.append(f"  computed: score {c['score']:.3f}  ci95 [{c['ci95'][0]:.3f}, {c['ci95'][1]:.3f}]  noise ±{c['noise_floor']:.3f}"
                     f"  baseline {c['baseline_score']:.3f}  threshold {c.get('threshold')}"
                     + (f"  judge TPR {c['tpr']:.3f} / TNR {c['tnr']:.3f}" if "tpr" in c else ""))
    lines += [f"  [{x.severity}] {x.code}: {x.message}" for x in v.findings]
    if v.requires_human_review:
        lines.append("  -> not done yet: queue checkpoint C4 (judgment review) before marking the task complete")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="BEV gate-check (see verify-before-completion.md)")
    ap.add_argument("result", type=Path, help="eval-result.yaml or .json written by the eval harness")
    ap.add_argument("--json", action="store_true", help="machine-readable verdict on stdout")
    ap.add_argument("--min-judge-alignment", type=float, default=0.8, help="minimum judge TPR and TNR (default 0.8, floor 0.5)")
    ap.add_argument("--contract", type=Path, help="the 04 eval spec; the threshold and method are read from its §4.2")
    ap.add_argument("--ledger", type=Path, help="the harness's append-only run log (JSON lines)")
    ap.add_argument("--traces", type=Path, help="trace-store export: JSON lines with trace_id[, span_ids], or bare IDs")
    args = ap.parse_args(argv)
    try:
        doc = load(args.result)
        contract = load_contract(args.contract) if args.contract else None
        ledger = load_ledger(args.ledger) if args.ledger else None
        traces = load_trace_index(args.traces) if args.traces else None
    except FileNotFoundError as e:
        print(f"NOT GATED  cannot read {e.filename}", file=sys.stderr)
        return EXIT_USAGE
    except Exception as e:  # unparseable YAML/JSON, or a 04 with no §4.2 table
        print(f"NOT GATED  cannot parse input: {e}", file=sys.stderr)
        return EXIT_USAGE
    try:
        v = evaluate(doc, args.min_judge_alignment, ledger, traces, contract)
    except Exception as e:  # a malformed result the checks did not anticipate: never a pass
        print(f"NOT GATED  the gate could not evaluate {args.result}: {type(e).__name__}: {e}", file=sys.stderr)
        return EXIT_USAGE
    print(json.dumps(v.to_dict(), indent=2) if args.json else render(v))
    return v.exit_code


if __name__ == "__main__":
    sys.exit(main())
