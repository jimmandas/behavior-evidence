# run-experiment

One hypothesis. One change. Same cases.

---

## Choose one hypothesis

From `analyze-failures.md`. **One.** If two clusters both look tractable, do the one with
the most cases or the clearest evidence — the other survives to the next cycle.

## Make the smallest change that tests it

**The change is not the fix. It is the test of the hypothesis.**

If the hypothesis is *"the prompt prioritises first-found evidence"*, change the ordering
instruction. Do not also rewrite the examples, adjust `top_k`, and swap the judge.

**If the change is deterministic — a schema, a validator, a control — hand it to
Superpowers TDD.** BEV states the behavioral outcome required; the implementation belongs
to the engine that owns dispatch, review and testing.

State what must **not** regress:

```
preserve:
  - existing citation behavior
  - ambiguity handling
  - the human escalation boundary
```

A fix that quietly degrades a neighbouring behavior is a regression **this dimension's
delta will not show**.

## Rerun

**Same case-set version. Same method. Same judge and judge-prompt version.**

If any of those changed, this is a new series, not a comparison. Record the discontinuity
and re-baseline deliberately.

**Rerun on the dev split only.** The held-out split is for `verify-before-completion`.
**Once you've read a held-out failure to decide what to change, that case is dev**, and the
held-out set needs replacing before it can verify anything.

## Compare

```
EVAL-D03 conflict recognition
baseline:   71%  (noise floor ±2pp)
candidate:  91%
delta:      +20pp                    → improved
critical misses:  4 → 1
regressions: 2 previously-passing near-miss cases now flagged incorrectly
```

**Four results, and the fourth is the honest one:**

| | |
|---|---|
| `improved` | delta exceeds the noise floor, no unacceptable regression |
| `unchanged` | delta is zero or trivially small, and the noise floor is tight enough to say so |
| `regressed` | delta is negative beyond the floor, **or a previously-passing case now fails** |
| **`inconclusive`** | the delta is inside the noise floor |

**`inconclusive` is not `unchanged`.** It means *not yet known*, and it resolves by
running more cases or making a larger change — **never by declaring completion.**

## Check regressions explicitly

Re-run previously-passing cases. A dimension can improve in aggregate while breaking
cases that used to work — the near-miss bucket is where this shows first.

## Then

- `improved` and threshold met on dev → `verify-before-completion.md`, which runs the held-out split. **Dev success is not green.**
- `regressed` or `unchanged` → back to `analyze-failures.md` with what you learned. Evidence state: `red`
- `inconclusive` → more cases, or a bigger change. Not a third option. Evidence state: `inconclusive`
