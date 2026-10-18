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


def test_empty_egress_dir_shows_zero_not_error(tmp_path):
    """Between takes logs/egress/*.jsonl is archived: the dir exists but is empty."""
    logs = tmp_path / "logs" / "egress"; logs.mkdir(parents=True)
    app = create_app(tmp_path / "state", logs)
    s = app.test_client().get("/api/state").get_json()
    t = s["egress"]["totals"]
    assert t["messages"] == 0 and t["rows_shared"] == 0 and t["blocked"] == 0 and t["params_shared"] == 0
    assert s["egress"]["tail"] == [] and s["files"]["logs/egress"] == {"present": True, "n_files": 0}


def _sar_fixture(tmp_path):
    state = tmp_path / "state"; (state / "sar").mkdir(parents=True)
    (state / "sar" / "A06.md").write_text("# Suspicious Activity Report — alert A06\n\n**Analyst assessment (LLM).** text\n")
    (tmp_path / "secret.md").write_text("do not serve")
    (state / "alerts.json").write_text(json.dumps({"meta": {"demo_alert_id": "A06", "prevalence": 0.00177},
        "alerts": [{"alert_id": "A06", "rank": 6, "score": 1.0, "banks_involved": ["1", "2"],
                    "trigger": {"amt_paid": 10.0, "cur_paid": "Euro", "is_laundering": 1}},
                   {"alert_id": "A07", "rank": 7, "score": 0.9, "banks_involved": ["1"],
                    "trigger": {"amt_paid": 5.0, "cur_paid": "Euro", "is_laundering": 0}}]}))
    return state


def test_sar_route_serves_known_report(tmp_path):
    client = create_app(_sar_fixture(tmp_path), tmp_path / "logs").test_client()
    r = client.get("/api/sar/A06")
    assert r.status_code == 200 and r.get_json()["markdown"].startswith("# Suspicious Activity Report")


def test_sar_route_rejects_traversal_and_unknown_ids(tmp_path):
    client = create_app(_sar_fixture(tmp_path), tmp_path / "logs").test_client()
    for bad in ["A07", "A999", "../secret", "..%2Fsecret", "%2e%2e%2fsecret", "A06.md", "a06", "A6", "A06%00", "B06"]:
        assert client.get(f"/api/sar/{bad}").status_code == 404, bad
    assert client.get("/api/sar/../../secret.md").status_code == 404


def test_alert_summary_in_state(tmp_path):
    s = create_app(_sar_fixture(tmp_path), tmp_path / "logs").test_client().get("/api/state").get_json()
    rows = {a["alert_id"]: a for a in s["alerts"]["alerts"]}
    assert rows["A06"]["has_sar"] is True and rows["A07"]["has_sar"] is False
    assert rows["A06"]["is_laundering"] == 1 and s["alerts"]["meta"]["demo_alert_id"] == "A06"
    assert s["files"]["sar/"]["n_files"] == 1
