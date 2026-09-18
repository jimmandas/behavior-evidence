#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Turn an OpenTelemetry trace export (OTLP JSON) into the trace export the gates read.

    uv run <skill>/tools/export_traces.py spans.json [more.json ...] --out traces.jsonl

Input: OTLP JSON — one `ExportTraceServiceRequest` object per file, or one per line (the
OpenTelemetry Collector's file exporter writes the latter):

    {"resourceSpans": [{"scopeSpans": [{"spans": [{"traceId": "5b8e…", "spanId": "051f…", ...}]}]}]}

Output: one line per trace, `{"trace_id": "<traceId>", "span_ids": ["<spanId>", ...]}`.

**The harness must record the same IDs the tracer exported**: OTLP JSON carries them as hex
strings, so record `trace_id` and `evidence_span_ids` as those hex strings.

Tracing backends that speak OpenTelemetry (Langfuse, Phoenix, Jaeger and others) can export or
forward OTLP; how to get an OTLP JSON file out of each depends on its version — check its docs.
Whatever the route, the gate only needs trace IDs and span IDs, and the file must come from the
trace store, not from the harness that wrote the result.

Exit codes: 0 written · 3 unreadable input.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _requests(text: str):
    text = text.strip()
    if not text:
        return
    try:
        yield json.loads(text)
        return
    except json.JSONDecodeError:
        pass
    for line in text.splitlines():
        if line.strip():
            yield json.loads(line)


def collect(paths: list[Path]) -> dict[str, set[str]]:
    traces: dict[str, set[str]] = {}
    for path in paths:
        for req in _requests(path.read_text()):
            for rs in req.get("resourceSpans") or []:
                for ss in rs.get("scopeSpans") or rs.get("instrumentationLibrarySpans") or []:
                    for span in ss.get("spans") or []:
                        tid, sid = span.get("traceId"), span.get("spanId")
                        if not tid or not sid:
                            raise ValueError(f"{path}: a span without traceId or spanId")
                        traces.setdefault(tid, set()).add(sid)
    return traces


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="OTLP JSON -> traces.jsonl for the BEV gates")
    ap.add_argument("inputs", type=Path, nargs="+")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        traces = collect(args.inputs)
    except (OSError, ValueError, AttributeError) as e:
        print(f"INVALID  {e}", file=sys.stderr)
        return 3
    args.out.write_text("".join(json.dumps({"trace_id": t, "span_ids": sorted(s)}) + "\n" for t, s in sorted(traces.items())))
    print(f"{len(traces)} traces, {sum(len(s) for s in traces.values())} spans -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
