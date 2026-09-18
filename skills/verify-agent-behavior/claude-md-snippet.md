# CLAUDE.md snippet — for a project using Superpowers + BEV (+ evals-skills)

Copy into the consuming project's `CLAUDE.md`. Superpowers' `using-superpowers` gives user
instructions precedence over skills, so these lines resolve the known conflicts
(`docs/design.md` §10.6 in the plugin) without forking anything.

```markdown
## Verification routing (BEV)

- BEV owns the behavioral loop and the completion gate. `evals:*` skills are measurement
  instruments called at the BEV step that needs them (see the BEV plugin's `instruments.md`).
  Never invoke `evals:evals-start` once 04 dimensions exist.
- After brainstorming, build the verification manifest from the skill's `templates/verification-manifest.yaml`
  (a human accepts it: C1); then `writing-plans`, with a task for each tracing requirement.
- Deterministic obligations and controls go through TDD and subagent-driven-development.
  BEV human checkpoints (C1–C5) are opened with the skill's `tools/checkpoints.py open`, outside
  SDD — keep working on unblocked tasks; do not stop the whole plan. **Never close a checkpoint:**
  a named human does, in their own terminal.
- The evidence (ledger, records, traces, checkpoint queue) lives in the directories named in
  `.claude/bev.json`. Don't write there; the harness and the plugin's tools do. The files it lists as
  `protected_files` (the eval spec's thresholds, judge prompts, held-out cases) are read-only for you:
  propose a change as a 04 change request for a human to accept (C5).
- The BEV tools are in the `behavior-evidence:verify-agent-behavior` skill's `tools/` directory; run them with
  `uv run <that skill's base directory>/tools/<tool>.py`.
- A BEV obligation is complete only when `gate_check.py` exits 0 **and** `requires_human_review`
  is false or a C4 checkpoint for that obligation reads `status: done`. Until then the task is `awaiting-judgment-review`.
- A Superpowers task is done when its commands pass; that claims nothing about behavior. **The slice
  is done when `slice_gate.py` exits 0.** Run it in `finishing-a-development-branch`, before any merge.
- A quality dimension with no observed failure is not slice work. List it on the manifest's
  `unmeasured[]` with its GAP and a tracing task; it never blocks the build slice. Build an evaluator
  only for failures seen in traces, or for crystal-clear red lines and controls. A failure found
  mid-build is promoted through a `04` change request (C5) and only then becomes a BEV row.
```
