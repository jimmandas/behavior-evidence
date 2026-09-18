"""The statistics behind a behavioral claim, computed from per-case records.

Shared by the judge adapter (which writes a result) and the gate-check (which re-derives it).
One implementation, so a result the adapter wrote reproduces exactly under the gate, and a
number anyone typed does not.

Stdlib only. Deterministic: the bootstrap uses a fixed seed and a fixed draw count that the
result file cannot change.

  - judge TPR / TNR from labelled items (human vs. judge, 1 = Pass)
  - per-run pass rate, corrected for the judge's errors (Rogan–Gladen) when model-scored
  - score (mean corrected rate) and noise floor (half the run spread)
  - a 95% percentile bootstrap interval that resamples the cases and, when model-scored,
    the judge's labels, so judge uncertainty widens it
  - regressions against baseline records, and unacceptable failures
"""

from __future__ import annotations

import random
from functools import lru_cache

MIN_INFORMATIVENESS = 0.05  # TPR + TNR - 1 below this: the judge is no better than chance
BOOTSTRAP = 2000
SEED = 7
MIN_VALID_RESAMPLES = 100


class StatsError(ValueError):
    pass


def label_pairs(items: list) -> tuple[tuple[int, int], ...]:
    """(human, judge) per labelled item, in the order given. Items are keyed by item_id."""
    if not isinstance(items, list) or not items:
        raise StatsError("judge_validation.items must list labelled items (item_id, human, judge)")
    ids = [i.get("item_id") if isinstance(i, dict) else None for i in items]
    if not all(ids) or len(set(ids)) != len(ids):
        raise StatsError("every judge_validation item needs a unique item_id")
    if any(i.get("human") not in (0, 1) or i.get("judge") not in (0, 1)
           or isinstance(i.get("human"), float) or isinstance(i.get("judge"), float) for i in items):
        raise StatsError("judge_validation human and judge verdicts must be 0 or 1")
    return tuple((int(i["human"]), int(i["judge"])) for i in items)


def alignment(pairs: tuple[tuple[int, int], ...]) -> tuple[float, float]:
    pos = [j for h, j in pairs if h == 1]
    neg = [j for h, j in pairs if h == 0]
    if not pos or not neg:
        raise StatsError("judge labels must contain both human Pass and Fail items")
    return sum(pos) / len(pos), sum(1 - j for j in neg) / len(neg)


def corrected_rate(p_obs: float, tpr: float, tnr: float) -> float:
    informativeness = tpr + tnr - 1
    if informativeness < MIN_INFORMATIVENESS:
        raise StatsError(f"judge is no better than chance (TPR + TNR - 1 = {informativeness:.3f}); correction undefined")
    return min(1.0, max(0.0, (p_obs + tnr - 1) / informativeness))


def aligned(runs: list, what: str = "runs") -> tuple[tuple[str, ...], tuple[tuple[int, ...], ...]]:
    """Case IDs (sorted) and verdict rows (one per run), aligned on test_case_id. Validates the records."""
    if not isinstance(runs, list) or not runs:
        raise StatsError(f"no {what} records")
    run_ids = [r.get("run_id") if isinstance(r, dict) else None for r in runs]
    if not all(run_ids) or len(set(run_ids)) != len(run_ids):
        raise StatsError(f"every {what} record needs a unique run_id")
    order, rows = None, []
    for r in runs:
        cases = r.get("cases")
        if not isinstance(cases, list) or not cases:
            raise StatsError(f"run {r['run_id']} has no cases")
        by_id = {}
        for c in cases:
            if not isinstance(c, dict) or not c.get("test_case_id") or not c.get("trace_id"):
                raise StatsError(f"run {r['run_id']}: every case needs test_case_id and trace_id")
            if c.get("verdict") not in (0, 1) or isinstance(c.get("verdict"), float):
                raise StatsError(f"run {r['run_id']} case {c['test_case_id']}: verdict {c.get('verdict')!r} must be 0 or 1")
            if c["test_case_id"] in by_id:
                raise StatsError(f"run {r['run_id']}: duplicate test_case_id {c['test_case_id']}")
            by_id[c["test_case_id"]] = int(c["verdict"])
        if order is None:
            order = tuple(sorted(by_id))
        elif set(by_id) != set(order):
            raise StatsError(f"run {r['run_id']} scores different cases from run {run_ids[0]}")
        rows.append(tuple(by_id[i] for i in order))
    return order, tuple(rows)


def run_rates(rows, tpr: float | None = None, tnr: float | None = None) -> list[float]:
    n = len(rows[0])
    raw = [sum(v) / n for v in rows]
    return raw if tpr is None else [corrected_rate(p, tpr, tnr) for p in raw]


@lru_cache(maxsize=256)
def summarize(rows: tuple, pairs: tuple | None = None) -> dict:
    """Score, run rates, noise floor and 95% CI. `pairs` given ⇒ model-scored (judge-corrected)."""
    tpr = tnr = None
    if pairs is not None:
        tpr, tnr = alignment(pairs)
    rates = run_rates(rows, tpr, tnr)
    score = sum(rates) / len(rates)
    noise = (max(rates) - min(rates)) / 2

    n = len(rows[0])
    per_case = [sum(col) / len(col) for col in zip(*rows)]
    rng = random.Random(SEED)
    samples = []
    for _ in range(BOOTSTRAP):
        p_obs = sum(per_case[rng.randrange(n)] for _ in range(n)) / n
        if pairs is None:
            samples.append(p_obs)
            continue
        drawn = tuple(pairs[rng.randrange(len(pairs))] for _ in range(len(pairs)))
        try:
            b_tpr, b_tnr = alignment(drawn)
            samples.append(corrected_rate(p_obs, b_tpr, b_tnr))
        except StatsError:
            continue  # a resample with one class, or an uninformative judge, carries no estimate
    if len(samples) < MIN_VALID_RESAMPLES:
        raise StatsError("too few valid bootstrap resamples; add judge labels of both classes")
    s = sorted(samples)
    lo, hi = s[int(0.025 * len(s))], s[min(len(s) - 1, int(0.975 * len(s)))]
    out = {"score": score, "runs": rates, "noise_floor": noise, "ci95": [min(lo, score), max(hi, score)], "n": n}
    if pairs is not None:
        out.update(tpr=tpr, tnr=tnr, test_n=len(pairs))
    return out


def regressions(ids: tuple, base_rows: tuple, rows: tuple) -> list[str]:
    """Cases that passed in every baseline run and now pass in fewer than half the runs."""
    out = []
    for k, case in enumerate(ids):
        if all(r[k] == 1 for r in base_rows) and sum(r[k] for r in rows) / len(rows) < 0.5:
            out.append(case)
    return out


def unacceptable(dimension: str, runs: list, ids: tuple, rows: tuple) -> list[str]:
    """Cases that tripped a red line: any failing verdict on an EVAL-T dimension, or a record listing `red_lines`."""
    hit = set()
    if str(dimension).startswith("EVAL-T"):
        hit |= {case for k, case in enumerate(ids) if any(r[k] == 0 for r in rows)}
    for r in runs:
        for c in r["cases"]:
            if c.get("red_lines"):
                hit.add(c["test_case_id"])
    return sorted(hit)
