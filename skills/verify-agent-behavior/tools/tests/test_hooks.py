"""The custody hook: the agent can't rewrite the evidence it is judged on."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[4] / "hooks" / "protect_evidence.py"
HOOKS_JSON = HOOK.parent / "hooks.json"


@pytest.fixture
def project(tmp_path):
    proj, evidence = tmp_path / "proj", tmp_path / "evidence" / "tvr"
    (proj / ".claude").mkdir(parents=True)
    evidence.mkdir(parents=True)
    (proj / ".claude" / "bev.json").write_text(json.dumps({"evidence_dirs": [str(evidence)]}))
    return proj, evidence


def hook(cwd, tool, **tool_input):
    event = {"session_id": "s", "cwd": str(cwd), "hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input}
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(event), capture_output=True, text=True)


def allowed(p):
    return p.returncode == 0


def blocked(p):
    return p.returncode == 2 and "behavior-evidence" in p.stderr


def test_dormant_without_config(tmp_path):
    assert allowed(hook(tmp_path, "Write", file_path=str(tmp_path / "anything")))
    assert allowed(hook(tmp_path, "Bash", command="rm -rf /tmp/x"))


@pytest.mark.parametrize("tool,key", [("Write", "file_path"), ("Edit", "file_path"), ("MultiEdit", "file_path"),
                                      ("NotebookEdit", "notebook_path")])
def test_file_tools_cannot_write_evidence(project, tool, key):
    proj, ev = project
    assert blocked(hook(proj, tool, **{key: str(ev / "runs.jsonl")}))
    assert blocked(hook(proj, tool, **{key: str(ev / "records" / "run-1.json")}))


def test_file_tools_may_write_the_project(project):
    proj, _ = project
    assert allowed(hook(proj, "Write", file_path=str(proj / "src" / "agent.py")))
    assert allowed(hook(proj, "Edit", file_path="verification-manifest.yaml"))


def test_relative_paths_into_evidence_are_caught(project):
    proj, _ = project
    assert blocked(hook(proj, "Write", file_path="../evidence/tvr/runs.jsonl"))


def test_the_config_itself_is_protected(project):
    proj, _ = project
    assert blocked(hook(proj, "Edit", file_path=str(proj / ".claude" / "bev.json")))
    assert blocked(hook(proj / "sub" if (proj / "sub").mkdir() is None else proj, "Bash", command="cat /dev/null > ../.claude/bev.json"))
    assert blocked(hook(proj, "Bash", command="python3 -c 'open(\".claude/bev.json\",\"w\")'"))


@pytest.mark.parametrize("command", [
    "echo '{{}}' >> {ev}/runs.jsonl",
    "sed -i '' 's/held-out/dev/' {ev}/runs.jsonl",
    "rm {ev}/runs.jsonl",
    "cp /tmp/forged.jsonl {ev}/runs.jsonl",
    "cd {ev} && truncate -s 0 runs.jsonl",
    "uv run tools/gate_check.py r.yaml --ledger {ev}/runs.jsonl; rm {ev}/runs.jsonl",
    "python3 tools/checkpoints.py close --queue {ev}/checkpoints.yaml --id CP-0001 --by me --status done --decision ok",
    "python3 tools/bev_harness.py --workdir {ev}",
])
def test_bash_cannot_touch_evidence(project, command):
    proj, ev = project
    assert blocked(hook(proj, "Bash", command=command.format(ev=ev)))


@pytest.mark.parametrize("command", [
    "uv run /x/tools/gate_check.py r.yaml --ledger {ev}/runs.jsonl --traces {ev}/traces.jsonl",
    "uv run /x/tools/slice_gate.py manifest.yaml --checkpoints {ev}/checkpoints.yaml",
    "uv run /x/tools/export_traces.py spans.json --out {ev}/traces.jsonl",
    "uv run /x/tools/judge_to_eval_result.py {ev}/judge-run.yaml --template t.yaml --out results/r.yaml",
    "uv run /x/tools/bev_harness.py judge-run --workdir {ev} --runs a --baseline b --out {ev}/judge-run.yaml",
    "uv run /x/tools/checkpoints.py open --queue {ev}/checkpoints.yaml --type C3 --obligation ABS-B05 --needed 'review 100 traces'",
    "uv run /x/tools/checkpoints.py list --queue {ev}/checkpoints.yaml --open",
])
def test_plugin_tools_may_read_and_append(project, command):
    proj, ev = project
    assert allowed(hook(proj, "Bash", command=command.format(ev=ev)))


def test_close_is_explained(project):
    proj, ev = project
    p = hook(proj, "Bash", command=f"uv run t/checkpoints.py close --queue {ev}/q.yaml --id CP-1 --by x --status done --decision y")
    assert blocked(p) and "human" in p.stderr


def test_bash_elsewhere_is_untouched(project):
    proj, _ = project
    assert allowed(hook(proj, "Bash", command="pytest -q && git status"))


def test_tilde_paths_are_caught(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "bev-evidence").mkdir(parents=True)
    proj = tmp_path / "proj"
    (proj / ".claude").mkdir(parents=True)
    (proj / ".claude" / "bev.json").write_text(json.dumps({"evidence_dirs": ["~/bev-evidence"]}))
    event = {"cwd": str(proj), "tool_name": "Bash", "tool_input": {"command": "echo x >> ~/bev-evidence/runs.jsonl"}}
    p = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(event), capture_output=True, text=True,
                       env={"HOME": str(home), "PATH": "/usr/bin:/bin"})
    assert blocked(p)


def test_unreadable_config_blocks(project):
    proj, ev = project
    (proj / ".claude" / "bev.json").write_text("{not json")
    assert blocked(hook(proj, "Write", file_path=str(proj / "x.py")))


def test_garbage_input_is_allowed_through():
    p = subprocess.run([sys.executable, str(HOOK)], input="not json", capture_output=True, text=True)
    assert p.returncode == 0


def test_hooks_json_wires_the_script():
    cfg = json.loads(HOOKS_JSON.read_text())
    entry = cfg["hooks"]["PreToolUse"][0]
    assert set(entry["matcher"].split("|")) == {"Write", "Edit", "MultiEdit", "NotebookEdit", "Bash"}
    assert "${CLAUDE_PLUGIN_ROOT}/hooks/protect_evidence.py" in entry["hooks"][0]["command"]


def test_bash_relative_paths_into_evidence_are_caught(project):
    proj, _ = project
    assert blocked(hook(proj, "Bash", command="rm ../evidence/tvr/runs.jsonl"))
    assert blocked(hook(proj, "Bash", command="python3 fix.py --ledger=../evidence/tvr/runs.jsonl"))


# ---------- protected spec files: what the gate trusts, owned by humans ----------

@pytest.fixture
def guarded(tmp_path):
    proj, evidence = tmp_path / "proj", tmp_path / "evidence"
    (proj / ".claude").mkdir(parents=True)
    (proj / "specs").mkdir()
    (proj / "evals" / "judges").mkdir(parents=True)
    evidence.mkdir()
    spec = proj / "specs" / "04-evaluation-spec.md"
    spec.write_text("| `EVAL-D01` | build | ≥ 0.90 | model |\n")
    (proj / ".claude" / "bev.json").write_text(json.dumps(
        {"evidence_dirs": [str(evidence)], "protected_files": ["specs/04-evaluation-spec.md", "evals/judges/"]}))
    return proj, spec


@pytest.mark.parametrize("tool,key", [("Write", "file_path"), ("Edit", "file_path"), ("MultiEdit", "file_path")])
def test_the_threshold_file_cannot_be_edited(guarded, tool, key):
    proj, spec = guarded
    p = hook(proj, tool, **{key: str(spec)})
    assert blocked(p) and "protected spec file" in p.stderr
    assert blocked(hook(proj, tool, **{key: "specs/04-evaluation-spec.md"}))


def test_a_protected_directory_covers_its_files(guarded):
    proj, _ = guarded
    assert blocked(hook(proj, "Write", file_path=str(proj / "evals" / "judges" / "escalation.md")))


@pytest.mark.parametrize("command", [
    "sed -i '' 's/0.90/0.85/' specs/04-evaluation-spec.md",
    "python3 -c \"open('specs/04-evaluation-spec.md','w')\"",
    "echo x > evals/judges/escalation.md",
])
def test_shell_cannot_edit_protected_files(guarded, command):
    proj, _ = guarded
    assert blocked(hook(proj, "Bash", command=command))


def test_the_gate_may_read_the_spec(guarded):
    proj, spec = guarded
    assert allowed(hook(proj, "Bash", command=f"uv run /x/tools/gate_check.py r.yaml --contract {spec}"))


def test_other_spec_files_stay_writable(guarded):
    proj, _ = guarded
    assert allowed(hook(proj, "Write", file_path=str(proj / "specs" / "02-agent-behavior-spec.md")))


def test_a_config_without_protected_files_still_works(project):
    proj, ev = project
    assert allowed(hook(proj, "Write", file_path=str(proj / "specs" / "04-evaluation-spec.md")))


def test_similar_names_are_not_caught(guarded):
    proj, _ = guarded
    assert allowed(hook(proj, "Bash", command="pytest evals/judges_test.py specs/04-evaluation-spec.md.bak"))
