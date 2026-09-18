"""The worked example in examples/slice/ (used by RUNBOOK.md) must keep running end to end."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

TOOLS = Path(__file__).resolve().parents[1]
EXAMPLE = TOOLS.parents[2] / "examples" / "slice"


def tool(name, *args):
    return subprocess.run([sys.executable, str(TOOLS / name), *map(str, args)], capture_output=True, text=True)


def copy(tmp_path) -> Path:
    d = tmp_path / "slice"
    shutil.copytree(EXAMPLE, d)
    return d


def test_adapter_reproduces_the_checked_in_result(tmp_path):
    out = tmp_path / "EVAL-D02.yaml"
    proc = tool("judge_to_eval_result.py", EXAMPLE / "judge-run.yaml", "--template", EXAMPLE / "eval-result-template.yaml", "--out", out)
    assert proc.returncode == 0, proc.stderr
    assert yaml.safe_load(out.read_text()) == yaml.safe_load((EXAMPLE / "results/EVAL-D02.yaml").read_text())


def test_gate_passes_the_example_as_green_provisional():
    proc = tool("gate_check.py", EXAMPLE / "results/EVAL-D02.yaml", "--contract", EXAMPLE / "04-evaluation-spec.md",
                "--ledger", EXAMPLE / "runs.jsonl", "--traces", EXAMPLE / "traces.jsonl", "--json")
    out = json.loads(proc.stdout)
    assert proc.returncode == 0 and out["evidence_state_after"] == "green-provisional"
    assert out["computed"]["threshold"] == 0.85
    assert not [f for f in out["findings"] if f["severity"] == "warning" and f["code"] != "W-PROVISIONAL"]


def test_a_forged_interval_in_the_example_is_caught(tmp_path):
    d = copy(tmp_path)
    r = yaml.safe_load((d / "results/EVAL-D02.yaml").read_text())
    r["result"]["ci95"] = [0.9, 1.0]
    (d / "results/EVAL-D02.yaml").write_text(yaml.safe_dump(r))
    proc = tool("slice_gate.py", d / "verification-manifest.yaml", "--checkpoints", d / "bev/checkpoints.yaml")
    assert proc.returncode == 1 and "F-RECOMPUTE" in proc.stdout


def test_slice_is_done_at_build():
    proc = tool("slice_gate.py", EXAMPLE / "verification-manifest.yaml", "--checkpoints", EXAMPLE / "bev/checkpoints.yaml")
    assert proc.returncode == 0, proc.stdout
    assert "ABS-B05" in proc.stdout


def test_an_unreported_held_out_run_fails_the_example(tmp_path):
    d = copy(tmp_path)
    with (d / "runs.jsonl").open("a") as f:
        f.write(json.dumps({"run_id": "run-2026-09-16-4", "dimension": "EVAL-D02", "split": "held-out",
                            "case_set_version": "tvr-heldout-v1", "commit": "9e1d2c4"}) + "\n")
    proc = tool("gate_check.py", d / "results/EVAL-D02.yaml", "--contract", d / "04-evaluation-spec.md",
                "--ledger", d / "runs.jsonl", "--traces", d / "traces.jsonl")
    assert proc.returncode == 1 and "F-RUNS-OMITTED" in proc.stdout


def test_the_example_awaits_a_human_at_release(tmp_path):
    d = copy(tmp_path)
    m = yaml.safe_load((d / "verification-manifest.yaml").read_text())
    m["stage"] = "release"
    (d / "verification-manifest.yaml").write_text(yaml.safe_dump(m))
    proc = tool("slice_gate.py", d / "verification-manifest.yaml", "--checkpoints", d / "bev/checkpoints.yaml")
    assert proc.returncode == 1   # build-stage evidence can't stand in for release evidence
    assert "S-RESULT-MISMATCH" in proc.stdout and "S-UNMEASURED-AT-RELEASE" in proc.stdout
