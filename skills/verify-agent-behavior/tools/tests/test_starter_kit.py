"""The starter kit end to end: a harness logs a baseline and a candidate in a real git repo,
the trace store's OTLP export becomes the trace index, the adapter writes the result, and the
gate passes it against the 04 contract. Then the kit's guard rails."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import bev_harness as bh  # noqa: E402
import export_traces as ex  # noqa: E402
import gate_check as gc  # noqa: E402
import judge_to_eval_result as ad  # noqa: E402
import slice_gate as sg  # noqa: E402

TEMPLATES = TOOLS.parent / "templates"
CONTRACT = """### 4.2 Offline contract

| `EVAL-nn` | Stage | Threshold | Method |
|---|---|---|---|
| `EVAL-D01` | build | ≥ 0.80 | model |
"""


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "prompt.txt").write_text("v1")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "v1")
    return tmp_path


def fake_agent(run_tag, i, passes, spans):
    """A traced agent: returns an OTLP span per case and a verdict."""
    trace_id = f"{run_tag}{i:04d}".encode().hex()
    span_id = f"s{run_tag}{i:03d}".encode().hex()
    spans.append({"traceId": trace_id, "spanId": span_id, "name": "agent"})
    return trace_id, span_id, int(i < passes)


def record_run(h, run_tag, passes, spans, purpose=None):
    with h.run(purpose=purpose, run_id=f"run-{run_tag}") as run:
        for i in range(40):
            trace_id, span_id, verdict = fake_agent(run_tag, i, passes, spans)
            run.case(f"case-{i:03d}", trace_id, verdict, "ok" if verdict else "wrong test booked", [span_id])
    return f"run-{run_tag}"


def labels():
    pairs = [(1, 1)] * 48 + [(1, 0)] * 2 + [(0, 0)] * 48 + [(0, 1)] * 2
    return [{"item_id": f"lab-{i}", "human": h, "judge": j} for i, (h, j) in enumerate(pairs)]


def test_the_kit_end_to_end(repo):
    work = repo / "bev"
    spans: list[dict] = []
    h = bh.Harness("EVAL-D01", "cs-v1", work, repo=repo)
    base = [record_run(h, f"b{k}", 20, spans, purpose="baseline") for k in range(3)]
    (repo / "prompt.txt").write_text("v2")
    git(repo, "commit", "-qam", "v2")
    runs = [record_run(h, f"c{k}", 38 + k % 2, spans) for k in range(3)]
    head = git(repo, "rev-parse", "HEAD")

    lines = [json.loads(l) for l in (work / "runs.jsonl").read_text().splitlines()]
    assert [l["purpose"] for l in lines[:3]] == ["baseline"] * 3 and all(l["commit"] == head for l in lines[3:])

    otlp = repo / "otlp.json"
    otlp.write_text("\n".join(json.dumps({"resourceSpans": [{"scopeSpans": [{"spans": [s]}]}]}) for s in spans))
    assert ex.main([str(otlp), "--out", str(work / "traces.jsonl")]) == 0

    h.write_judge_run(work / "judge-run.yaml", runs=runs, baseline_runs=base, judge_items=labels(), labels_version="v1")
    template = yaml.safe_load((TEMPLATES / "eval-result-template.yaml").read_text())
    template["case_set"]["version"] = template["baseline"]["case_set_version"] = "cs-v1"
    template["versions"].update(commit=head, judge="jp1")
    template["baseline"]["judge"] = "jp1"
    result = ad.merge(template, ad.build(yaml.safe_load((work / "judge-run.yaml").read_text())))
    (work / "EVAL-D01.yaml").write_text(yaml.safe_dump(result))
    (repo / "04.md").write_text(CONTRACT)

    v = gc.evaluate(result, ledger=gc.load_ledger(work / "runs.jsonl"),
                    trace_index=gc.load_trace_index(work / "traces.jsonl"), contract=gc.load_contract(repo / "04.md"))
    assert v.exit_code == gc.EXIT_PASS, v.findings
    assert not [f for f in v.findings if f.severity == "warning" and f.code != "W-PROVISIONAL"]

    m = yaml.safe_load((TEMPLATES / "verification-manifest.yaml").read_text())
    m.update(commit=head, contract="04.md", ledger="bev/runs.jsonl", traces="bev/traces.jsonl",
             checkpoints="bev/checkpoints.yaml", unmeasured=[])
    m["obligations"] = [m["obligations"][0]]
    ob = m["obligations"][0]
    ob.update(accepted=True)
    ob["verification"]["tdd"]["state"] = "green"
    ob["verification"]["bev"]["last_result"] = "bev/EVAL-D01.yaml"
    (repo / "manifest.yaml").write_text(yaml.safe_dump(m))
    s = sg.evaluate_slice(repo / "manifest.yaml")
    assert s.exit_code == sg.EXIT_DONE, s.findings


def test_a_crashed_run_stays_in_the_ledger(repo):
    h = bh.Harness("EVAL-D01", "cs-v1", repo / "bev", repo=repo)
    with pytest.raises(ZeroDivisionError):
        with h.run(run_id="run-x") as run:
            run.case("case-0", "t0", 1)
            1 / 0
    assert "run-x" in (repo / "bev/runs.jsonl").read_text()
    assert not (repo / "bev/records/run-x.json").exists()


def test_a_dirty_tree_is_refused(repo):
    (repo / "prompt.txt").write_text("uncommitted")
    h = bh.Harness("EVAL-D01", "cs-v1", repo / "bev", repo=repo)
    with pytest.raises(RuntimeError, match="uncommitted"):
        with h.run():
            pass


@pytest.mark.parametrize("args,match", [
    (("c", "t", 0.8), "0 or 1"), (("c", "t", True), "0 or 1"), (("", "t", 1), "test_case_id"), (("c", "", 1), "trace_id"),
])
def test_the_recorder_refuses_bad_cases(args, match):
    r = bh.RunRecorder("run-1")
    with pytest.raises(ValueError, match=match):
        r.case(*args)


def test_the_recorder_refuses_a_duplicate_case():
    r = bh.RunRecorder("run-1")
    r.case("c", "t", 1)
    with pytest.raises(ValueError, match="twice"):
        r.case("c", "t2", 0)


def test_an_empty_run_is_refused(repo):
    h = bh.Harness("EVAL-D01", "cs-v1", repo / "bev", repo=repo)
    with pytest.raises(RuntimeError, match="no cases"):
        with h.run():
            pass


def test_bad_split_or_purpose_is_refused(repo):
    h = bh.Harness("EVAL-D01", "cs-v1", repo / "bev", repo=repo)
    with pytest.raises(ValueError):
        with h.run(split="train"):
            pass
    with pytest.raises(ValueError):
        with h.run(purpose="verify"):
            pass


def test_judge_run_cli(repo):
    h = bh.Harness("EVAL-D01", "cs-v1", repo / "bev", commit="abc")
    spans: list = []
    ids = [record_run(h, t, 30, spans) for t in ("a", "b")]
    (repo / "labels.jsonl").write_text("\n".join(json.dumps(l) for l in labels()))
    out = repo / "jr.yaml"
    assert bh.main(["judge-run", "--workdir", str(repo / "bev"), "--runs", ids[0], "--baseline", ids[1],
                    "--labels", str(repo / "labels.jsonl"), "--out", str(out)]) == 0
    doc = yaml.safe_load(out.read_text())
    assert len(doc["judge_validation"]["items"]) == 100 and doc["runs"][0]["run_id"] == ids[0]
    assert bh.main(["judge-run", "--workdir", str(repo / "bev"), "--runs", "run-nope", "--baseline", ids[1],
                    "--out", str(out)]) == 3


def test_exporter_reads_one_object_or_json_lines(tmp_path):
    one = {"resourceSpans": [{"scopeSpans": [{"spans": [{"traceId": "aa", "spanId": "01"}, {"traceId": "aa", "spanId": "02"}]}]}]}
    (tmp_path / "a.json").write_text(json.dumps(one, indent=2))
    (tmp_path / "b.jsonl").write_text(json.dumps({"resourceSpans": [{"scopeSpans": [{"spans": [{"traceId": "bb", "spanId": "03"}]}]}]}))
    assert ex.collect([tmp_path / "a.json", tmp_path / "b.jsonl"]) == {"aa": {"01", "02"}, "bb": {"03"}}


def test_exporter_rejects_spans_without_ids(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps({"resourceSpans": [{"scopeSpans": [{"spans": [{"traceId": "aa"}]}]}]}))
    assert ex.main([str(tmp_path / "a.json"), "--out", str(tmp_path / "t.jsonl")]) == 3


def test_templates_parse_and_route_cleanly():
    m = yaml.safe_load((TEMPLATES / "verification-manifest.yaml").read_text())
    assert {o["routing"] for o in m["obligations"]} <= set(sg.ROUTES)
    t = yaml.safe_load((TEMPLATES / "eval-result-template.yaml").read_text())
    assert {"obligation", "dimension", "stage", "split", "method", "baseline"} <= set(t)


def test_evidence_can_live_outside_the_repo(repo, tmp_path_factory, monkeypatch):
    """The RUNBOOK's advice: keep the ledger where the building agent can't rewrite it."""
    outside = tmp_path_factory.mktemp("custody") / "tvr"
    monkeypatch.chdir(repo)
    h = bh.Harness("EVAL-D01", "cs-v1", outside)          # repo defaults to the current directory
    with h.run(run_id="run-o") as run:
        run.case("c", "t", 1)
    entry = json.loads((outside / "runs.jsonl").read_text())
    assert entry["commit"] == git(repo, "rev-parse", "HEAD")
