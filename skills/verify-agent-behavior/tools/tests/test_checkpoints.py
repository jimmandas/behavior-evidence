"""The checkpoint queue tool: the agent opens, a named human closes."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import checkpoints as cp  # noqa: E402


def test_open_numbers_entries_and_starts_them_open(tmp_path):
    q = tmp_path / "q.yaml"
    a = cp.open_entry(q, "C3", "ABS-B05", "review 100 traces", blocks=["task-9"], estimate=45)
    b = cp.open_entry(q, "C4", "ABS-B03", "judgment review")
    assert (a["id"], b["id"]) == ("CP-0001", "CP-0002")
    assert a["status"] == "open" and a["closed_by"] is None and a["blocks"] == ["task-9"]
    assert len(yaml.safe_load(q.read_text())) == 2


def test_close_records_who_when_and_what(tmp_path):
    q = tmp_path / "q.yaml"
    cp.open_entry(q, "C4", "ABS-B03", "judgment review")
    e = cp.close_entry(q, "CP-0001", "Jim Mandas", "done", "cases credible", actual=30)
    assert e["closed_by"] == "Jim Mandas" and e["closed"] and e["actual_min"] == 30
    assert yaml.safe_load(q.read_text())[0]["status"] == "done"


@pytest.mark.parametrize("kw,match", [
    ({"by": " ", "status": "done", "decision": "ok"}, "named person"),
    ({"by": "Jim", "status": "done", "decision": ""}, "decision"),
    ({"by": "Jim", "status": "approved", "decision": "ok"}, "done or declined"),
])
def test_close_needs_a_name_a_decision_and_a_valid_status(tmp_path, kw, match):
    q = tmp_path / "q.yaml"
    cp.open_entry(q, "C4", "ABS-B03", "judgment review")
    with pytest.raises(ValueError, match=match):
        cp.close_entry(q, "CP-0001", **kw)


def test_closed_entries_stay_closed(tmp_path):
    q = tmp_path / "q.yaml"
    cp.open_entry(q, "C4", "ABS-B03", "judgment review")
    cp.close_entry(q, "CP-0001", "Jim", "declined", "not credible")
    with pytest.raises(ValueError, match="already"):
        cp.close_entry(q, "CP-0001", "Jim", "done", "changed my mind")


def test_unknown_id_and_bad_type_are_refused(tmp_path):
    q = tmp_path / "q.yaml"
    with pytest.raises(ValueError):
        cp.close_entry(q, "CP-0404", "Jim", "done", "ok")
    with pytest.raises(ValueError):
        cp.open_entry(q, "C9", "ABS-B03", "x")


def test_cli_round_trip(tmp_path, capsys):
    q = str(tmp_path / "q.yaml")
    assert cp.main(["open", "--queue", q, "--type", "C3", "--obligation", "ABS-B05", "--needed", "review"]) == 0
    assert cp.main(["list", "--queue", q, "--open"]) == 0
    assert "CP-0001" in capsys.readouterr().out
    assert cp.main(["close", "--queue", q, "--id", "CP-0001", "--by", "Jim", "--status", "done", "--decision", "fine"]) == 0
    assert "done by Jim" in capsys.readouterr().out
    assert cp.main(["list", "--queue", q, "--open"]) == 0
    assert capsys.readouterr().out == ""
    assert cp.main(["close", "--queue", q, "--id", "CP-0001", "--by", "Jim", "--status", "done", "--decision", "x"]) == 3


def test_queue_the_slice_gate_accepts(tmp_path):
    """What checkpoints.py writes is what slice_gate.py reads."""
    import slice_gate as sg
    q = tmp_path / "q.yaml"
    cp.open_entry(q, "C4", "ABS-B03", "judgment review")
    cp.close_entry(q, "CP-0001", "Jim", "done", "ok")
    entries = yaml.safe_load(q.read_text())
    assert entries[0]["type"] == "C4" and entries[0]["status"] in sg.CLOSED_STATUSES and entries[0]["closed_by"]
