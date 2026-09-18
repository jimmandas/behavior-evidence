"""Tests for the BEV gate-check. One test per rule in verify-before-completion.md.

    uv run --with pytest --with pyyaml pytest tools/tests -q   # from the skill directory

Results are built from per-case records, and their reported numbers are filled from the same
statistics the gate uses, so a fixture is honest unless a test makes it lie.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import evidence_stats as es  # noqa: E402
import gate_check as gc  # noqa: E402

TOOL = Path(__file__).resolve().parents[1] / "gate_check.py"

JUDGE = (97, 3, 97, 3)          # tp, fn, tn, fp — TPR = TNR = 0.97 on 200 labels
N = 120
GREEN = (112, 113, 114)          # corrected score ≈ 0.97, lower bound ≈ 0.915 → green at 0.90
PROVISIONAL = (106, 107, 108)    # ≈ 0.917, lower bound ≈ 0.85 → provisional at build
RED = (98, 99, 100)              # ≈ 0.85 → below 0.90
BASE = (83, 84, 85)              # ≈ 0.71


def items(tp, fn, tn, fp) -> list[dict]:
    pairs = [(1, 1)] * tp + [(1, 0)] * fn + [(0, 0)] * tn + [(0, 1)] * fp
    return [{"item_id": f"lab-{i:04d}", "human": h, "judge": j} for i, (h, j) in enumerate(pairs)]


def record(run_id: str, passes: int, n: int) -> dict:
    return {"run_id": run_id, "cases": [
        {"test_case_id": f"case-{j:03d}", "trace_id": f"trace-{run_id}-{j:03d}", "verdict": int(j < passes),
         "critique": "ok" if j < passes else "claim not supported", "evidence_span_ids": [f"span-{run_id}-{j:03d}"]}
        for j in range(n)]}


def fill(d: dict) -> dict:
    """Write the reported numbers the records give, as the adapter would."""
    ids, rows = es.aligned(d["runs"])
    _, base_rows = es.aligned(d["baseline"]["records"])
    pairs = es.label_pairs(d["judge_validation"]["items"]) if d["method"] == "model" else None
    try:
        s = es.summarize(rows, pairs)
    except es.StatsError:
        return d  # an unusable judge: nothing honest to report
    tpr, tnr = (s["tpr"], s["tnr"]) if pairs else (None, None)
    base_rates = es.run_rates(base_rows, tpr, tnr)
    r3 = lambda x: round(x, 3)  # noqa: E731
    d["result"] = {**d.get("result", {}), "score": r3(s["score"]), "runs": [r3(x) for x in s["runs"]],
                   "noise_floor": r3(s["noise_floor"]), "ci95": [r3(x) for x in s["ci95"]]}
    d["baseline"].update(score=r3(sum(base_rates) / len(base_rates)), runs=[r3(x) for x in base_rates],
                         run_ids=[r["run_id"] for r in d["baseline"]["records"]])
    if pairs:
        d["judge_validation"].update(tpr=r3(tpr), tnr=r3(tnr), test_n=len(pairs))
    d["regressions"] = len(es.regressions(ids, base_rows, rows))
    d["unacceptable_failures"] = len(es.unacceptable(d["dimension"], d["runs"], ids, rows))
    return d


def build(passes=GREEN, base=BASE, n=N, method="model", judge=JUDGE, **over) -> dict:
    d = {
        "obligation": "ABS-B07",
        "dimension": "EVAL-D03",
        "provenance": "DISC-promoted",
        "stage": "build",
        "split": "held-out",
        "method": method,
        "case_set": {"version": "v4-heldout", "n": n},
        "versions": {"model": "m-2026-09", "prompt": "p-abc123", "retrieval": "idx-7", "tools": "t-3",
                     "control_policy": "cp-2", "judge": "jp-v3"},
        "baseline": {"case_set_version": "v4-heldout", "method": method, "judge": "jp-v3",
                     "records": [record(f"base-{i}", p, n) for i, p in enumerate(base, 1)]},
        "runs": [record(f"run-{i}", p, n) for i, p in enumerate(passes, 1)],
        "result": {"threshold": 0.90},
        "evidence_state_before": "red",
    }
    if method == "model":
        d["judge_validation"] = {"labels": "v2", "items": items(*judge)}
    else:
        d["versions"].pop("judge")
        d["baseline"].pop("judge")
    d.update(over)
    return fill(d)


def passing_build() -> dict:
    return build()


def set_score(d: dict, passes: tuple, **result) -> dict:
    """Rebuild the result's runs with new pass counts (kept for the slice-gate tests)."""
    n = d["case_set"]["n"]
    d["runs"] = [record(f"run-{i}", p, n) for i, p in enumerate(passes, 1)]
    d["result"].update(result)
    return fill(d)


def ledger_for(d: dict, commit: str = "abc123", split: str = "held-out") -> list[dict]:
    """The candidate's verification runs, plus the baseline runs logged at an earlier commit."""
    verify = [{"run_id": r["run_id"], "dimension": d["dimension"], "split": split,
               "case_set_version": d["case_set"]["version"], "commit": commit} for r in d["runs"]]
    base = [{"run_id": r["run_id"], "dimension": d["dimension"], "split": "held-out", "purpose": "baseline",
             "case_set_version": d["baseline"]["case_set_version"], "commit": "base000"}
            for r in d["baseline"]["records"]]
    return verify + base


def trace_index_for(d: dict) -> dict:
    return {c["trace_id"]: set(c.get("evidence_span_ids") or [])
            for r in d["runs"] + d["baseline"]["records"] for c in r["cases"]}


CONTRACT_MD = """# 04 — Eval Spec

### 4.2 Offline contract

| `EVAL-nn` | Stage | Threshold | Method | Case set | Variance | Status |
|---|---|---|---|---|---|---|
| `EVAL-D03` | build | ≥ 0.90 | model | held-out v4, n=120 | ±0.01 | emerging |
| `EVAL-D03` | release | >= 0.92 | model | held-out v4, n=120 | ±0.01 | |
| `EVAL-D05` | build | 85% | deterministic | | | |
| `EVAL-T02` | release | violations = 0 | deterministic | adversarial, n=40 | — | met |
| `EVAL-D09` | build |  | model | | | |

### 4.3 Calibration

| | |
|---|---|
"""


def contract(tmp_path=None) -> dict:
    import tempfile
    p = Path(tempfile.mkdtemp()) / "04.md"
    p.write_text(CONTRACT_MD)
    return gc.load_contract(p)


def check(doc: dict, **kw) -> gc.Verdict:
    return gc.evaluate(doc, **kw)


def codes(v: gc.Verdict) -> set[str]:
    return {f.code for f in v.findings}


# ---------- pass paths ----------

def test_clean_build_pass_is_green():
    v = check(passing_build())
    assert v.exit_code == gc.EXIT_PASS, v.findings
    assert v.evidence_state_after == "green"
    assert not [f for f in v.findings if f.severity == "fail"]


def test_build_with_lower_bound_below_threshold_is_green_provisional_with_warning():
    v = check(build(passes=PROVISIONAL))
    assert v.exit_code == gc.EXIT_PASS
    assert v.evidence_state_after == "green-provisional"
    assert "W-PROVISIONAL" in codes(v)


def test_release_with_lower_bound_clearing_threshold_passes():
    v = check(build(stage="release"))
    assert v.exit_code == gc.EXIT_PASS
    assert v.evidence_state_after == "green"
    assert "N-JUDGMENT-REVIEW" in codes(v)


def test_deterministic_method_needs_no_judge_and_allows_single_run():
    v = check(build(method="deterministic", passes=(118,), base=(85,)))
    assert v.exit_code == gc.EXIT_PASS, v.findings


def test_baseline_already_meeting_threshold_does_not_need_a_delta():
    v = check(build(base=GREEN, evidence_state_before="stale"))
    assert v.exit_code == gc.EXIT_PASS, v.findings
    assert "I-DELTA-IN-NOISE" not in codes(v)


def test_spec_only_provenance_passes_but_flags_judgment_review():
    v = check(build(provenance="spec-only"))
    assert v.exit_code == gc.EXIT_PASS
    assert "N-JUDGMENT-REVIEW" in codes(v)


def test_the_gate_reports_the_numbers_it_used():
    v = check(passing_build())
    assert v.computed["score"] == pytest.approx(0.97, abs=0.01)
    assert v.computed["threshold"] == 0.90 and len(v.computed["ci95"]) == 2


# ---------- invalid evidence: exit 1, state unchanged ----------

@pytest.mark.parametrize("path", [
    ("obligation",), ("dimension",), ("stage",), ("split",), ("method",), ("provenance",),
    ("case_set", "version"), ("case_set", "n"), ("versions",),
    ("baseline", "case_set_version"), ("baseline", "method"), ("evidence_state_before",),
])
def test_missing_required_field_fails(path):
    d = passing_build()
    cur = d
    for k in path[:-1]:
        cur = cur[k]
    cur.pop(path[-1])
    v = check(d)
    assert v.exit_code == gc.EXIT_FAIL and v.evidence_state_after == "unchanged"
    assert "F-MISSING" in codes(v)


def test_unknown_enum_value_fails():
    v = check(build(split="training"))
    assert v.exit_code == gc.EXIT_FAIL and "F-ENUM" in codes(v)


def test_dev_split_cannot_verify():
    v = check(build(split="dev"))
    assert v.exit_code == gc.EXIT_FAIL and v.evidence_state_after == "unchanged"
    assert "F-NOT-HELD-OUT" in codes(v)


def test_unmeasured_before_means_no_baseline_and_fails():
    v = check(build(evidence_state_before="unmeasured"))
    assert v.exit_code == gc.EXIT_FAIL and "F-NO-BASELINE" in codes(v)


@pytest.mark.parametrize("field,value", [("case_set_version", "v5-heldout"), ("method", "human"), ("judge", "jp-v4")])
def test_measurement_pins_must_match_baseline(field, value):
    d = passing_build()
    d["baseline"][field] = value
    v = check(d)
    assert v.exit_code == gc.EXIT_FAIL and "F-PIN-MISMATCH" in codes(v)


def test_system_versions_may_differ_from_baseline():
    d = passing_build()
    d["versions"]["prompt"] = "p-new"
    assert check(d).exit_code == gc.EXIT_PASS


def test_model_scored_without_judge_items_fails():
    d = passing_build()
    d["judge_validation"].pop("items")
    v = check(d)
    assert v.exit_code == gc.EXIT_FAIL and v.evidence_state_after == "unchanged"
    assert "F-JUDGE-UNVALIDATED" in codes(v)


@pytest.mark.parametrize("judge", [(79, 21, 90, 10), (90, 10, 50, 50)])
def test_judge_below_minimum_alignment_fails(judge):
    v = check(build(judge=judge))
    assert v.exit_code == gc.EXIT_FAIL and "F-JUDGE-UNVALIDATED" in codes(v)


def test_reported_judge_alignment_is_not_trusted():
    """TPR/TNR come from the labels; typing better ones in is a recompute failure."""
    d = build(judge=(79, 21, 90, 10))
    d["judge_validation"].update(tpr=0.95, tnr=0.95)
    v = check(d)
    assert "F-JUDGE-UNVALIDATED" in codes(v)


def test_model_scored_needs_at_least_three_runs():
    v = check(build(passes=(113, 113)))
    assert v.exit_code == gc.EXIT_FAIL and "F-TOO-FEW-RUNS" in codes(v)


@pytest.mark.parametrize("mutate", [
    lambda d: d["result"].update(ci95=[0.95, 0.99]),
    lambda d: d["result"].update(score=0.99),
    lambda d: d["result"].update(noise_floor=0.0),
    lambda d: d["result"].update(runs=[0.99, 0.99, 0.99]),
    lambda d: d["baseline"].update(score=0.5),
    lambda d: d["baseline"].update(runs=[0.5, 0.5, 0.5]),
    lambda d: d["baseline"].update(run_ids=["base-9"]),
    lambda d: d.update(regressions=3),
    lambda d: d.update(unacceptable_failures=1),
    lambda d: d["judge_validation"].update(tpr=0.99),
])
def test_reported_numbers_the_records_do_not_give_are_invalid(mutate):
    d = passing_build()
    mutate(d)
    v = check(d)
    assert v.exit_code == gc.EXIT_FAIL and v.evidence_state_after == "unchanged"
    assert "F-RECOMPUTE" in codes(v)


def test_forged_interval_cannot_turn_provisional_into_green():
    """The review's exploit: ci95 [0.9, 1.0] on a provisional result."""
    d = build(passes=PROVISIONAL)
    d["result"]["ci95"] = [0.9, 1.0]
    assert check(d).evidence_state_after != "green"


def test_verdict_uses_computed_numbers_when_reported_ones_are_absent():
    d = build(passes=PROVISIONAL)
    for k in ("score", "runs", "noise_floor", "ci95"):
        d["result"].pop(k)
    for k in ("score", "runs", "run_ids"):
        d["baseline"].pop(k)
    d.pop("regressions"); d.pop("unacceptable_failures"); d["judge_validation"].pop("tpr")
    v = check(d)
    assert v.exit_code == gc.EXIT_PASS and v.evidence_state_after == "green-provisional", v.findings


@pytest.mark.parametrize("field", ["unacceptable_failures", "regressions"])
@pytest.mark.parametrize("value", [-1, "0", 0.5, True])
def test_failure_counts_must_be_non_negative_integers(field, value):
    d = passing_build()
    d[field] = value
    v = check(d)
    assert v.exit_code == gc.EXIT_FAIL and v.evidence_state_after == "unchanged"
    assert {"F-RANGE", "F-RECOMPUTE"} & codes(v)


# ---------- behavioral failure: exit 1, state red — computed, not reported ----------

def test_red_line_tripped_in_a_record_is_red():
    d = passing_build()
    d["runs"][0]["cases"][0]["red_lines"] = ["EVAL-T02"]
    fill(d)
    v = check(d)
    assert v.exit_code == gc.EXIT_FAIL and v.evidence_state_after == "red"
    assert "F-UNACCEPTABLE" in codes(v)


def test_eval_t_dimension_fails_on_any_failing_verdict():
    d = build(dimension="EVAL-T02", passes=(120, 119, 120), base=(110, 110, 110))
    v = check(d)
    assert v.evidence_state_after == "red" and "F-UNACCEPTABLE" in codes(v)


def test_regression_is_red():
    """Cases 0-9 passed every baseline run and now fail in every run."""
    d = passing_build()
    for r in d["runs"]:
        for c in r["cases"][:10]:
            c["verdict"] = 0
        for c in r["cases"][100:110]:
            c["verdict"] = 1
    fill(d)
    v = check(d)
    assert v.exit_code == gc.EXIT_FAIL and v.evidence_state_after == "red"
    assert "F-REGRESSION" in codes(v)


def test_point_estimate_below_threshold_is_red():
    v = check(build(passes=RED))
    assert v.exit_code == gc.EXIT_FAIL and v.evidence_state_after == "red"
    assert "F-BELOW-THRESHOLD" in codes(v)


def test_invalid_evidence_takes_precedence_over_behavioral_red():
    v = check(build(passes=RED, split="dev"))
    assert v.evidence_state_after == "unchanged"


# ---------- inconclusive: exit 2 ----------

def test_crossing_threshold_inside_noise_floor_is_inconclusive():
    """Baseline 0.895, candidate 0.905, run spread wider than the gain."""
    v = check(build(method="deterministic", passes=(106, 109, 111), base=(107, 107, 108), n=120,
                    result={"threshold": 0.90}))
    assert v.exit_code == gc.EXIT_INCONCLUSIVE, (v.computed, v.findings)
    assert "I-DELTA-IN-NOISE" in codes(v)


def test_release_with_lower_bound_below_threshold_is_inconclusive():
    v = check(build(passes=PROVISIONAL, stage="release"))
    assert v.exit_code == gc.EXIT_INCONCLUSIVE and "I-LOWER-BOUND" in codes(v)


def test_production_uses_release_rule():
    v = check(build(passes=PROVISIONAL, stage="production"))
    assert v.exit_code == gc.EXIT_INCONCLUSIVE


def test_discovery_stage_is_not_gated():
    v = check(build(stage="discovery"))
    assert v.exit_code == gc.EXIT_USAGE and "U-NOT-APPLICABLE" in codes(v)


def test_non_mapping_document_is_usage_error():
    assert check([1, 2]).exit_code == gc.EXIT_USAGE


# ---------- the threshold comes from 04 §4.2 ----------

def test_threshold_is_read_from_the_contract():
    d = passing_build()
    d["result"].pop("threshold")
    v = check(d, contract=contract())
    assert v.exit_code == gc.EXIT_PASS and v.computed["threshold"] == 0.90
    assert "W-THRESHOLD-UNPINNED" not in codes(v)


def test_contract_threshold_differs_by_stage():
    d = build(stage="release")
    d["result"].pop("threshold")
    v = check(d, contract=contract())
    assert v.computed["threshold"] == 0.92


def test_reported_threshold_must_match_the_contract():
    d = passing_build()
    d["result"]["threshold"] = 0.80
    v = check(d, contract=contract())
    assert v.evidence_state_after == "unchanged" and "F-CONTRACT" in codes(v)


@pytest.mark.parametrize("dimension", ["EVAL-D77", "EVAL-D09"])
def test_dimension_without_a_readable_contract_row_is_invalid(dimension):
    d = build(dimension=dimension)
    d["result"].pop("threshold")
    v = check(d, contract=contract())
    assert "F-CONTRACT" in codes(v)


def test_contract_method_must_match():
    d = build(method="deterministic", passes=(118,), base=(85,))
    d["result"].pop("threshold")
    v = check(d, contract=contract())
    assert "F-CONTRACT" in codes(v)


def test_no_contract_means_the_threshold_is_unpinned():
    v = check(passing_build())
    assert "W-THRESHOLD-UNPINNED" in codes(v)
    r = check(build(stage="release"))
    assert any("04" in x for x in r.review_reasons)


def test_no_contract_and_no_threshold_fails():
    d = passing_build()
    d["result"].pop("threshold")
    assert "F-MISSING" in codes(check(d))


@pytest.mark.parametrize("cell,dim,expected", [
    ("≥ 0.92", "EVAL-D01", 0.92), (">= 0.9", "EVAL-D01", 0.9), ("0.85", "EVAL-D01", 0.85), ("85%", "EVAL-D01", 0.85),
    ("violations = 0", "EVAL-T01", 1.0), ("= 0", "EVAL-T01", 1.0), ("", "EVAL-D01", None), ("tbd", "EVAL-D01", None),
    ("1.5", "EVAL-D01", None),
])
def test_threshold_cells_parse(cell, dim, expected):
    assert gc.parse_threshold(cell, dim) == expected


def test_contract_parses_the_offline_table():
    c = contract()
    assert c[("EVAL-T02", "release")] == {"threshold": 1.0, "method": "deterministic"}
    assert ("EVAL-D03", "build") in c and ("EVAL-D03", "release") in c


def test_contract_without_a_4_2_table_is_rejected(tmp_path):
    p = tmp_path / "04.md"
    p.write_text("# 04\n\n### 4.1 Case sets\n")
    with pytest.raises(ValueError):
        gc.load_contract(p)


# ---------- CLI ----------

def _run_cli(tmp_path, doc, *args, suffix=".yaml"):
    p = tmp_path / f"eval-result{suffix}"
    p.write_text(json.dumps(doc) if suffix == ".json" else yaml.safe_dump(doc))
    return subprocess.run([sys.executable, str(TOOL), str(p), *args], capture_output=True, text=True)


def test_cli_exit_code_and_json_output(tmp_path):
    proc = _run_cli(tmp_path, passing_build(), "--json")
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["evidence_state_after"] == "green" and "score" in out["computed"]


def test_cli_accepts_json_input(tmp_path):
    assert _run_cli(tmp_path, passing_build(), suffix=".json").returncode == 0


def test_cli_missing_file_is_usage_error(tmp_path):
    proc = subprocess.run([sys.executable, str(TOOL), str(tmp_path / "nope.yaml")], capture_output=True, text=True)
    assert proc.returncode == 3


def test_cli_unparseable_file_is_usage_error(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("{not: [valid")
    proc = subprocess.run([sys.executable, str(TOOL), str(p)], capture_output=True, text=True)
    assert proc.returncode == 3


def test_cli_reads_the_contract(tmp_path):
    (tmp_path / "04.md").write_text(CONTRACT_MD)
    d = passing_build()
    d["result"]["threshold"] = 0.80
    proc = _run_cli(tmp_path, d, "--contract", str(tmp_path / "04.md"))
    assert proc.returncode == 1 and "F-CONTRACT" in proc.stdout


def test_min_judge_alignment_is_configurable(tmp_path):
    proc = _run_cli(tmp_path, build(judge=(85, 15, 85, 15)), "--min-judge-alignment", "0.9")
    assert proc.returncode == 1


def test_evaluate_does_not_mutate_input():
    d = passing_build()
    before = copy.deepcopy(d)
    gc.evaluate(d)
    assert d == before


# ---------- requires_human_review (checkpoint C4) ----------

def test_clean_build_pass_needs_no_human_review():
    v = check(passing_build())
    assert v.requires_human_review is False and v.review_reasons == []


@pytest.mark.parametrize("stage", ["release", "production"])
def test_release_and_production_pass_require_review(stage):
    v = check(build(stage=stage))
    assert v.exit_code == gc.EXIT_PASS and v.requires_human_review is True
    assert any(stage in r for r in v.review_reasons)


def test_first_green_on_spec_only_requires_review_but_later_greens_do_not():
    assert check(build(provenance="spec-only")).requires_human_review is True
    assert check(build(provenance="spec-only", evidence_state_before="green")).requires_human_review is False


def test_safety_critical_dimension_requires_review():
    v = check(build(safety_critical=True))
    assert v.requires_human_review is True and any("safety" in r for r in v.review_reasons)


def test_new_series_requires_review():
    v = check(build(new_series=True))
    assert v.requires_human_review is True and any("series" in r for r in v.review_reasons)


def test_eval_t_pass_requires_review():
    v = check(build(dimension="EVAL-T02", method="deterministic", passes=(120,), base=(110,), result={"threshold": 1.0}))
    assert v.exit_code == gc.EXIT_PASS, v.findings
    assert any("EVAL-T" in r for r in v.review_reasons)


def test_non_pass_verdicts_never_request_review():
    v = check(build(passes=RED, stage="release", safety_critical=True))
    assert v.exit_code == gc.EXIT_FAIL and v.requires_human_review is False


def test_json_output_carries_review_flag(tmp_path):
    out = json.loads(_run_cli(tmp_path, build(stage="release"), "--json").stdout)
    assert out["requires_human_review"] is True and out["review_reasons"]


# ---------- per-case records ----------

def test_missing_records_are_invalid_evidence():
    d = passing_build()
    d.pop("runs")
    v = check(d)
    assert v.evidence_state_after == "unchanged" and "F-NO-RECORDS" in codes(v)


def test_missing_baseline_records_are_invalid_evidence():
    d = passing_build()
    d["baseline"].pop("records")
    assert "F-NO-RECORDS" in codes(check(d))


@pytest.mark.parametrize("field", ["test_case_id", "trace_id", "verdict"])
def test_case_record_missing_an_id_or_verdict_is_invalid(field):
    d = passing_build()
    d["runs"][0]["cases"][5].pop(field)
    v = check(d)
    assert v.evidence_state_after == "unchanged" and "F-RECORDS" in codes(v)


def test_non_binary_verdict_is_invalid():
    """An EVAL-D score is a rate of binary verdicts, never a per-case score."""
    d = passing_build()
    d["runs"][0]["cases"][0]["verdict"] = 0.82
    assert "F-RECORDS" in codes(check(d))


def test_duplicate_run_ids_are_invalid():
    d = passing_build()
    d["runs"][1]["run_id"] = d["runs"][0]["run_id"]
    assert "F-RECORDS" in codes(check(d))


def test_duplicate_case_in_a_run_is_invalid():
    d = passing_build()
    d["runs"][0]["cases"][1]["test_case_id"] = d["runs"][0]["cases"][0]["test_case_id"]
    assert "F-RECORDS" in codes(check(d))


def test_runs_over_different_cases_are_invalid():
    d = passing_build()
    d["runs"][2]["cases"][0]["test_case_id"] = "case-other"
    assert "F-RECORDS" in codes(check(d))


def test_baseline_over_different_cases_is_invalid():
    d = passing_build()
    for r in d["baseline"]["records"]:
        r["cases"][0]["test_case_id"] = "case-other"
    assert "F-RECORDS" in codes(check(d))


def test_record_count_must_match_case_set_n():
    d = passing_build()
    d["case_set"]["n"] = 119
    assert "F-RECORDS" in codes(check(d))


def test_deterministic_rates_are_not_corrected():
    v = check(build(method="deterministic", passes=(118,), base=(85,)))
    assert v.computed["score"] == pytest.approx(118 / 120, abs=1e-9)


# ---------- trace resolution ----------

def test_every_trace_resolves_against_the_trace_index():
    d = passing_build()
    assert check(d, trace_index=trace_index_for(d)).exit_code == gc.EXIT_PASS


@pytest.mark.parametrize("which", ["runs", "baseline"])
def test_trace_missing_from_the_store_is_invalid_evidence(which):
    """A run the harness claims but the trace store never saw — fabricated or lost."""
    d = passing_build()
    idx = trace_index_for(d)
    runs = d["runs"] if which == "runs" else d["baseline"]["records"]
    idx.pop(runs[1]["cases"][7]["trace_id"])
    v = check(d, trace_index=idx)
    assert v.evidence_state_after == "unchanged" and "F-TRACE-MISSING" in codes(v)


def test_cited_span_not_in_its_trace_is_invalid_evidence():
    d = passing_build()
    idx = trace_index_for(d)
    d["runs"][0]["cases"][3]["evidence_span_ids"] = ["span-from-somewhere-else"]
    assert "F-SPAN-MISSING" in codes(check(d, trace_index=idx))


def test_index_without_span_lists_checks_trace_ids_only():
    d = passing_build()
    v = check(d, trace_index={t: None for t in trace_index_for(d)})
    assert v.exit_code == gc.EXIT_PASS and "W-SPANS-UNCHECKED" in codes(v)


def test_unresolved_traces_warn_at_build():
    v = check(passing_build())
    assert v.exit_code == gc.EXIT_PASS and "W-TRACES-UNRESOLVED" in codes(v)
    assert v.requires_human_review is False


def test_unresolved_traces_need_review_at_release():
    d = with_commit(build(stage="release"))
    v = check(d, ledger=ledger_for(d))
    assert v.exit_code == gc.EXIT_PASS and any("trace" in r for r in v.review_reasons)


# ---------- the run ledger ----------

def with_commit(d, commit="abc123"):
    d["versions"]["commit"] = commit
    return d


def test_result_matching_the_ledger_passes():
    d = with_commit(passing_build())
    v = check(d, ledger=ledger_for(d), trace_index=trace_index_for(d))
    assert v.exit_code == gc.EXIT_PASS and not v.requires_human_review, v.review_reasons


def test_run_absent_from_the_ledger_is_invalid_evidence():
    d = with_commit(passing_build())
    v = check(d, ledger=ledger_for(d)[1:])
    assert v.evidence_state_after == "unchanged" and "F-RUN-NOT-LOGGED" in codes(v)


def test_omitted_held_out_run_is_cherry_picking():
    """Retry-until-green: a failing held-out run on the same candidate left out of the result."""
    d = with_commit(passing_build())
    led = ledger_for(d) + [{"run_id": "run-4", "dimension": "EVAL-D03", "split": "held-out",
                            "case_set_version": "v4-heldout", "commit": "abc123"}]
    v = check(d, ledger=led)
    assert v.evidence_state_after == "unchanged" and "F-RUNS-OMITTED" in codes(v)


@pytest.mark.parametrize("other", [{"dimension": "EVAL-D09"}, {"split": "dev"}, {"case_set_version": "v3-heldout"}])
def test_ledger_runs_for_other_series_are_not_omissions(other):
    d = with_commit(passing_build())
    extra = {"run_id": "run-x", "dimension": "EVAL-D03", "split": "held-out", "case_set_version": "v4-heldout",
             "commit": "abc123", **other}
    assert check(d, ledger=ledger_for(d) + [extra]).exit_code == gc.EXIT_PASS


def test_ledger_needs_the_result_pinned_to_a_commit():
    d = passing_build()
    assert "F-LEDGER-COMMIT" in codes(check(d, ledger=ledger_for(d)))


def test_held_out_set_reused_across_candidates_needs_review():
    d = with_commit(passing_build())
    earlier = [{**e, "run_id": e["run_id"] + "-old", "commit": sha}
               for sha in ("c0ffee1", "c0ffee2") for e in ledger_for(d) if not e.get("purpose")]
    v = check(d, ledger=ledger_for(d) + earlier)
    assert v.exit_code == gc.EXIT_PASS and v.requires_human_review is True
    assert any("2 earlier" in r for r in v.review_reasons)


def test_no_ledger_warns_at_build_and_needs_review_at_release():
    assert {"W-NO-LEDGER", "W-BASELINE-UNCHECKED"} <= codes(check(passing_build()))
    d = build(stage="release")
    v = check(d, trace_index=trace_index_for(d))
    assert any("ledger" in r for r in v.review_reasons)


def test_cli_reads_ledger_and_trace_index(tmp_path):
    d = with_commit(passing_build())
    (tmp_path / "ledger.jsonl").write_text("\n".join(json.dumps(e) for e in ledger_for(d)) + "\n")
    (tmp_path / "traces.jsonl").write_text("\n".join(json.dumps({"trace_id": t, "span_ids": sorted(s)})
                                                     for t, s in trace_index_for(d).items()))
    proc = _run_cli(tmp_path, d, "--ledger", str(tmp_path / "ledger.jsonl"), "--traces", str(tmp_path / "traces.jsonl"), "--json")
    out = json.loads(proc.stdout)
    assert proc.returncode == 0, out
    assert not ({"W-NO-LEDGER", "W-TRACES-UNRESOLVED"} & {f["code"] for f in out["findings"]})


def test_cli_accepts_a_plain_trace_id_list(tmp_path):
    d = passing_build()
    (tmp_path / "traces.txt").write_text("\n".join(trace_index_for(d)))
    proc = _run_cli(tmp_path, d, "--traces", str(tmp_path / "traces.txt"), "--json")
    assert proc.returncode == 0
    assert "W-TRACES-UNRESOLVED" not in {f["code"] for f in json.loads(proc.stdout)["findings"]}


def test_uninformative_judge_fails_whatever_the_alignment_flag():
    v = check(build(judge=(50, 50, 50, 50)), min_judge_alignment=0.3)
    assert v.evidence_state_after == "unchanged" and "F-JUDGE-UNVALIDATED" in codes(v)


def test_alignment_flag_has_a_floor():
    v = check(build(judge=(45, 55, 95, 5)), min_judge_alignment=0.3)
    assert "F-JUDGE-UNVALIDATED" in codes(v)


def test_baseline_unchecked_without_a_ledger_warns():
    assert "W-BASELINE-UNCHECKED" in codes(check(passing_build()))


@pytest.mark.parametrize("mutate", [
    lambda d, led: [e.pop("purpose") for e in led if e.get("purpose")],
    lambda d, led: [e.update(commit="abc123") for e in led if e.get("purpose")],
    lambda d, led: [e.update(dimension="EVAL-D09") for e in led if e.get("purpose")],
    lambda d, led: [e.update(case_set_version="v3") for e in led if e.get("purpose")],
    lambda d, led: led.remove(next(e for e in led if e.get("purpose"))),
])
def test_baseline_must_be_logged_runs_on_an_earlier_candidate(mutate):
    d = with_commit(passing_build())
    led = ledger_for(d)
    mutate(d, led)
    v = check(d, ledger=led)
    assert v.evidence_state_after == "unchanged" and "F-NO-BASELINE" in codes(v)


@pytest.mark.parametrize("mutate", [
    lambda e: e.update(split="dev"),
    lambda e: e.update(commit="other"),
    lambda e: e.update(dimension="EVAL-D09"),
    lambda e: e.update(case_set_version="v3"),
    lambda e: e.update(purpose="baseline"),
])
def test_claimed_run_must_be_logged_as_a_held_out_run_of_this_candidate(mutate):
    d = with_commit(passing_build())
    led = ledger_for(d)
    mutate(led[0])
    v = check(d, ledger=led)
    assert v.evidence_state_after == "unchanged" and "F-RUN-NOT-LOGGED" in codes(v)


def test_cli_reports_a_gate_error_as_not_gated(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("bad")
    monkeypatch.setattr(gc, "evaluate", boom)
    p = tmp_path / "r.yaml"
    p.write_text(yaml.safe_dump(passing_build()))
    assert gc.main([str(p)]) == gc.EXIT_USAGE


@pytest.mark.parametrize("kind", ["red_line", "regression"])
def test_failures_are_found_even_when_the_result_omits_its_counts(kind):
    d = passing_build()
    if kind == "red_line":
        d["runs"][0]["cases"][0]["red_lines"] = ["EVAL-T02"]
    else:
        for r in d["runs"]:
            for c in r["cases"][:10]:
                c["verdict"] = 0
            for c in r["cases"][100:110]:
                c["verdict"] = 1
    fill(d)
    d.pop("unacceptable_failures"); d.pop("regressions")
    v = check(d)
    assert v.evidence_state_after == "red"
    assert ("F-UNACCEPTABLE" if kind == "red_line" else "F-REGRESSION") in codes(v)
