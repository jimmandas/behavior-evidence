"""Tests for the slice gate: is a vertical slice done, across tasks, obligations and checkpoints?"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import slice_gate as sg  # noqa: E402
from test_gate_check import (CONTRACT_MD, PROVISIONAL, build, ledger_for, passing_build,  # noqa: E402
                             set_score, trace_index_for)


def manifest(**over) -> dict:
    m = {
        "slice": "SLICE-03",
        "stage": "build",
        "commit": "abc123",
        "contract": "04-evaluation-spec.md",
        "ledger": "runs.jsonl",
        "traces": "traces.jsonl",
        "obligations": [
            {
                "requirement": "ABS-B07",
                "routing": "both",
                "tasks": ["plan-2026-09-16/task-4"],
                "accepted": True,
                "verification": {
                    "tdd": {"required": True, "refs": ["CONTRACT-021"], "state": "green"},
                    "bev": {"required": True, "dimension": "EVAL-D03", "evidence_state": "green",
                            "last_result": "results/EVAL-D03.yaml"},
                },
            },
            {
                "requirement": "ABS-B08",
                "routing": "tdd",
                "tasks": ["plan-2026-09-16/task-6"],
                "accepted": True,
                "verification": {"tdd": {"required": True, "refs": ["UNIT-088"], "state": "green"},
                                 "bev": {"required": False}},
            },
        ],
    }
    m.update(over)
    return m


def write(tmp_path, m, result=None, checkpoints=None, commit="abc123"):
    (tmp_path / "results").mkdir(exist_ok=True)
    r = result if result is not None else {**passing_build(), "versions": {**passing_build()["versions"], "commit": commit}}
    if r:
        (tmp_path / "results/EVAL-D03.yaml").write_text(yaml.safe_dump(r))
        if not (tmp_path / "runs.jsonl").exists() and isinstance(r.get("runs"), list):
            write_evidence(tmp_path, r)
    if not (tmp_path / "04-evaluation-spec.md").exists():
        (tmp_path / "04-evaluation-spec.md").write_text(CONTRACT_MD)
    (tmp_path / "manifest.yaml").write_text(yaml.safe_dump(m))
    if checkpoints is not None:
        (tmp_path / "checkpoints.yaml").write_text(yaml.safe_dump(checkpoints))
    return tmp_path / "manifest.yaml"


def run(tmp_path, m, **kw):
    path = write(tmp_path, m, **kw)
    return sg.evaluate_slice(path, checkpoints=(tmp_path / "checkpoints.yaml" if (tmp_path / "checkpoints.yaml").exists() else None))


def codes(v):
    return {f.code for f in v.findings}


# ---------- done ----------

def test_slice_with_everything_green_passes(tmp_path):
    v = run(tmp_path, manifest())
    assert v.exit_code == sg.EXIT_DONE, v.findings


def test_obligation_with_no_bev_requirement_needs_only_tdd(tmp_path):
    m = manifest()
    m["obligations"] = [m["obligations"][1]]
    assert run(tmp_path, m).exit_code == sg.EXIT_DONE


# ---------- not done: exit 1 ----------

@pytest.mark.parametrize("state", ["unmeasured", "red", "stale", None])
def test_bev_obligation_with_no_result_blocks_the_slice(tmp_path, state):
    """A BEV row has an earned dimension. With no result yet, its baseline or verification is still owed."""
    m = manifest()
    bev = m["obligations"][0]["verification"]["bev"]
    bev.pop("last_result")
    bev["evidence_state"] = state
    v = run(tmp_path, m)
    assert v.exit_code == sg.EXIT_NOT_DONE
    assert "S-BEV-NOT-GREEN" in codes(v)


def test_tdd_not_green_blocks_the_slice(tmp_path):
    m = manifest()
    m["obligations"][1]["verification"]["tdd"]["state"] = "red"
    v = run(tmp_path, m)
    assert v.exit_code == sg.EXIT_NOT_DONE
    assert "S-TDD-NOT-GREEN" in codes(v)


def test_unresolved_routing_blocks_the_slice(tmp_path):
    m = manifest()
    m["obligations"][0]["routing"] = "UNRESOLVED"
    v = run(tmp_path, m)
    assert v.exit_code == sg.EXIT_NOT_DONE
    assert "S-UNRESOLVED" in codes(v)


def test_unaccepted_derive_rows_block_the_slice(tmp_path):
    m = manifest()
    m["obligations"][0]["accepted"] = False
    v = run(tmp_path, m)
    assert v.exit_code == sg.EXIT_NOT_DONE
    assert "S-NOT-ACCEPTED" in codes(v)


def test_green_without_a_result_file_is_unfounded(tmp_path):
    m = manifest()
    m["obligations"][0]["verification"]["bev"].pop("last_result")
    v = run(tmp_path, m)
    assert v.exit_code == sg.EXIT_NOT_DONE
    assert "S-NO-EVIDENCE" in codes(v)


def test_green_whose_result_file_fails_the_gate_check_is_rejected(tmp_path):
    bad = {**passing_build(), "regressions": 2}
    bad["versions"] = {**bad["versions"], "commit": "abc123"}
    v = run(tmp_path, manifest(), result=bad)
    assert v.exit_code == sg.EXIT_NOT_DONE
    assert "S-GATE-FAILED" in codes(v)


def test_result_pinned_to_another_commit_is_stale(tmp_path):
    m = manifest()
    m["obligations"][0]["verification"]["bev"].pop("evidence_state")
    v = run(tmp_path, m, commit="oldsha")
    assert v.exit_code == sg.EXIT_NOT_DONE
    assert "S-STALE" in codes(v)
    assert v.obligations[0]["evidence_state"] == "stale"


def test_missing_obligation_fields_block_the_slice(tmp_path):
    m = manifest()
    m["obligations"][0].pop("routing")
    v = run(tmp_path, m)
    assert v.exit_code == sg.EXIT_NOT_DONE
    assert "S-MALFORMED" in codes(v)


def test_slice_with_no_obligations_is_not_done(tmp_path):
    v = run(tmp_path, manifest(obligations=[]))
    assert v.exit_code == sg.EXIT_NOT_DONE
    assert "S-EMPTY" in codes(v)


# ---------- awaiting a human: exit 2 ----------

def test_open_blocking_checkpoint_awaits(tmp_path):
    m = manifest()
    m["obligations"][0]["blocked_by"] = ["CP-0007"]
    cps = [{"id": "CP-0007", "type": "C3", "status": "open", "estimate_min": 40}]
    v = run(tmp_path, m, checkpoints=cps)
    assert v.exit_code == sg.EXIT_AWAITING
    assert "S-CHECKPOINT-OPEN" in codes(v)


def test_closed_checkpoint_does_not_block(tmp_path):
    m = manifest()
    m["obligations"][0]["blocked_by"] = ["CP-0007"]
    cps = [{"id": "CP-0007", "type": "C3", "status": "done"}]
    assert run(tmp_path, m, checkpoints=cps).exit_code == sg.EXIT_DONE


def test_result_requiring_judgment_review_awaits_until_c4_closes(tmp_path):
    r = {**passing_build(), "safety_critical": True}
    r["versions"] = {**r["versions"], "commit": "abc123"}
    v = run(tmp_path, manifest(), result=r)
    assert v.exit_code == sg.EXIT_AWAITING
    assert "S-AWAITING-REVIEW" in codes(v)


def test_review_satisfied_by_a_closed_c4(tmp_path):
    r = {**passing_build(), "safety_critical": True}
    r["versions"] = {**r["versions"], "commit": "abc123"}
    m = manifest()
    m["obligations"][0]["blocked_by"] = ["CP-0009"]
    cps = [{"id": "CP-0009", "type": "C4", "obligation": "ABS-B07", "status": "done", "closed_by": "Jim",
            "decision": "cases credible; residual failures acceptable"}]
    assert run(tmp_path, m, result=r, checkpoints=cps).exit_code == sg.EXIT_DONE


def test_green_provisional_passes_at_build(tmp_path):
    r = {**passing_build()}
    set_score(r, PROVISIONAL)
    r["versions"] = {**r["versions"], "commit": "abc123"}
    m = manifest()
    m["obligations"][0]["verification"]["bev"]["evidence_state"] = "green-provisional"
    assert run(tmp_path, m, result=r).exit_code == sg.EXIT_DONE


def test_build_stage_evidence_cannot_ship_a_release_slice(tmp_path):
    """The slice moved to release; the evidence is a build-stage provisional pass."""
    r = {**passing_build()}
    set_score(r, PROVISIONAL)   # lower bound below threshold
    r["versions"] = {**r["versions"], "commit": "abc123"}
    m = copy.deepcopy(manifest())
    m["stage"] = "release"
    m["obligations"][0]["verification"]["bev"]["evidence_state"] = "green-provisional"
    v = run(tmp_path, m, result=r)
    assert v.exit_code == sg.EXIT_NOT_DONE
    assert "S-RESULT-MISMATCH" in codes(v)


def test_release_stage_evidence_that_is_inconclusive_blocks(tmp_path):
    """A release-stage run whose lower bound misses the threshold is inconclusive, not awaiting."""
    r = build(passes=PROVISIONAL, stage="release")
    r["result"].pop("threshold")   # the contract's release row (0.92) decides
    r["versions"] = {**r["versions"], "commit": "abc123"}
    m = copy.deepcopy(manifest())
    m["stage"] = "release"
    m["obligations"][0]["verification"]["bev"].pop("evidence_state")
    (tmp_path / "04-evaluation-spec.md").write_text(CONTRACT_MD.replace("| release | >= 0.92 |", "| release | >= 0.90 |"))
    v = run(tmp_path, m, result=r)
    assert v.exit_code == sg.EXIT_NOT_DONE
    f = next(f for f in v.findings if f.code == "S-GATE-FAILED")
    assert "I-LOWER-BOUND" in f.message and "inconclusive" in f.message


# ---------- BEV rows need an earned dimension ----------

@pytest.mark.parametrize("dimension", [None, "", "GAP-02-04", "DISC-D02"])
def test_bev_row_without_an_earned_dimension_is_misrouted(tmp_path, dimension):
    m = manifest()
    m["obligations"][0]["verification"]["bev"]["dimension"] = dimension
    v = run(tmp_path, m)
    assert v.exit_code == sg.EXIT_NOT_DONE
    assert "S-BEV-NO-DIMENSION" in codes(v)


@pytest.mark.parametrize("dimension", ["EVAL-D03", "EVAL-T12"])
def test_bev_row_accepts_scored_and_pass_fail_dimensions(tmp_path, dimension):
    m = manifest()
    m["obligations"][0]["verification"]["bev"]["dimension"] = dimension
    assert "S-BEV-NO-DIMENSION" not in codes(run(tmp_path, m))


# ---------- unmeasured[]: obligations with no earned evaluator ----------

def waiting(**over) -> dict:
    u = {"requirement": "ABS-B09", "gap": "GAP-02-04", "tracing_task": "plan-2026-09-16/task-9",
         "error_analysis": {"trigger": "100 traces", "checkpoint": "CP-0012"}}
    u.update(over)
    return u


def test_waiting_obligation_does_not_block_a_build_slice(tmp_path):
    v = run(tmp_path, manifest(unmeasured=[waiting()]))
    assert v.exit_code == sg.EXIT_DONE, v.findings
    assert [u["requirement"] for u in v.unmeasured] == ["ABS-B09"]


def test_open_error_analysis_checkpoint_does_not_block_a_build_slice(tmp_path):
    cps = [{"id": "CP-0012", "type": "C3", "status": "open"}]
    assert run(tmp_path, manifest(unmeasured=[waiting()]), checkpoints=cps).exit_code == sg.EXIT_DONE


def test_waiting_obligation_with_no_tracing_task_blocks(tmp_path):
    """Without tracing the failure can never be seen, so the evaluator can never be earned."""
    v = run(tmp_path, manifest(unmeasured=[waiting(tracing_task=None)]))
    assert v.exit_code == sg.EXIT_NOT_DONE
    assert "S-UNTRACED" in codes(v)


def test_waiting_obligation_with_no_requirement_is_malformed(tmp_path):
    u = waiting()
    u.pop("requirement")
    v = run(tmp_path, manifest(unmeasured=[u]))
    assert v.exit_code == sg.EXIT_NOT_DONE
    assert "S-MALFORMED" in codes(v)


def test_obligation_both_waiting_and_routed_to_bev_is_double_routed(tmp_path):
    v = run(tmp_path, manifest(unmeasured=[waiting(requirement="ABS-B07")]))
    assert v.exit_code == sg.EXIT_NOT_DONE
    assert "S-DOUBLE-ROUTED" in codes(v)


def test_promoted_obligation_may_stay_listed_once_its_row_exists(tmp_path):
    u = waiting(requirement="ABS-B07", decision={"outcome": "promoted", "dimension": "EVAL-D03"})
    assert run(tmp_path, manifest(unmeasured=[u])).exit_code == sg.EXIT_DONE


def test_promoted_obligation_with_no_bev_row_blocks(tmp_path):
    u = waiting(decision={"outcome": "promoted", "dimension": "EVAL-D05"})
    v = run(tmp_path, manifest(unmeasured=[u]))
    assert v.exit_code == sg.EXIT_NOT_DONE
    assert "S-PROMOTED-NOT-ROUTED" in codes(v)


def test_unknown_decision_outcome_is_malformed(tmp_path):
    v = run(tmp_path, manifest(unmeasured=[waiting(decision={"outcome": "looks-fine"})]))
    assert v.exit_code == sg.EXIT_NOT_DONE
    assert "S-MALFORMED" in codes(v)


def release(**over):
    m = manifest(stage="release", unmeasured=[waiting(**over)])
    m["obligations"] = [m["obligations"][1]]   # TDD-only, so only the unmeasured list is under test
    return m


def test_undecided_waiting_obligation_awaits_a_human_at_release(tmp_path):
    v = run(tmp_path, release())
    assert v.exit_code == sg.EXIT_AWAITING
    assert "S-UNMEASURED-AT-RELEASE" in codes(v)


def closed(cp_id="CP-0012", type_="C3", obligation="ABS-B09", status="done", by="Jim"):
    return {"id": cp_id, "type": type_, "obligation": obligation, "needed": "release decision",
            "status": status, "closed_by": by}


def test_reviewed_with_no_failures_on_enough_traces_releases(tmp_path):
    d = {"outcome": "no-failures-observed", "traces_reviewed": 120, "reviewer": "Jim", "date": "2026-10-01"}
    assert run(tmp_path, release(decision=d), checkpoints=[closed()]).exit_code == sg.EXIT_DONE


def test_no_failures_on_too_few_traces_awaits_and_reports_the_bound(tmp_path):
    d = {"outcome": "no-failures-observed", "traces_reviewed": 30, "reviewer": "Jim", "date": "2026-10-01"}
    v = run(tmp_path, release(decision=d), checkpoints=[closed()])
    assert v.exit_code == sg.EXIT_AWAITING
    f = next(f for f in v.findings if f.code == "S-THIN-REVIEW")
    assert "0.10" in f.message   # rule of three: 3/30


def test_no_failures_without_a_reviewer_awaits(tmp_path):
    d = {"outcome": "no-failures-observed", "traces_reviewed": 120}
    v = run(tmp_path, release(decision=d))
    assert v.exit_code == sg.EXIT_AWAITING
    assert "S-DECISION-UNSIGNED" in codes(v)


def test_deferred_to_production_with_an_approver_releases(tmp_path):
    d = {"outcome": "deferred-to-production", "approver": "Jim", "date": "2026-10-01", "monitor": "06 §6",
         "checkpoint": "CP-0020"}
    assert run(tmp_path, release(decision=d), checkpoints=[closed("CP-0020", "C4")]).exit_code == sg.EXIT_DONE


# ---------- a release decision must be backed by a checkpoint a person closed ----------

NFO = {"outcome": "no-failures-observed", "traces_reviewed": 120, "reviewer": "Jim", "date": "2026-10-01"}


def test_a_reviewer_named_only_in_the_manifest_awaits(tmp_path):
    v = run(tmp_path, release(decision=NFO, error_analysis={"trigger": "100 traces", "checkpoint": None}))
    assert v.exit_code == sg.EXIT_AWAITING
    assert "S-DECISION-UNBACKED" in codes(v)


def test_decision_citing_a_checkpoint_not_in_the_queue_blocks(tmp_path):
    v = run(tmp_path, release(decision=NFO), checkpoints=[])
    assert v.exit_code == sg.EXIT_NOT_DONE
    assert "S-CHECKPOINT-MISSING" in codes(v)


def test_decision_whose_checkpoint_is_still_open_awaits(tmp_path):
    cp = {**closed(status="open"), "closed_by": None}
    v = run(tmp_path, release(decision=NFO), checkpoints=[cp])
    assert v.exit_code == sg.EXIT_AWAITING
    assert "S-CHECKPOINT-OPEN" in codes(v)


def test_decision_whose_checkpoint_was_declined_blocks(tmp_path):
    v = run(tmp_path, release(decision=NFO), checkpoints=[closed(status="declined")])
    assert v.exit_code == sg.EXIT_NOT_DONE
    assert "S-DECISION-UNBACKED" in codes(v)


def test_decision_whose_checkpoint_has_no_closer_blocks(tmp_path):
    v = run(tmp_path, release(decision=NFO), checkpoints=[closed(by="")])
    assert v.exit_code == sg.EXIT_NOT_DONE
    assert "S-DECISION-UNBACKED" in codes(v)


def test_agent_writing_a_different_reviewer_than_the_closer_blocks(tmp_path):
    v = run(tmp_path, release(decision=NFO), checkpoints=[closed(by="Ana")])
    assert v.exit_code == sg.EXIT_NOT_DONE
    f = next(f for f in v.findings if f.code == "S-DECISION-UNBACKED")
    assert "Ana" in f.message and "Jim" in f.message


def test_reviewer_match_ignores_case_and_spaces(tmp_path):
    assert run(tmp_path, release(decision=NFO), checkpoints=[closed(by=" jim ")]).exit_code == sg.EXIT_DONE


def test_checkpoint_for_another_obligation_does_not_back_the_decision(tmp_path):
    v = run(tmp_path, release(decision=NFO), checkpoints=[closed(obligation="ABS-B07")])
    assert v.exit_code == sg.EXIT_NOT_DONE
    assert "S-DECISION-UNBACKED" in codes(v)


def test_no_failures_needs_a_c3_not_a_c4(tmp_path):
    v = run(tmp_path, release(decision=NFO), checkpoints=[closed(type_="C4")])
    assert v.exit_code == sg.EXIT_NOT_DONE
    assert "S-DECISION-UNBACKED" in codes(v)


def test_decision_checkpoint_overrides_the_trigger_checkpoint(tmp_path):
    d = {**NFO, "checkpoint": "CP-0030"}
    v = run(tmp_path, release(decision=d), checkpoints=[closed(), closed("CP-0030", by="Ana")])
    assert "S-DECISION-UNBACKED" in codes(v)   # CP-0030 is the one cited, and Ana closed it


def test_deferral_with_no_checkpoint_awaits(tmp_path):
    d = {"outcome": "deferred-to-production", "approver": "Jim", "monitor": "06 §6"}
    v = run(tmp_path, release(decision=d))
    assert v.exit_code == sg.EXIT_AWAITING
    assert "S-DECISION-UNBACKED" in codes(v)


def test_deferral_needs_a_c4_not_a_c3(tmp_path):
    d = {"outcome": "deferred-to-production", "approver": "Jim", "checkpoint": "CP-0012"}
    v = run(tmp_path, release(decision=d), checkpoints=[closed()])
    assert v.exit_code == sg.EXIT_NOT_DONE
    assert "S-DECISION-UNBACKED" in codes(v)


def test_backing_is_not_checked_at_build(tmp_path):
    m = release(decision=NFO)
    m["stage"] = "build"
    assert run(tmp_path, m).exit_code == sg.EXIT_DONE


def test_deferred_to_production_without_an_approver_awaits(tmp_path):
    v = run(tmp_path, release(decision={"outcome": "deferred-to-production"}))
    assert v.exit_code == sg.EXIT_AWAITING
    assert "S-DECISION-UNSIGNED" in codes(v)


def test_min_traces_is_configurable(tmp_path):
    d = {"outcome": "no-failures-observed", "traces_reviewed": 30, "reviewer": "Jim"}
    path = write(tmp_path, release(decision=d), checkpoints=[closed()])
    assert sg.evaluate_slice(path, checkpoints=tmp_path / "checkpoints.yaml", min_traces=30).exit_code == sg.EXIT_DONE


# ---------- ledger and trace index pass through to the gate-check ----------

def committed():
    r = passing_build()
    r["versions"] = {**r["versions"], "commit": "abc123"}
    return r


def write_evidence(tmp_path, r, ledger=None, traces=None):
    import json as _json
    (tmp_path / "runs.jsonl").write_text("\n".join(_json.dumps(e) for e in (ledger if ledger is not None else ledger_for(r, commit=(r.get("versions") or {}).get("commit") or "abc123"))))
    idx = traces if traces is not None else trace_index_for(r)
    (tmp_path / "traces.jsonl").write_text("\n".join(_json.dumps({"trace_id": t, "span_ids": sorted(s or [])}) for t, s in idx.items()))


def test_manifest_ledger_and_traces_are_used(tmp_path):
    r = committed()
    write_evidence(tmp_path, r)
    path = write(tmp_path, manifest(ledger="runs.jsonl", traces="traces.jsonl"), result=r)
    assert sg.evaluate_slice(path).exit_code == sg.EXIT_DONE


def test_omitted_run_in_the_manifest_ledger_blocks_the_slice(tmp_path):
    r = committed()
    extra = {**ledger_for(r)[0], "run_id": "run-9"}
    write_evidence(tmp_path, r, ledger=ledger_for(r) + [extra])
    path = write(tmp_path, manifest(ledger="runs.jsonl", traces="traces.jsonl"), result=r)
    v = sg.evaluate_slice(path)
    assert v.exit_code == sg.EXIT_NOT_DONE
    assert "S-GATE-FAILED" in codes(v) and "F-RUNS-OMITTED" in next(f.message for f in v.findings if f.code == "S-GATE-FAILED")


def test_missing_trace_blocks_the_slice(tmp_path):
    r = committed()
    idx = trace_index_for(r)
    idx.pop(next(iter(idx)))
    write_evidence(tmp_path, r, traces=idx)
    path = write(tmp_path, manifest(ledger="runs.jsonl", traces="traces.jsonl"), result=r)
    assert sg.evaluate_slice(path).exit_code == sg.EXIT_NOT_DONE


def test_cli_ledger_flag_overrides_the_manifest(tmp_path):
    r = committed()
    write_evidence(tmp_path, r)
    path = write(tmp_path, manifest(ledger="nowhere.jsonl"), result=r)
    assert sg.main([str(path), "--ledger", str(tmp_path / "runs.jsonl"), "--traces", str(tmp_path / "traces.jsonl")]) == sg.EXIT_DONE


def test_missing_ledger_file_is_usage_error(tmp_path):
    path = write(tmp_path, manifest(ledger="nowhere.jsonl"))
    assert sg.main([str(path)]) == sg.EXIT_USAGE


# ---------- usage: exit 3 ----------

def test_missing_manifest_is_usage_error(tmp_path):
    assert sg.main([str(tmp_path / "nope.yaml")]) == sg.EXIT_USAGE


def test_unparseable_manifest_is_usage_error(tmp_path):
    p = tmp_path / "manifest.yaml"
    p.write_text("{not: [valid")
    assert sg.main([str(p)]) == sg.EXIT_USAGE


# ---------- CLI ----------

def test_cli_json_lists_every_obligation(tmp_path):
    path = write(tmp_path, manifest())
    proc = subprocess.run([sys.executable, str(TOOLS / "slice_gate.py"), str(path), "--json"], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["exit_code"] == 0 and len(out["obligations"]) == 2
    assert {o["requirement"] for o in out["obligations"]} == {"ABS-B07", "ABS-B08"}


def test_cli_lists_waiting_obligations_without_blocking(tmp_path):
    path = write(tmp_path, manifest(unmeasured=[waiting()]))
    proc = subprocess.run([sys.executable, str(TOOLS / "slice_gate.py"), str(path)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout
    assert "ABS-B09" in proc.stdout and "GAP-02-04" in proc.stdout


def test_cli_reports_what_blocks(tmp_path):
    m = manifest()
    m["obligations"][0]["verification"]["bev"]["evidence_state"] = "red"
    path = write(tmp_path, m)
    proc = subprocess.run([sys.executable, str(TOOLS / "slice_gate.py"), str(path)], capture_output=True, text=True)
    assert proc.returncode == 1
    assert "ABS-B07" in proc.stdout and "S-STATE-MISMATCH" in proc.stdout


# ---------- review pass 1: the slice gate no longer trusts the manifest ----------

def committed_result(**over):
    r = passing_build()
    r["versions"] = {**r["versions"], "commit": "abc123"}
    r.update(over)
    return r


@pytest.mark.parametrize("field,value", [("obligation", "ABS-B99"), ("dimension", "EVAL-D09"), ("stage", "release")])
def test_result_must_belong_to_the_row_that_cites_it(tmp_path, field, value):
    v = run(tmp_path, manifest(), result=committed_result(**{field: value}))
    assert v.exit_code == sg.EXIT_NOT_DONE
    assert "S-RESULT-MISMATCH" in codes(v)


def test_one_result_cannot_serve_two_requirements(tmp_path):
    m = manifest()
    other = copy.deepcopy(m["obligations"][0])
    other["requirement"] = "ABS-B10"
    m["obligations"].append(other)
    v = run(tmp_path, m)
    assert v.exit_code == sg.EXIT_NOT_DONE
    assert "S-RESULT-MISMATCH" in codes(v)


def test_release_slice_citing_a_provisional_build_result_as_green_is_blocked(tmp_path):
    """The exploit the review ran: manifest says release + green; the evidence is build + provisional."""
    r = committed_result()
    set_score(r, PROVISIONAL)
    v = run(tmp_path, manifest(stage="release"), result=r)
    assert v.exit_code == sg.EXIT_NOT_DONE
    assert {"S-RESULT-MISMATCH", "S-STATE-MISMATCH"} <= codes(v)


def test_manifest_state_must_equal_the_gate_verdict(tmp_path):
    r = committed_result()
    set_score(r, PROVISIONAL)   # the gate says green-provisional
    v = run(tmp_path, manifest(), result=r)   # the manifest says green
    assert v.exit_code == sg.EXIT_NOT_DONE
    assert "S-STATE-MISMATCH" in codes(v)


@pytest.mark.parametrize("key", ["commit"])
def test_bev_row_needs_the_slice_commit(tmp_path, key):
    m = manifest()
    m.pop(key)
    v = run(tmp_path, m)
    assert v.exit_code == sg.EXIT_NOT_DONE
    assert "S-NO-COMMIT" in codes(v)


def test_result_without_a_commit_is_stale_not_skipped(tmp_path):
    r = passing_build()   # no versions.commit
    v = run(tmp_path, manifest(), result=r)
    assert v.exit_code == sg.EXIT_NOT_DONE


@pytest.mark.parametrize("key,code", [("ledger", "S-NO-LEDGER"), ("traces", "S-NO-TRACES")])
def test_bev_row_needs_a_ledger_and_a_trace_export(tmp_path, key, code):
    m = manifest()
    m.pop(key)
    v = run(tmp_path, m)
    assert v.exit_code == sg.EXIT_NOT_DONE
    assert code in codes(v)


def test_tdd_only_slice_needs_no_ledger_or_traces(tmp_path):
    m = manifest()
    m.pop("ledger"); m.pop("traces")
    m["obligations"] = [m["obligations"][1]]
    assert run(tmp_path, m).exit_code == sg.EXIT_DONE


def test_trace_export_without_spans_blocks_when_spans_are_cited(tmp_path):
    r = committed_result()
    write_evidence(tmp_path, r, traces={t: None for t in trace_index_for(r)})
    (tmp_path / "traces.jsonl").write_text("\n".join(trace_index_for(r)))
    v = run(tmp_path, manifest(), result=r)
    assert v.exit_code == sg.EXIT_NOT_DONE
    assert "S-SPANS-UNCHECKED" in codes(v)


def review_needed():
    return committed_result(safety_critical=True)


def test_c4_closed_for_another_obligation_does_not_count(tmp_path):
    cps = [{"id": "CP-0009", "type": "C4", "obligation": "ABS-B99", "status": "done"}]
    v = run(tmp_path, manifest(), result=review_needed(), checkpoints=cps)
    assert v.exit_code == sg.EXIT_AWAITING
    assert "S-AWAITING-REVIEW" in codes(v)


@pytest.mark.parametrize("status", ["declined", "pending", "in-progress"])
def test_c4_counts_only_when_done(tmp_path, status):
    cps = [{"id": "CP-0009", "type": "C4", "obligation": "ABS-B07", "status": status}]
    v = run(tmp_path, manifest(), result=review_needed(), checkpoints=cps)
    assert "S-AWAITING-REVIEW" in codes(v)


@pytest.mark.parametrize("status", ["pending", "in-progress", "waiting"])
def test_unknown_checkpoint_status_is_open(tmp_path, status):
    m = manifest()
    m["obligations"][0]["blocked_by"] = ["CP-0007"]
    cps = [{"id": "CP-0007", "type": "C3", "status": status}]
    assert "S-CHECKPOINT-OPEN" in codes(run(tmp_path, m, checkpoints=cps))


@pytest.mark.parametrize("routing,tdd,bev", [
    ("tdd", True, True), ("both", True, False), ("both", False, True), ("bev", True, True),
    ("BEV_ONLY", False, False), ("sideways", True, True),
])
def test_routing_must_agree_with_what_is_required(tmp_path, routing, tdd, bev):
    m = manifest()
    ob = m["obligations"][0]
    ob["routing"] = routing
    ob["verification"]["tdd"]["required"] = tdd
    ob["verification"]["bev"]["required"] = bev
    v = run(tmp_path, m)
    assert v.exit_code == sg.EXIT_NOT_DONE
    assert "S-ROUTING-MISMATCH" in codes(v)


@pytest.mark.parametrize("routing,tdd,bev", [
    ("TDD_AND_BEV", True, True), ("BEV_ONLY", False, True), ("TDD_ONLY", True, False),
    ("bev", False, True), ("MANUAL_GOVERNANCE", False, False), ("MEASUREMENT_ONLY", False, False),
])
def test_classifier_routes_are_accepted(tmp_path, routing, tdd, bev):
    m = manifest()
    ob = m["obligations"][0]
    ob["routing"] = routing
    ob["verification"]["tdd"]["required"] = tdd
    ob["verification"]["bev"]["required"] = bev
    assert "S-ROUTING-MISMATCH" not in codes(run(tmp_path, m))


def test_a_result_that_crashes_the_gate_blocks_instead_of_exiting(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise TypeError("bad value")
    monkeypatch.setattr(sg.gate_check, "evaluate", boom)
    v = run(tmp_path, manifest())
    assert v.exit_code == sg.EXIT_NOT_DONE
    assert "S-GATE-ERROR" in codes(v)


def test_duplicate_rows_cannot_count_one_result_twice(tmp_path):
    m = manifest()
    m["obligations"].append(copy.deepcopy(m["obligations"][0]))
    v = run(tmp_path, m)
    assert v.exit_code == sg.EXIT_NOT_DONE
    assert any(f.code == "S-RESULT-MISMATCH" and "already the evidence" in f.message for f in v.findings)


# ---------- review pass 2: the contract, and a state nobody copies ----------

def test_bev_slice_needs_the_04_contract(tmp_path):
    m = manifest()
    m.pop("contract")
    v = run(tmp_path, m)
    assert v.exit_code == sg.EXIT_NOT_DONE and "S-NO-CONTRACT" in codes(v)


def test_the_contract_threshold_decides(tmp_path):
    """The result says 0.90; 04 says 0.97 for build. The gate uses 04, and the reported one conflicts."""
    (tmp_path / "04-evaluation-spec.md").write_text(CONTRACT_MD.replace("| build | ≥ 0.90 |", "| build | ≥ 0.97 |"))
    v = run(tmp_path, manifest())
    assert v.exit_code == sg.EXIT_NOT_DONE
    assert "F-CONTRACT" in next(f.message for f in v.findings if f.code == "S-GATE-FAILED")


def test_state_is_derived_when_the_manifest_omits_it(tmp_path):
    m = manifest()
    m["obligations"][0]["verification"]["bev"].pop("evidence_state")
    r = committed_result()
    set_score(r, PROVISIONAL)
    v = run(tmp_path, m, result=r)
    assert v.exit_code == sg.EXIT_DONE, v.findings
    assert v.obligations[0]["evidence_state"] == "green-provisional"


def test_a_red_result_reports_its_derived_state(tmp_path):
    m = manifest()
    m["obligations"][0]["verification"]["bev"].pop("evidence_state")
    r = committed_result()
    set_score(r, (98, 99, 100))
    v = run(tmp_path, m, result=r)
    assert v.exit_code == sg.EXIT_NOT_DONE
    assert v.obligations[0]["evidence_state"] == "red"


def test_invalid_evidence_is_reported_as_such(tmp_path):
    m = manifest()
    r = committed_result(split="dev")
    v = run(tmp_path, m, result=r)
    assert v.obligations[0]["evidence_state"] == "invalid evidence"
    assert "S-STATE-MISMATCH" not in codes(v) and "S-GATE-FAILED" in codes(v)


def test_cli_contract_flag_overrides_the_manifest(tmp_path):
    path = write(tmp_path, manifest(contract="nowhere.md"))
    assert sg.main([str(path), "--contract", str(tmp_path / "04-evaluation-spec.md")]) == sg.EXIT_DONE


# ---------- custody: a C4 is closed by a named person ----------

@pytest.mark.parametrize("closed_by", [None, "", "  "])
def test_c4_without_a_named_closer_does_not_count(tmp_path, closed_by):
    cps = [{"id": "CP-0009", "type": "C4", "obligation": "ABS-B07", "status": "done", "closed_by": closed_by}]
    v = run(tmp_path, manifest(), result=review_needed(), checkpoints=cps)
    assert "S-AWAITING-REVIEW" in codes(v)


def test_manifest_names_the_checkpoint_queue(tmp_path):
    cps = [{"id": "CP-0009", "type": "C4", "obligation": "ABS-B07", "status": "done", "closed_by": "Jim"}]
    path = write(tmp_path, manifest(checkpoints="checkpoints.yaml"), result=review_needed(), checkpoints=cps)
    assert sg.evaluate_slice(path).exit_code == sg.EXIT_DONE


def test_manifest_paths_expand_the_home_directory(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "ev").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    r = committed_result()
    write_evidence(home / "ev", r)
    path = write(tmp_path, manifest(ledger="~/ev/runs.jsonl", traces="~/ev/traces.jsonl"), result=r)
    assert sg.evaluate_slice(path).exit_code == sg.EXIT_DONE
