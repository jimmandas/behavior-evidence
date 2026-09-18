#!/usr/bin/env python3
"""PreToolUse hook: the coding agent may not rewrite the evidence it is judged on.

Dormant unless the project has `.claude/bev.json`:

    {"evidence_dirs": ["~/bev-evidence/tvr"],
     "protected_files": ["specs/04-evaluation-spec.md", "evals/judges/", "evals/cases/held-out/"]}

`evidence_dirs` hold what the harness writes (run log, records, traces, checkpoint queue).
`protected_files` are human-owned inputs the gate trusts — the eval spec with its thresholds, judge
prompts, held-out cases — files or directories, relative to the project root. The agent reads them
(the Read tool is not intercepted) but doesn't change them; a change goes through a human (checkpoint C5).

Then, inside the agent's session:
  - Write / Edit / MultiEdit / NotebookEdit into an evidence directory or a protected file, or to
    `.claude/bev.json`, is denied.
  - A Bash command that touches any of them is denied, unless it is a
    single, uncomposed call of one of the plugin's tools in a mode that is allowed from the session:
    gate_check.py · slice_gate.py · judge_to_eval_result.py · export_traces.py ·
    bev_harness.py judge-run · checkpoints.py open|list.
    `checkpoints.py close` is denied: a human closes checkpoints, outside the session.

What it does not stop: a program the agent writes elsewhere and runs, which opens the evidence
files itself. The hook makes tampering deliberate rather than casual; custody that holds against
a determined agent needs the evidence written somewhere the session can't reach (CI).

Stdlib only. Exit 0 allows; exit 2 blocks, and stderr goes back to the agent.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path

CONFIG = Path(".claude") / "bev.json"
FILE_TOOLS = {"Write": "file_path", "Edit": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path"}
ALLOWED = {
    "gate_check.py": None,
    "slice_gate.py": None,
    "judge_to_eval_result.py": None,
    "export_traces.py": None,
    "bev_harness.py": {"judge-run"},
    "checkpoints.py": {"open", "list"},
}
COMPOSITION = re.compile(r"[;&|<>`]|\$\(")


def find_config(cwd: Path) -> Path | None:
    for d in [cwd, *cwd.parents]:
        if (d / CONFIG).is_file():
            return d / CONFIG
    return None


def resolve(p: str, cwd: Path) -> Path:
    q = Path(os.path.expanduser(os.path.expandvars(p)))
    return (q if q.is_absolute() else cwd / q).resolve()


def inside(p: Path, roots: list[Path]) -> bool:
    return any(p == r or r in p.parents for r in roots)


def block(reason: str) -> int:
    print(f"behavior-evidence: {reason}", file=sys.stderr)
    return 2


def check_bash(command: str, cwd: Path, roots: list[Path], config: Path, spellings: tuple[str, ...] = ()) -> int:
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        tokens = command.split()
    home = os.path.expanduser("~")
    literal = [str(r) for r in roots] + ["~" + str(r)[len(home):] for r in roots if str(r).startswith(home)]
    literal += [s for s in spellings if s and s not in (".", "..")]
    # whole path components only: "evals/judges" matches "evals/judges/x.md", not "evals/judges_test.py"
    touches = any(re.search(re.escape(s) + r"(?![\w.-])", command) for s in literal) or "bev.json" in command
    for t in tokens:
        for part in t.split("="):
            if "/" in part or part.startswith("."):
                try:
                    if inside(resolve(part, cwd), roots) or resolve(part, cwd) == config.resolve():
                        touches = True
                except (OSError, RuntimeError):
                    continue
    if not touches:
        return 0
    if COMPOSITION.search(command):
        return block("this command touches evidence or a protected spec file and chains, pipes or redirects; "
                     "run one plugin tool on its own (see RUNBOOK §2)")
    script = next((Path(t).name for t in tokens if Path(t).name in ALLOWED), None)
    if script is None:
        return block("evidence and protected spec files are written by the harness and by humans, not from the agent's "
                     "session. Read them with the Read tool or the plugin's tools (gate_check.py, slice_gate.py, "
                     "checkpoints.py list); propose a spec change for a human to accept (C5)")
    modes = ALLOWED[script]
    if modes is not None:
        after = tokens[[Path(t).name for t in tokens].index(script) + 1:]
        mode = next((t for t in after if not t.startswith("-")), None)
        if mode not in modes:
            if script == "checkpoints.py" and mode == "close":
                return block("closing a checkpoint is a human act: the reviewer runs `checkpoints.py close --by <name>` "
                             "in their own terminal. Leave it open and continue with unblocked work")
            return block(f"{script} {mode or ''} isn't allowed from the session on the evidence directory")
    return 0


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    cwd = Path(event.get("cwd") or os.getcwd())
    config = find_config(cwd)
    if config is None:
        return 0
    try:
        cfg = json.loads(config.read_text())
        dirs = cfg.get("evidence_dirs") or []
        files = cfg.get("protected_files") or []
    except (OSError, json.JSONDecodeError, AttributeError):
        return block(f"{config} is unreadable: fix it before touching evidence")
    project = config.parent.parent
    evidence = [resolve(d, project) for d in dirs]
    protected = [resolve(f, project) for f in files]
    roots = evidence + protected
    tool, args = event.get("tool_name"), event.get("tool_input") or {}

    if tool in FILE_TOOLS:
        target = args.get(FILE_TOOLS[tool])
        if not target:
            return 0
        p = resolve(target, cwd)
        if p == config.resolve():
            return block(".claude/bev.json sets what the agent may not touch; a human edits it")
        if inside(p, evidence):
            return block(f"{p} is evidence (the run ledger, records, traces or checkpoint queue). "
                         "The harness and humans write it; the agent doesn't")
        if inside(p, protected):
            return block(f"{p} is a protected spec file (thresholds, judge prompts or held-out cases — what the gate "
                         "trusts). A human changes it: propose the change as a 04 change request (checkpoint C5)")
        return 0
    if tool == "Bash":
        # also match each path as configured and as seen from the working directory, wherever it appears
        # in the command (quoted inside a `python -c`, say)
        spellings = tuple(str(x).rstrip("/") for x in [*dirs, *files]) + tuple(
            os.path.relpath(r, cwd) for r in roots)
        return check_bash(str(args.get("command") or ""), cwd, roots, config, spellings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
