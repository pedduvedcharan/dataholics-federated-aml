"""Tests for the regulator dashboard API (CONTRACTS §6 readers must be defensive)."""
from __future__ import annotations

import json

from fedaml.dashboard import build_state, create_app


def test_api_state_with_nothing_present(tmp_path):
    app = create_app(tmp_path / "state", tmp_path / "logs" / "egress")
    client = app.test_client()
    r = client.get("/api/state")
    assert r.status_code == 200
    s = r.get_json()
    assert s["status"] is None and s["redteam"] is None
    assert s["files"]["status.json"]["present"] is False
    assert s["egress"]["totals"]["messages"] == 0 and s["egress"]["tail"] == []
    assert client.get("/").status_code == 200
    assert b"Regulator view" in client.get("/").data


def test_half_written_file_is_null_not_crash(tmp_path):
    state = tmp_path / "state"; state.mkdir()
    (state / "status.json").write_text('{"round": 3, "rounds": [')  # mid-write
    (state / "redteam.json").write_text(json.dumps({"attack": "loss_threshold"}))
    s = build_state(state, tmp_path / "nologs")
    assert s["status"] is None
    assert s["redteam"]["attack"] == "loss_threshold"
    assert s["files"]["status.json"]["present"] is True


def test_egress_summary_is_merged(tmp_path):
    logs = tmp_path / "logs" / "egress"; logs.mkdir(parents=True)
    (logs / "bank_2.jsonl").write_text(
        '{"ts":"2026-10-17T20:00:00+00:00","bank_id":2,"round":1,"kind":"model_update","bytes":700,'
        '"sha256":"ab","keys":["x"],"rows_shared":0,"params_shared":21}\n'
        'garbage line\n'
        '{"ts":"2026-10-17T20:00:01+00:00","bank_id":2,"round":0,"kind":"blocked","reason":"rows"}\n')
    s = build_state(tmp_path / "state", logs, eps_budget=8)
    t = s["egress"]["totals"]
    assert t["messages"] == 1 and t["blocked"] == 1 and t["rows_shared"] == 0 and t["params_shared"] == 21
    assert [r["kind"] for r in s["egress"]["tail"]] == ["model_update", "blocked"]
    assert s["eps_budget"] == 8
