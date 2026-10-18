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


# --------------------------------------------------------------------------- CONTRACTS §9.2
FORBIDDEN = {"from_acct", "to_acct", "amt_paid", "amt_recv", "ts"}
TXN = {"ts": "2022-09-10T17:28:00", "from_acct": "80426FC30", "to_acct": "8025EF980", "to_bank": "013083",
       "amt_paid": 10795798.6, "cur_paid": "Euro", "amt_recv": 10795798.6, "cur_recv": "Euro", "fmt": "ACH"}


def _bank_local_fixture(tmp_path):
    """bank_local files shaped per §9.1 that DO contain per-transaction fields, plus leaky central files."""
    state = tmp_path / "state"; bl = state / "bank_local"
    for b in (1, 2):
        d = bl / f"bank_{b}"; (d / "sar").mkdir(parents=True)
        (d / "alerts.json").write_text(json.dumps({"meta": {"bank_id": b, "k": 20},
            "alerts": [dict(TXN, alert_id=f"B{b}-A01", rank=1, score=0.99, is_laundering=1, has_sar=True)]}))
        (d / "demo.json").write_text(json.dumps({"bank_id": b, "alert_id": f"B{b}-A01", "synthetic": True,
            "transaction": TXN, "related": [TXN], "score": 0.99}))
        (d / "sar" / f"B{b}-A01.md").write_text(f"# Report B{b}-A01\n\nAccount **80426FC30** paid 10,795,798.60 Euro.\n")
    (bl / "summary.json").write_text(json.dumps({"generated_at": "2026-10-17T21:30:00Z", "model_sha256": "ab" * 32,
        "per_bank": {"1": {"n_scored": 1000, "k": 20, "n_alerts": 20, "labelled_in_top_k": 2, "reports_written": 1,
                           "top_alert": TXN, "accounts": ["80426FC30"]},          # must be dropped
                     "2": {"n_scored": 900, "k": 20, "n_alerts": 20, "labelled_in_top_k": 1, "reports_written": 1}},
        "leaked_rows": [TXN]}))                                                   # must be dropped
    # leaky central files from other agents: old alerts.json, redteam target txn, egress audit lines with ts
    (state / "alerts.json").write_text(json.dumps({"alerts": [dict(TXN, alert_id="A06")]}))
    (state / "redteam.json").write_text(json.dumps({"attack": "canary_update", "target_row_txn": TXN,
        "game": {"canary": TXN}, "rows": {"DP off": {"sigma": 0, "attack_auc": 0.99}}}))
    (state / "footprint.json").write_text(json.dumps({"samples": [{"ts": "x", "rss": 1}], "seconds_per_round": 2.1}))
    logs = tmp_path / "logs" / "egress"; logs.mkdir(parents=True)
    (logs / "bank_1.jsonl").write_text('{"ts":"2026-10-17T22:03:28+00:00","bank_id":1,"round":1,"kind":"model_update",'
                                       '"bytes":700,"sha256":"ab","keys":["x"],"rows_shared":0,"params_shared":21}\n')
    return state, logs


def _keys_at_any_depth(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _keys_at_any_depth(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys_at_any_depth(v)


def test_state_is_aggregate_only(tmp_path):
    state, logs = _bank_local_fixture(tmp_path)
    s = create_app(state, logs).test_client().get("/api/state").get_json()
    leaked = FORBIDDEN & {str(k).lower() for k in _keys_at_any_depth(s)}
    assert not leaked, leaked
    body = json.dumps(s)
    assert "80426FC30" not in body and "10795798.6" not in body and "8025EF980" not in body
    assert "alerts" not in s                                       # no per-alert rows centrally
    agg = s["alerts_aggregate"]
    assert agg["per_bank"]["1"] == {"n_scored": 1000, "k": 20, "n_alerts": 20, "labelled_in_top_k": 2, "reports_written": 1}
    assert "leaked_rows" not in agg
    assert s["egress"]["tail"][0]["logged_at"].startswith("2026-10-17T22:03")   # audit time kept, renamed
    assert s["redteam"]["rows"]["DP off"]["attack_auc"] == 0.99                  # model-level content survives
    assert "logical" in s["boundary"]


def test_central_sar_route_removed(tmp_path):
    state, logs = _bank_local_fixture(tmp_path)
    (state / "sar").mkdir(); (state / "sar" / "A06.md").write_text("# old central report")
    r = create_app(state, logs).test_client().get("/api/sar/A06")
    assert r.status_code == 404 and r.get_json() == {"error": "not found"}


def test_bank_routes_serve_files_byte_for_byte(tmp_path):
    state, logs = _bank_local_fixture(tmp_path)
    c = create_app(state, logs).test_client()
    for b in ("1", "2"):
        d = state / "bank_local" / f"bank_{b}"
        r = c.get(f"/api/bank/{b}/alerts"); assert r.status_code == 200 and r.data == (d / "alerts.json").read_bytes()
        r = c.get(f"/api/bank/{b}/demo"); assert r.status_code == 200 and r.data == (d / "demo.json").read_bytes()
        r = c.get(f"/api/bank/{b}/sar/B{b}-A01")
        assert r.status_code == 200 and r.data == (d / "sar" / f"B{b}-A01.md").read_bytes()
        assert r.headers["Content-Type"].startswith("text/markdown")


def test_bank_routes_reject_cross_bank_traversal_and_bad_ids(tmp_path):
    state, logs = _bank_local_fixture(tmp_path)
    (state / "bank_local" / "secret.json").write_text('{"x": 1}')
    c = create_app(state, logs).test_client()
    bad = [
        "/api/bank/1/sar/B2-A01",            # bank 1 asking for bank 2's report (file exists)
        "/api/bank/2/sar/B1-A01",
        "/api/bank/5/alerts", "/api/bank/0/alerts", "/api/bank/01/alerts", "/api/bank/1a/demo", "/api/bank/-1/demo",
        "/api/bank/3/alerts",                # valid bank id, no files -> 404, not a crash
        "/api/bank/1/sar/B1-A1", "/api/bank/1/sar/B1-A001", "/api/bank/1/sar/b1-a01", "/api/bank/1/sar/B1-A01.md",
        "/api/bank/1/sar/../alerts", "/api/bank/1/sar/..%2Falerts", "/api/bank/1/sar/%2e%2e%2falerts",
        "/api/bank/1/sar/%2e%2e", "/api/bank/%2e%2e/alerts", "/api/bank/1/../secret.json",
        "/api/bank/1/sar/B1-A01%00", "/api/bank/1/other", "/api/sar/B1-A01",
    ]
    for url in bad:
        r = c.get(url)
        assert r.status_code == 404, url
        assert r.get_json() == {"error": "not found"}, url


def test_bank_route_refuses_symlink_out_of_folder(tmp_path):
    state, logs = _bank_local_fixture(tmp_path)
    outside = tmp_path / "outside.md"; outside.write_text("not this bank's file")
    link = state / "bank_local" / "bank_1" / "sar" / "B1-A02.md"
    link.symlink_to(outside)
    assert create_app(state, logs).test_client().get("/api/bank/1/sar/B1-A02").status_code == 404


def test_bank_route_size_cap(tmp_path):
    state, logs = _bank_local_fixture(tmp_path)
    (state / "bank_local" / "bank_1" / "sar" / "B1-A03.md").write_bytes(b"x" * (256 * 1024 + 1))
    assert create_app(state, logs).test_client().get("/api/bank/1/sar/B1-A03").status_code == 404
