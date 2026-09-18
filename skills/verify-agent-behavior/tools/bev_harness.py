#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml"]
# ///
"""A small helper for an eval harness: log every run, record every case, assemble the judge run.

Import it from your harness (copy it, or add `<skill>/tools` to `sys.path`):

    from bev_harness import Harness

    h = Harness("EVAL-D02", case_set_version="tvr-heldout-v1", workdir="../bev-evidence/tvr", repo=".")
    with h.run(split="held-out", purpose="baseline") as run:      # purpose only for baseline runs
        for case in cases:
            out, trace_id = my_agent(case)                          # your agent, traced
            verdict, critique, spans = my_judge(case, out)          # your judge or code check
            run.case(case.id, trace_id, verdict, critique, spans)

    h.write_judge_run("evals/bev/judge-run.yaml", runs=[...], baseline_runs=[...],
                      judge_items=labels)                            # omit judge_items if not model-scored

**The ledger line is written when a run starts, before any result exists.** A run that crashes
or is abandoned stays in the ledger, and the gate will refuse a result that leaves it out
(`F-RUNS-OMITTED`): fix the problem and rerun at a new commit. That is the point — a failing run
can't be quietly dropped.

Files, under `workdir`:
    runs.jsonl              the ledger (append-only; keep it where the building agent can't rewrite it)
    records/<run_id>.json   one run's per-case records

**Keep `workdir` out of git's tracked files** (outside the repo, or ignored). Every run refuses a
dirty tree so the commit it logs is the code it ran; a tracked ledger would dirty the tree itself.

CLI, to assemble a judge run from recorded runs:

    uv run <skill>/tools/bev_harness.py judge-run --workdir evals/bev --runs run-a run-b run-c \\
        --baseline base-a base-b base-c [--labels labels.jsonl] --out evals/bev/judge-run.yaml

`labels.jsonl` holds one `{"item_id": ..., "human": 0|1, "judge": 0|1}` per line.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import subprocess
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path

SPLITS = {"dev", "held-out"}


def git_commit(cwd: str | Path | None = None) -> str:
    """The current commit, refusing a dirty tree: evidence must pin a real code state."""
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=cwd,
                           capture_output=True, text=True, check=True).stdout.strip()
    if dirty:
        raise RuntimeError("the working tree has uncommitted changes: commit them, so the evidence pins the code it ran")
    return head


class RunRecorder:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.cases: list[dict] = []
        self._seen: set[str] = set()

    def case(self, test_case_id: str, trace_id: str, verdict: int, critique: str = "",
             evidence_span_ids=(), red_lines=()) -> None:
        if verdict not in (0, 1) or isinstance(verdict, (bool, float)):
            raise ValueError(f"{test_case_id}: verdict must be 0 or 1, never a score")
        if not test_case_id or not trace_id:
            raise ValueError("every case needs a test_case_id and the trace_id your tracer assigned")
        if test_case_id in self._seen:
            raise ValueError(f"{test_case_id} recorded twice in run {self.run_id}")
        self._seen.add(test_case_id)
        rec = {"test_case_id": test_case_id, "trace_id": trace_id, "verdict": verdict}
        if critique:
            rec["critique"] = critique
        if evidence_span_ids:
            rec["evidence_span_ids"] = list(evidence_span_ids)
        if red_lines:
            rec["red_lines"] = list(red_lines)
        self.cases.append(rec)


class Harness:
    def __init__(self, dimension: str, case_set_version: str, workdir: str | Path = ".",
                 commit: str | None = None, repo: str | Path | None = None):
        """`repo` is the project under test (default: the current directory); its HEAD is the commit logged."""
        self.dimension = dimension
        self.repo = Path(repo) if repo is not None else Path.cwd()
        self.case_set_version = case_set_version
        self.workdir = Path(workdir)
        self.commit = commit
        self.ledger = self.workdir / "runs.jsonl"
        self.records = self.workdir / "records"

    @contextmanager
    def run(self, split: str = "held-out", purpose: str | None = None, run_id: str | None = None):
        if split not in SPLITS:
            raise ValueError(f"split must be one of {sorted(SPLITS)}")
        if purpose not in (None, "baseline"):
            raise ValueError("purpose is 'baseline' or omitted")
        commit = self.commit or git_commit(self.repo)
        run_id = run_id or f"run-{_dt.datetime.now(_dt.timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"
        entry = {"run_id": run_id, "dimension": self.dimension, "split": split,
                 "case_set_version": self.case_set_version, "commit": commit,
                 "started": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")}
        if purpose:
            entry["purpose"] = purpose
        self.workdir.mkdir(parents=True, exist_ok=True)
        with self.ledger.open("a") as f:          # logged before any case runs
            f.write(json.dumps(entry) + "\n")
        recorder = RunRecorder(run_id)
        yield recorder
        if not recorder.cases:
            raise RuntimeError(f"run {run_id} recorded no cases; it stays in the ledger — rerun at a new commit")
        self.records.mkdir(parents=True, exist_ok=True)
        (self.records / f"{run_id}.json").write_text(json.dumps({"run_id": run_id, "cases": recorder.cases}, indent=1))

    def load(self, run_id: str) -> dict:
        return json.loads((self.records / f"{run_id}.json").read_text())

    def write_judge_run(self, path: str | Path, runs: list[str], baseline_runs: list[str],
                        judge_items: list[dict] | None = None, labels_version: str | None = None) -> Path:
        import yaml

        doc: dict = {}
        if judge_items is not None:
            doc["judge_validation"] = {"labels": labels_version, "items": list(judge_items)}
        doc["baseline_runs"] = [self.load(r) for r in baseline_runs]
        doc["runs"] = [self.load(r) for r in runs]
        path = Path(path)
        path.write_text(yaml.safe_dump(doc, sort_keys=False))
        return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="assemble a judge run from recorded runs")
    sub = ap.add_subparsers(dest="cmd", required=True)
    jr = sub.add_parser("judge-run")
    jr.add_argument("--workdir", type=Path, required=True)
    jr.add_argument("--runs", nargs="+", required=True)
    jr.add_argument("--baseline", nargs="+", required=True)
    jr.add_argument("--labels", type=Path, help="JSON lines: item_id, human, judge")
    jr.add_argument("--labels-version")
    jr.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    items = None
    if args.labels:
        items = [json.loads(line) for line in args.labels.read_text().splitlines() if line.strip()]
    h = Harness("-", "-", args.workdir)
    try:
        h.write_judge_run(args.out, args.runs, args.baseline, items, args.labels_version)
    except FileNotFoundError as e:
        print(f"INVALID  no records for {Path(e.filename).stem}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
