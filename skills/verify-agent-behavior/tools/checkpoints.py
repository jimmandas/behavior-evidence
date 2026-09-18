#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml"]
# ///
"""The checkpoint queue: the agent opens entries, a named human closes them.

    uv run <skill>/tools/checkpoints.py open  --queue Q --type C3 --obligation ABS-B05 --needed "…" [--blocks task-12 …] [--estimate 45] [--dimension EVAL-D02] [--prepared file …]
    uv run <skill>/tools/checkpoints.py close --queue Q --id CP-0003 --by "Jim Mandas" --status done|declined --decision "…" [--actual 40]
    uv run <skill>/tools/checkpoints.py list  --queue Q [--open]

The queue lives with the rest of the evidence, outside the repo. The plugin's hook lets the
coding agent run `open` and `list`, and blocks `close` and any other write to that directory:
**closing a checkpoint is a human act**, done in a terminal outside the agent's session. A C4
clears a review only with `status: done` and a `closed_by` (slice_gate.py).

Exit codes: 0 ok · 3 bad input.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import sys
from pathlib import Path

TYPES = {"C1", "C2", "C3", "C4", "C5"}


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def load(queue: Path) -> list[dict]:
    import yaml

    if not queue.exists():
        return []
    data = yaml.safe_load(queue.read_text()) or []
    if not isinstance(data, list):
        raise ValueError(f"{queue} must be a list of checkpoint entries")
    return data


def save(queue: Path, entries: list[dict]) -> None:
    import yaml

    queue.parent.mkdir(parents=True, exist_ok=True)
    queue.write_text(yaml.safe_dump(entries, sort_keys=False))


def open_entry(queue: Path, type_: str, obligation: str, needed: str, blocks=(), estimate=None,
               dimension=None, prepared=()) -> dict:
    if type_ not in TYPES:
        raise ValueError(f"type must be one of {sorted(TYPES)}")
    if not obligation or not needed:
        raise ValueError("an entry needs the obligation and what the human is asked to do")
    entries = load(queue)
    numbers = [int(e["id"].split("-")[1]) for e in entries if str(e.get("id", "")).startswith("CP-")]
    entry = {"id": f"CP-{(max(numbers) + 1) if numbers else 1:04d}", "type": type_, "obligation": obligation,
             "dimension": dimension, "opened": _now(), "needed": needed, "prepared": list(prepared),
             "estimate_min": estimate, "blocks": list(blocks), "status": "open",
             "closed": None, "closed_by": None, "actual_min": None, "decision": None}
    entries.append(entry)
    save(queue, entries)
    return entry


def close_entry(queue: Path, id_: str, by: str, status: str, decision: str, actual=None) -> dict:
    if status not in ("done", "declined"):
        raise ValueError("status is done or declined")
    if not by or not by.strip():
        raise ValueError("a checkpoint is closed by a named person (--by)")
    if not decision or not decision.strip():
        raise ValueError("record the decision in one line (--decision)")
    entries = load(queue)
    for e in entries:
        if e.get("id") == id_:
            if e.get("status") in ("done", "declined"):
                raise ValueError(f"{id_} is already {e['status']}")
            e.update(status=status, closed=_now(), closed_by=by.strip(), decision=decision.strip(), actual_min=actual)
            save(queue, entries)
            return e
    raise ValueError(f"no checkpoint {id_} in {queue}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="the BEV checkpoint queue")
    sub = ap.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("open")
    o.add_argument("--queue", type=Path, required=True)
    o.add_argument("--type", required=True, choices=sorted(TYPES))
    o.add_argument("--obligation", required=True)
    o.add_argument("--needed", required=True)
    o.add_argument("--dimension")
    o.add_argument("--blocks", nargs="*", default=[])
    o.add_argument("--prepared", nargs="*", default=[])
    o.add_argument("--estimate", type=int)
    c = sub.add_parser("close")
    c.add_argument("--queue", type=Path, required=True)
    c.add_argument("--id", required=True)
    c.add_argument("--by", required=True)
    c.add_argument("--status", required=True, choices=["done", "declined"])
    c.add_argument("--decision", required=True)
    c.add_argument("--actual", type=int)
    ls = sub.add_parser("list")
    ls.add_argument("--queue", type=Path, required=True)
    ls.add_argument("--open", action="store_true")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "open":
            e = open_entry(args.queue, args.type, args.obligation, args.needed, args.blocks, args.estimate,
                           args.dimension, args.prepared)
            print(f"{e['id']}  {e['type']}  {e['obligation']}  opened")
        elif args.cmd == "close":
            e = close_entry(args.queue, args.id, args.by, args.status, args.decision, args.actual)
            print(f"{e['id']}  {e['status']} by {e['closed_by']}")
        else:
            for e in load(args.queue):
                if args.open and e.get("status") in ("done", "declined"):
                    continue
                print(f"{e.get('id')}  {e.get('type')}  {e.get('obligation')}  {e.get('status')}  {e.get('needed') or ''}")
    except ValueError as err:
        print(f"INVALID  {err}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
