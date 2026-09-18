#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml"]
# ///
"""Slice gate: is a vertical slice done, across tasks, obligations and checkpoints?

    uv run <skill>/tools/slice_gate.py verification-manifest.yaml [--checkpoints bev/checkpoints.yaml]
        [--contract 04-evaluation-spec.md] [--ledger runs.jsonl] [--traces traces.jsonl] [--min-traces 100] [--json]

The gate-check answers one obligation. **This answers the slice**, which is where a behavioral
claim gets blocked — not inside a Superpowers task. Tasks finish on command output in a session;
obligations finish when the evidence lands, days later. Two clocks, joined by IDs in the manifest.

Exit codes
    0  done       every obligation verified on every required side; no open blocking checkpoint
    1  not done   an earned dimension that isn't green (red, baseline owed, stale), unaccepted,
                  unresolved, unfounded, misrouted, or a waiting obligation with no tracing
    2  awaiting    a human: an open checkpoint, a pass that needs judgment review (C4), or, at
                  release, a waiting obligation nobody has decided — or whose decision no closed
                  checkpoint backs (no-failures-observed: a C3; deferred-to-production: a C4)
    3  usage      the manifest can't be read or parsed

Manifest fields this reads (design §4):
    slice · stage · commit · contract · ledger · traces · checkpoints   (paths relative to the manifest; the CLI flags override)
    obligations[]: requirement · routing · tasks[] · accepted · blocked_by[]
      verification.tdd:  required · refs[] · state
      verification.bev:  required · dimension · last_result · evidence_state (optional: if given, it must
                         equal the gate's verdict; the slice gate derives the state from the result either way)
    unmeasured[]: requirement · gap · tracing_task · error_analysis · decision

A BEV row needs an **earned** dimension (`EVAL-D*` or `EVAL-T*`). A quality obligation still waiting
for failure data is not slice work: it goes on `unmeasured[]`, and the only thing the build owes it is
tracing. It never blocks a build slice. At release each entry needs a signed decision.
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
import gate_check  # noqa: E402

EXIT_DONE, EXIT_NOT_DONE, EXIT_AWAITING, EXIT_USAGE = 0, 1, 2, 3

GREEN_BEV = {"green", "green-provisional"}
CLOSED_STATUSES = {"done", "declined"}   # any other checkpoint status is open
# route -> (tdd.required, bev.required). Short forms and the requirements classifier's routes.
ROUTES = {"tdd": (True, False), "tdd_only": (True, False), "bev": (False, True), "bev_only": (False, True),
          "both": (True, True), "tdd_and_bev": (True, True),
          "manual_governance": (False, False), "measurement_only": (False, False)}
EARNED_DIMENSION = re.compile(r"^EVAL-[DT]\d+$")
DECISIONS = {"no-failures-observed", "deferred-to-production", "promoted"}
RELEASE_STAGES = {"release", "production"}


@dataclass
class Finding:
    code: str
    severity: str  # not-done | awaiting
    requirement: str
    message: str


@dataclass
class SliceVerdict:
    exit_code: int
    slice: str | None = None
    stage: str | None = None
    findings: list[Finding] = field(default_factory=list)
    obligations: list[dict] = field(default_factory=list)
    unmeasured: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _load(path: Path) -> Any:
    import yaml

    return yaml.safe_load(path.read_text())


def evaluate_slice(manifest_path: Path, checkpoints: Path | None = None, min_judge_alignment: float = 0.8,
                   min_traces: int = 100, ledger: Path | None = None, traces: Path | None = None,
                   contract: Path | None = None) -> SliceVerdict:
    m = _load(Path(manifest_path))
    if not isinstance(m, dict):
        raise ValueError("manifest must be a mapping")
    base = Path(manifest_path).parent
    stage, commit = m.get("stage"), m.get("commit")
    def resolve(p) -> Path:
        q = Path(p).expanduser()
        return q if q.is_absolute() else base / q
    ledger = ledger or (resolve(m["ledger"]) if m.get("ledger") else None)
    traces = traces or (resolve(m["traces"]) if m.get("traces") else None)
    contract = contract or (resolve(m["contract"]) if m.get("contract") else None)
    checkpoints = checkpoints or (resolve(m["checkpoints"]) if m.get("checkpoints") else None)
    thresholds = gate_check.load_contract(Path(contract)) if contract else None
    run_log = gate_check.load_ledger(Path(ledger)) if ledger else None
    trace_index = gate_check.load_trace_index(Path(traces)) if traces else None
    findings: list[Finding] = []
    rows: list[dict] = []

    cps = {}
    if checkpoints and Path(checkpoints).exists():
        for cp in _load(Path(checkpoints)) or []:
            if isinstance(cp, dict) and cp.get("id"):
                cps[cp["id"]] = cp
    reviewed = {cp.get("obligation") for cp in cps.values()
                if cp.get("type") == "C4" and cp.get("status") == "done" and str(cp.get("closed_by") or "").strip()}

    obligations = m.get("obligations") or []
    if not obligations:
        findings.append(Finding("S-EMPTY", "not-done", "—", "the manifest lists no obligations: nothing has been classified yet"))

    # Behavioral evidence is only checkable against a commit, a run ledger and a trace export.
    if any(isinstance(ob, dict) and ((ob.get("verification") or {}).get("bev") or {}).get("required") for ob in obligations):
        for missing, code, msg in ((not commit, "S-NO-COMMIT", "the slice has no `commit`: evidence can't be pinned to a code state"),
                                   (run_log is None, "S-NO-LEDGER", "no run ledger: omitted held-out runs and the baseline can't be checked"),
                                   (trace_index is None, "S-NO-TRACES", "no trace export: claimed runs can't be checked against the trace store"),
                                   (thresholds is None, "S-NO-CONTRACT", "no 04 contract: thresholds would come from the results themselves")):
            if missing:
                findings.append(Finding(code, "not-done", "—", msg))
    cited: dict[Path, str] = {}

    for ob in obligations:
        req = (ob or {}).get("requirement", "—")
        row = {"requirement": req, "routing": (ob or {}).get("routing"), "tasks": (ob or {}).get("tasks", []), "status": "done"}
        add = lambda code, sev, msg: (findings.append(Finding(code, sev, req, msg)),  # noqa: E731
                                      row.__setitem__("status", "not-done" if sev == "not-done" else ("awaiting" if row["status"] == "done" else row["status"])))

        if not isinstance(ob, dict) or "routing" not in ob or "verification" not in ob:
            add("S-MALFORMED", "not-done", "missing `routing` or `verification`: not implementation-ready")
            rows.append(row)
            continue
        tdd = ob["verification"].get("tdd") or {}
        bev = ob["verification"].get("bev") or {}
        route = str(ob["routing"]).lower()
        if route == "unresolved":
            add("S-UNRESOLVED", "not-done", "routing is UNRESOLVED: the specs do not decide how this is verified")
        elif route not in ROUTES:
            add("S-ROUTING-MISMATCH", "not-done", f"unknown routing {ob['routing']!r}: use one of {sorted(ROUTES)} or UNRESOLVED")
        elif ROUTES[route] != (bool(tdd.get("required")), bool(bev.get("required"))):
            want = ROUTES[route]
            add("S-ROUTING-MISMATCH", "not-done", f"routing {ob['routing']!r} requires tdd={want[0]}, bev={want[1]}; the row says "
                f"tdd={bool(tdd.get('required'))}, bev={bool(bev.get('required'))}")
        if ob.get("accepted") is not True:
            add("S-NOT-ACCEPTED", "not-done", "the DERIVE rows have not been accepted by a human (checkpoint C1)")

        if tdd.get("required") and tdd.get("state") != "green":
            add("S-TDD-NOT-GREEN", "not-done", f"TDD state is {tdd.get('state')!r}; refs {tdd.get('refs') or []}")

        row["dimension"] = bev.get("dimension")
        row["evidence_state"] = bev.get("evidence_state")   # replaced by the gate's verdict when a result is evaluated
        if bev.get("required"):
            claimed = bev.get("evidence_state")
            result_path = bev.get("last_result")
            if not EARNED_DIMENSION.match(str(bev.get("dimension") or "")):
                add("S-BEV-NO-DIMENSION", "not-done", f"dimension is {bev.get('dimension')!r}: a BEV row needs an earned "
                    "EVAL-D/EVAL-T id; an obligation still waiting for failure data goes on `unmeasured[]`")
            elif not result_path:
                if claimed in GREEN_BEV:
                    add("S-NO-EVIDENCE", "not-done", f"{claimed} with no result file: an unfounded claim")
                else:
                    add("S-BEV-NOT-GREEN", "not-done", f"evidence state is {claimed or 'unmeasured'!r} for {bev.get('dimension')}: no result yet")
            else:
                p = Path(result_path)
                p = p if p.is_absolute() else base / p
                if not p.exists():
                    add("S-NO-EVIDENCE", "not-done", f"result file not found: {result_path}")
                else:
                    doc = _load(p)
                    key = p.resolve()
                    if key in cited:
                        add("S-RESULT-MISMATCH", "not-done", f"{result_path} is already the evidence for {cited[key]}: one result, one obligation")
                    cited.setdefault(key, req)
                    if isinstance(doc, dict):
                        wrong = [f"{k} is {doc.get(k)!r}, the row needs {want!r}"
                                 for k, want in (("obligation", req), ("dimension", bev.get("dimension")), ("stage", stage))
                                 if doc.get(k) != want]
                        if wrong:
                            add("S-RESULT-MISMATCH", "not-done", f"{result_path} is not this row's evidence: " + "; ".join(wrong))
                    try:
                        v = gate_check.evaluate(doc, min_judge_alignment, run_log, trace_index, thresholds)
                    except Exception as e:  # never let a malformed result read as a manifest error, or as a pass
                        add("S-GATE-ERROR", "not-done", f"the gate-check could not evaluate {result_path}: {type(e).__name__}: {e}")
                        v = None
                    if v is not None:
                        row["gate_exit"] = v.exit_code
                        derived = None if v.evidence_state_after == "unchanged" else v.evidence_state_after
                        row["evidence_state"] = derived or "invalid evidence"
                        if claimed is not None and derived is not None and claimed != derived:
                            add("S-STATE-MISMATCH", "not-done", f"the manifest says {claimed!r}, the gate says {derived!r}: "
                                "drop the field or copy the gate's verdict, never a claim")
                        if any(f.code == "W-SPANS-UNCHECKED" for f in v.findings):
                            add("S-SPANS-UNCHECKED", "not-done", "cases cite spans the trace export doesn't list: export span IDs")
                        if v.exit_code != gate_check.EXIT_PASS:
                            add("S-GATE-FAILED", "not-done", f"the gate-check rejects {result_path} ({row['evidence_state']}): "
                                + "; ".join(f.code for f in v.findings if f.severity in ("fail", "inconclusive")))
                        else:
                            result_commit = ((doc.get("versions") or {}).get("commit")) if isinstance(doc, dict) else None
                            if commit and result_commit != commit:
                                add("S-STALE", "not-done", f"evidence is pinned to commit {result_commit!r}, the slice is at {commit}: re-run it")
                                row["evidence_state"] = "stale"
                            if v.requires_human_review and req not in reviewed:
                                add("S-AWAITING-REVIEW", "awaiting", "judgment review required (" + "; ".join(v.review_reasons) + f"): a reviewer closes a C4 for {req} (`checkpoints.py close --by <name> --status done`)")

        for cp_id in ob.get("blocked_by") or []:
            cp = cps.get(cp_id)
            if cp is None:
                add("S-CHECKPOINT-MISSING", "not-done", f"blocked_by {cp_id}, which is not in the checkpoint queue")
            elif cp.get("status") not in CLOSED_STATUSES:
                add("S-CHECKPOINT-OPEN", "awaiting", f"{cp_id} ({cp.get('type')}) is open: {cp.get('needed') or 'human input needed'}")
        rows.append(row)

    bev_rows = {r["requirement"]: r.get("dimension") for r, ob in zip(rows, obligations)
                if isinstance(ob, dict) and ((ob.get("verification") or {}).get("bev") or {}).get("required")}
    waiting = _check_unmeasured(m.get("unmeasured") or [], bev_rows, stage, min_traces, findings, cps)

    if any(f.severity == "not-done" for f in findings):
        code = EXIT_NOT_DONE
    elif findings:
        code = EXIT_AWAITING
    else:
        code = EXIT_DONE
    return SliceVerdict(code, m.get("slice"), stage, findings, rows, waiting)


def _check_unmeasured(entries: list, bev_rows: dict, stage: str | None, min_traces: int, findings: list[Finding],
                      cps: dict | None = None) -> list[dict]:
    """Obligations waiting for failure data. Outside the build slice's done; decided before release."""
    out = []
    for u in entries:
        req = (u or {}).get("requirement") if isinstance(u, dict) else None
        add = lambda code, sev, msg: findings.append(Finding(code, sev, req or "—", msg))  # noqa: E731
        if not req:
            add("S-MALFORMED", "not-done", "an `unmeasured[]` entry has no requirement")
            continue
        d = u.get("decision") or {}
        outcome = d.get("outcome") if isinstance(d, dict) else None
        out.append({"requirement": req, "gap": u.get("gap"), "tracing_task": u.get("tracing_task"),
                    "trigger": (u.get("error_analysis") or {}).get("trigger"), "decision": outcome})

        if not u.get("tracing_task"):
            add("S-UNTRACED", "not-done", "no tracing task: without traces the failure can't be seen and the evaluator can't be earned")
        if d and outcome not in DECISIONS:
            add("S-MALFORMED", "not-done", f"decision outcome {outcome!r} is not one of {sorted(DECISIONS)}")
            continue

        if outcome == "promoted":
            if bev_rows.get(req) != d.get("dimension"):
                add("S-PROMOTED-NOT-ROUTED", "not-done", f"promoted to {d.get('dimension')!r} but no BEV row carries it: add the obligation row")
            continue
        if req in bev_rows:
            add("S-DOUBLE-ROUTED", "not-done", "listed as waiting and routed to BEV: decide which (a promotion records `decision.outcome: promoted`)")
            continue

        if stage not in RELEASE_STAGES:
            continue
        if not outcome:
            add("S-UNMEASURED-AT-RELEASE", "awaiting", f"{u.get('gap') or 'no GAP'} still waiting: record no-failures-observed, "
                "deferred-to-production, or promote it")
        elif outcome == "no-failures-observed":
            n = d.get("traces_reviewed") or 0
            if not d.get("reviewer"):
                add("S-DECISION-UNSIGNED", "awaiting", "no-failures-observed needs a reviewer")
            if n < min_traces:
                bound = f"{3 / n:.2f}" if n else "unbounded"
                add("S-THIN-REVIEW", "awaiting", f"0 failures in {n} traces bounds the failure rate only below {bound} "
                    f"(rule of three); {min_traces} are expected, or a human accepts the bound")
            if d.get("reviewer"):
                _check_backing(req, d, "reviewer", "C3", d.get("checkpoint") or (u.get("error_analysis") or {}).get("checkpoint"), cps or {}, add)
        elif outcome == "deferred-to-production":
            if not d.get("approver"):
                add("S-DECISION-UNSIGNED", "awaiting", "deferred-to-production needs an approver")
            else:
                _check_backing(req, d, "approver", "C4", d.get("checkpoint"), cps or {}, add)
    return out


def _check_backing(req: str, d: dict, role: str, cp_type: str, cp_id, cps: dict, add) -> None:
    """A release decision names a person; the checkpoint queue, which only a person can close, must back it.

    The manifest is agent-writable, so `reviewer: Jim` there proves nothing on its own. The decision counts only
    if it cites a checkpoint of the right type, for this obligation, closed `done` by that same person."""
    how = f"`checkpoints.py open --type {cp_type} --obligation {req}`, closed by {d.get(role)} with `close --by`"
    if not cp_id:
        add("S-DECISION-UNBACKED", "awaiting", f"the {role} is named in the manifest only: record `decision.checkpoint` ({how})")
        return
    cp = cps.get(cp_id)
    if cp is None:
        add("S-CHECKPOINT-MISSING", "not-done", f"decision cites {cp_id}, which is not in the checkpoint queue")
    elif cp.get("type") != cp_type or cp.get("obligation") != req:
        add("S-DECISION-UNBACKED", "not-done", f"{cp_id} is a {cp.get('type')} for {cp.get('obligation')}; this decision needs a {cp_type} for {req}")
    elif cp.get("status") not in CLOSED_STATUSES:
        add("S-CHECKPOINT-OPEN", "awaiting", f"{cp_id} ({cp_type}) is still open: the decision isn't made until {d.get(role)} closes it")
    elif cp.get("status") != "done":
        add("S-DECISION-UNBACKED", "not-done", f"{cp_id} was closed `{cp.get('status')}`: the decision was declined, not made")
    elif not str(cp.get("closed_by") or "").strip():
        add("S-DECISION-UNBACKED", "not-done", f"{cp_id} has no `closed_by`: only `checkpoints.py close --by` records who decided")
    elif str(cp["closed_by"]).strip().casefold() != str(d.get(role)).strip().casefold():
        add("S-DECISION-UNBACKED", "not-done", f"the manifest names {d.get(role)!r} as {role}, but {cp_id} was closed by {cp['closed_by']!r}")


def render(v: SliceVerdict) -> str:
    label = {EXIT_DONE: "SLICE DONE", EXIT_NOT_DONE: "NOT DONE", EXIT_AWAITING: "AWAITING A HUMAN"}[v.exit_code]
    lines = [f"{label}  {v.slice or '?'} ({v.stage or '?'})  —  {len(v.obligations)} obligations  (exit {v.exit_code})"]
    for r in v.obligations:
        mark = {"done": "ok  ", "awaiting": "wait", "not-done": "BLOCK"}[r["status"]]
        lines.append(f"  [{mark}] {r['requirement']:<10} routing={r.get('routing')}  bev={r.get('evidence_state') or '—'}  tasks={','.join(r.get('tasks') or []) or '—'}")
    for u in v.unmeasured:
        lines.append(f"  [open] {u['requirement']:<10} unmeasured  {u.get('gap') or '—'}  tracing={u.get('tracing_task') or '—'}"
                     f"  trigger={u.get('trigger') or '—'}  decision={u.get('decision') or '—'}")
    lines += [f"  [{f.severity}] {f.code} {f.requirement}: {f.message}" for f in v.findings]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="BEV slice gate (see docs/design.md §10.10)")
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--checkpoints", type=Path, default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--min-judge-alignment", type=float, default=0.8)
    ap.add_argument("--min-traces", type=int, default=100, help="traces a no-failures-observed decision must cover at release")
    ap.add_argument("--ledger", type=Path, help="run ledger (JSON lines); overrides the manifest's `ledger`")
    ap.add_argument("--traces", type=Path, help="trace-store export; overrides the manifest's `traces`")
    ap.add_argument("--contract", type=Path, help="the 04 eval spec (thresholds, §4.2); overrides the manifest's `contract`")
    args = ap.parse_args(argv)
    try:
        v = evaluate_slice(args.manifest, args.checkpoints, args.min_judge_alignment, args.min_traces, args.ledger, args.traces, args.contract)
    except Exception as e:
        print(f"NOT GATED  cannot read {args.manifest}: {e}", file=sys.stderr)
        return EXIT_USAGE
    print(json.dumps(v.to_dict(), indent=2) if args.json else render(v))
    return v.exit_code


if __name__ == "__main__":
    sys.exit(main())
