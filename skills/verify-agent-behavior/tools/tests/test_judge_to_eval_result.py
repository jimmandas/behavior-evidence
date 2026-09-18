"""Tests for the per-case verdicts → eval-result adapter and the statistics it shares with the gate.

    uv run --with pytest --with pyyaml pytest tools/tests -q   # from the skill directory
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import evidence_stats as es  # noqa: E402
import gate_check as gc  # noqa: E402
import judge_to_eval_result as ad  # noqa: E402


def items(tp, fn, tn, fp):
    pairs = [(1, 1)] * tp + [(1, 0)] * fn + [(0, 0)] * tn + [(0, 1)] * fp
    return [{"item_id": f"lab-{i:04d}", "human": h, "judge": j} for i, (h, j) in enumerate(pairs)]


def cases(run_id, passes, n):
    return [{"test_case_id": f"case-{i:03d}", "trace_id": f"trace-{run_id}-{i:03d}", "verdict": int(i < passes),
             "critique": "ok" if i < passes else "unsupported claim", "evidence_span_ids": [f"span-{run_id}-{i:03d}"]}
            for i in range(n)]


def run_doc(tp=46, fn=4, tn=45, fp=5, run_passes=(57, 58, 59), base_passes=(40, 41, 42), n=60, threshold=0.85):
    return {
        "judge_validation": {"labels": "v2", "items": items(tp, fn, tn, fp)},
        "baseline_runs": [{"run_id": f"base-{k}", "cases": cases(f"base-{k}", p, n)} for k, p in enumerate(base_passes, 1)],
        "runs": [{"run_id": f"run-{k}", "cases": cases(f"run-{k}", p, n)} for k, p in enumerate(run_passes, 1)],
        "threshold": threshold,
    }


TEMPLATE = {
    "obligation": "ABS-B07", "dimension": "EVAL-D03", "provenance": "DISC-promoted",
    "stage": "build", "split": "held-out", "method": "model",
    "case_set": {"version": "v4-heldout"},
    "versions": {"model": "m1", "prompt": "p2", "judge": "jp-v3"},
    "baseline": {"case_set_version": "v4-heldout", "method": "model", "judge": "jp-v3"},
    "evidence_state_before": "red",
}


def pairs_of(tp, fn, tn, fp):
    return es.label_pairs(items(tp, fn, tn, fp))


# ---------- the arithmetic (evidence_stats) ----------

def test_tpr_tnr():
    tpr, tnr = es.alignment(pairs_of(45, 5, 40, 10))
    assert tpr == pytest.approx(0.90) and tnr == pytest.approx(0.80)


def test_rogan_gladen_correction():
    # observed 0.80 with TPR 0.92 / TNR 0.88 -> (0.80 + 0.88 - 1) / (0.92 + 0.88 - 1) = 0.85
    assert ad.corrected_rate(0.80, 0.92, 0.88) == pytest.approx(0.85)


@pytest.mark.parametrize("p_obs,expected", [(0.99, 1.0), (0.05, 0.0)])
def test_correction_is_clipped_to_unit_interval(p_obs, expected):
    assert ad.corrected_rate(p_obs, 0.9, 0.9) == pytest.approx(expected)


def test_judge_no_better_than_chance_is_rejected():
    with pytest.raises(es.StatsError, match="no better than chance"):
        ad.corrected_rate(0.7, 0.52, 0.51)


def test_labels_without_both_classes_are_rejected():
    with pytest.raises(es.StatsError, match="Pass and Fail"):
        es.alignment(((1, 1), (1, 0), (1, 1)))


def test_bootstrap_is_deterministic_and_contains_the_score():
    rows = tuple(tuple([1] * p + [0] * (60 - p)) for p in (57, 58, 59))
    a = es.summarize(rows, pairs_of(46, 4, 45, 5))
    es.summarize.cache_clear()
    b = es.summarize(rows, pairs_of(46, 4, 45, 5))
    assert a["ci95"] == b["ci95"]
    assert 0 <= a["ci95"][0] <= a["score"] <= a["ci95"][1] <= 1


def test_ci_narrows_with_more_cases():
    small = ad.build(run_doc(run_passes=(19, 19, 20), base_passes=(10, 10, 10), n=20))["result"]["ci95"]
    large = ad.build(run_doc(run_passes=(190, 191, 192), base_passes=(100, 100, 100), n=200))["result"]["ci95"]
    assert (large[1] - large[0]) < (small[1] - small[0])


def test_ci_narrows_with_more_judge_labels():
    """Judge uncertainty is part of the interval: same cases, 5x the labels, narrower CI."""
    few = run_doc(tp=18, fn=2, tn=18, fp=2, run_passes=(48, 48, 48))
    many = run_doc(tp=90, fn=10, tn=90, fp=10, run_passes=(48, 48, 48))
    width = lambda c: c[1] - c[0]  # noqa: E731
    assert width(ad.build(many)["result"]["ci95"]) < width(ad.build(few)["result"]["ci95"])


def test_regressions_need_every_baseline_run_passing_and_most_runs_failing():
    ids = ("a", "b", "c")
    base = ((1, 1, 0), (1, 1, 1))
    now = ((0, 1, 0), (0, 0, 0), (1, 1, 0))
    assert es.regressions(ids, base, now) == ["a"]   # b fails 1 of 3 (not a majority); c never passed every baseline


# ---------- building the result ----------

def test_build_result_fields():
    out = ad.build(run_doc())
    tpr, tnr = 46 / 50, 45 / 50
    expected_runs = [ad.corrected_rate(p / 60, tpr, tnr) for p in (57, 58, 59)]
    assert out["judge_validation"]["tpr"] == round(tpr, 3) and out["judge_validation"]["test_n"] == 100
    assert len(out["judge_validation"]["items"]) == 100
    assert out["result"]["runs"] == [round(r, 3) for r in expected_runs]
    assert out["result"]["score"] == pytest.approx(sum(expected_runs) / 3, abs=1e-3)
    assert out["result"]["threshold"] == 0.85
    assert out["baseline"]["run_ids"] == ["base-1", "base-2", "base-3"]
    assert out["case_set_n"] == 60


def test_deterministic_input_needs_no_judge():
    d = run_doc()
    d.pop("judge_validation")
    out = ad.build(d)
    assert "judge_validation" not in out
    assert out["result"]["runs"] == [round(p / 60, 3) for p in (57, 58, 59)]


def test_runs_must_score_the_same_cases():
    d = run_doc()
    d["runs"][1]["cases"].pop()
    with pytest.raises(ad.AdapterError, match="different cases"):
        ad.build(d)


def test_baseline_must_score_the_same_cases():
    d = run_doc()
    for r in d["baseline_runs"]:
        r["cases"].pop()
    with pytest.raises(ad.AdapterError, match="different cases"):
        ad.build(d)


def test_baseline_runs_are_required():
    d = run_doc()
    d.pop("baseline_runs")
    with pytest.raises(ad.AdapterError, match="baseline_runs"):
        ad.build(d)


def test_runs_are_matched_by_case_id_not_position():
    d, shuffled = run_doc(), run_doc()
    shuffled["runs"][1]["cases"].reverse()
    assert ad.build(d)["result"] == ad.build(shuffled)["result"]


@pytest.mark.parametrize("where", ["labels", "runs"])
def test_positional_input_is_rejected(where):
    d = run_doc()
    if where == "labels":
        d["judge_validation"] = {"labels": "v2", "human": [1, 0], "judge": [1, 0]}
    else:
        d["runs"] = [{"verdicts": [1, 0, 1]}]
    with pytest.raises(ad.AdapterError, match="positional"):
        ad.build(d)


@pytest.mark.parametrize("mutate,match", [
    (lambda d: d["runs"][0]["cases"][0].pop("trace_id"), "trace_id"),
    (lambda d: d["runs"][0]["cases"][0].update(verdict=0.8), "0 or 1"),
    (lambda d: d["runs"][0]["cases"][1].update(test_case_id="case-000"), "duplicate"),
    (lambda d: d["runs"][1].update(run_id="run-1"), "unique run_id"),
    (lambda d: d["judge_validation"]["items"][1].update(item_id="lab-0000"), "unique item_id"),
    (lambda d: d["judge_validation"]["items"][0].update(human=2), "0 or 1"),
])
def test_malformed_records_are_rejected(mutate, match):
    d = run_doc()
    mutate(d)
    with pytest.raises(ad.AdapterError, match=match):
        ad.build(d)


def test_records_are_carried_into_the_result():
    d = run_doc()
    d["runs"][0]["cases"][0]["red_lines"] = ["EVAL-T02"]
    out = ad.build(d)
    assert [r["run_id"] for r in out["runs"]] == ["run-1", "run-2", "run-3"]
    assert set(out["runs"][0]["cases"][0]) == {"test_case_id", "trace_id", "verdict", "critique",
                                               "evidence_span_ids", "red_lines"}
    assert len(out["baseline"]["records"]) == 3


def test_merge_into_template_preserves_fields_and_computes_counts():
    d = run_doc()
    d["runs"][0]["cases"][0]["red_lines"] = ["EVAL-T02"]
    merged = ad.merge(TEMPLATE, ad.build(d))
    assert merged["obligation"] == "ABS-B07" and merged["baseline"]["case_set_version"] == "v4-heldout"
    assert merged["case_set"] == {"version": "v4-heldout", "n": 60}
    assert merged["unacceptable_failures"] == 1 and merged["regressions"] == 0
    assert "_aligned" not in merged


def test_merge_refuses_conflicting_case_count():
    t = {**TEMPLATE, "case_set": {"version": "v4-heldout", "n": 99}}
    with pytest.raises(ad.AdapterError, match="case_set.n"):
        ad.merge(t, ad.build(run_doc()))


# ---------- end to end with the gate-check ----------

def good():
    return ad.merge({**TEMPLATE, "versions": {**TEMPLATE["versions"], "commit": "abc123"}},
                    ad.build(run_doc(tp=97, fn=3, tn=97, fp=3, n=120, run_passes=(112, 113, 114),
                                     base_passes=(83, 84, 85), threshold=0.90)))


def test_adapter_output_passes_the_gate_with_every_number_reproduced():
    v = gc.evaluate(good())
    assert v.exit_code == gc.EXIT_PASS, v.findings
    assert "F-RECOMPUTE" not in {f.code for f in v.findings}


def test_adapter_output_resolves_against_its_own_traces_and_ledger():
    merged = good()
    idx = {c["trace_id"]: set(c["evidence_span_ids"]) for r in merged["runs"] + merged["baseline"]["records"] for c in r["cases"]}
    led = [{"run_id": r["run_id"], "dimension": "EVAL-D03", "split": "held-out",
            "case_set_version": "v4-heldout", "commit": "abc123"} for r in merged["runs"]]
    led += [{"run_id": r, "dimension": "EVAL-D03", "split": "held-out", "purpose": "baseline",
             "case_set_version": "v4-heldout", "commit": "base000"} for r in merged["baseline"]["run_ids"]]
    v = gc.evaluate(merged, ledger=led, trace_index=idx)
    assert v.exit_code == gc.EXIT_PASS and not v.requires_human_review, v.findings


def test_adapter_output_fails_gate_check_for_a_weak_judge():
    merged = ad.merge(TEMPLATE, ad.build(run_doc(tp=35, fn=15, tn=45, fp=5)))  # TPR 0.70
    v = gc.evaluate(merged)
    assert v.exit_code == gc.EXIT_FAIL
    assert "F-JUDGE-UNVALIDATED" in {f.code for f in v.findings}


def test_cli_writes_merged_yaml(tmp_path):
    run_file, tmpl_file, out_file = tmp_path / "judge-run.yaml", tmp_path / "template.yaml", tmp_path / "eval-result.yaml"
    run_file.write_text(yaml.safe_dump(run_doc()))
    tmpl_file.write_text(yaml.safe_dump(TEMPLATE))
    proc = subprocess.run([sys.executable, str(TOOLS / "judge_to_eval_result.py"), str(run_file),
                           "--template", str(tmpl_file), "--out", str(out_file)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    out = yaml.safe_load(out_file.read_text())
    assert out["case_set"]["n"] == 60 and "ci95" in out["result"] and out["baseline"]["records"]


def test_cli_invalid_input_exits_3(tmp_path):
    run_file = tmp_path / "judge-run.yaml"
    d = run_doc()
    d["judge_validation"]["items"] = items(2, 0, 0, 0)
    run_file.write_text(yaml.safe_dump(d))
    proc = subprocess.run([sys.executable, str(TOOLS / "judge_to_eval_result.py"), str(run_file)], capture_output=True, text=True)
    assert proc.returncode == 3
