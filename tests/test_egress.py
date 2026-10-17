"""Tests for fedaml.egress (CONTRACTS §5). Run: python -m pytest tests -q"""
from __future__ import annotations

import hashlib
import json

import pytest

from fedaml import egress


class _FakeResponse:
    status_code = 200

    def __init__(self, body: bytes):
        self.body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"ok": True, "received_bytes": len(self.body)}


def _install_fake_post(monkeypatch):
    calls: list[dict] = []

    def fake_post(url, data=None, timeout=None, headers=None, **kw):
        calls.append({"url": url, "data": data, "timeout": timeout, "headers": headers})
        return _FakeResponse(data)

    monkeypatch.setattr(egress.requests, "post", fake_post)
    return calls


def _valid_update(n_features: int) -> dict:
    return {
        "bank_id": 1, "round": 3, "n_samples": 412000,
        "delta_coef": [0.01 * i for i in range(n_features)],
        "delta_intercept": [0.01],
        "clip_norm": 1.0, "dp": {"enabled": True, "sigma": 0.8},
        "feature_names_sha256": "f" * 64, "payload_sha256": "p" * 64,
        "signature": None,
    }


def _lines(path):
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def test_rows_key_raises_and_is_logged_blocked(tmp_path, monkeypatch):
    calls = _install_fake_post(monkeypatch)
    payload = {"bank_id": 1, "round": 1,
               "rows": [{"from_acct": "A", "to_acct": "B", "amt_paid": 10.0}]}
    with pytest.raises(egress.EgressViolation, match="forbidden key 'rows'"):
        egress.send("http://coordinator:8000", payload, 1, 1, logs_dir=tmp_path)
    assert calls == [], "a blocked payload must never reach requests.post"
    recs = _lines(tmp_path / "bank_1.jsonl")
    assert len(recs) == 1
    assert recs[0]["kind"] == "blocked"
    assert recs[0]["rows_shared"] == 0 and recs[0]["params_shared"] == 0
    assert "rows" in recs[0]["keys"]


def test_valid_update_logged_with_rows_shared_zero(tmp_path, monkeypatch):
    calls = _install_fake_post(monkeypatch)
    n = egress.feature_count()
    payload = _valid_update(n)
    reply = egress.send("http://coordinator:8000", payload, 1, 3, logs_dir=tmp_path)
    assert reply["ok"] is True
    assert len(calls) == 1
    assert calls[0]["url"] == "http://coordinator:8000/update"
    assert calls[0]["headers"]["Content-Type"] == "application/json"
    assert json.loads(calls[0]["data"]) == payload
    recs = _lines(tmp_path / "bank_1.jsonl")
    assert len(recs) == 1
    rec = recs[0]
    assert rec["kind"] == "model_update"
    assert rec["rows_shared"] == 0
    assert rec["params_shared"] == n + 1
    assert rec["bank_id"] == 1 and rec["round"] == 3
    assert rec["bytes"] == len(calls[0]["data"])
    assert rec["sha256"] == hashlib.sha256(calls[0]["data"]).hexdigest()
    assert set(rec["keys"]) == set(payload)


def test_forbidden_key_is_case_insensitive_and_nested(tmp_path, monkeypatch):
    calls = _install_fake_post(monkeypatch)
    nested = {"bank_id": 2, "round": 1, "meta": {"Is_Laundering": 1}}
    with pytest.raises(egress.EgressViolation, match="Is_Laundering"):
        egress.send("http://c:8000", nested, 2, 1, logs_dir=tmp_path)
    in_list = {"bank_id": 2, "round": 1, "items": [{"TS": "2024-01-01"}]}
    with pytest.raises(egress.EgressViolation, match="TS"):
        egress.send("http://c:8000", in_list, 2, 1, logs_dir=tmp_path)
    assert calls == []


def test_list_longer_than_one_weight_vector_raises(tmp_path, monkeypatch):
    _install_fake_post(monkeypatch)
    payload = _valid_update(egress.feature_count())
    payload["delta_coef"] = [0.0] * (egress.max_list_len() + 1)
    with pytest.raises(egress.EgressViolation, match="max is"):
        egress.send("http://c:8000", payload, 3, 1, logs_dir=tmp_path)


def test_oversize_payload_raises(tmp_path, monkeypatch):
    _install_fake_post(monkeypatch)
    payload = _valid_update(egress.feature_count())
    payload["note"] = "x" * (egress.MAX_BYTES + 1)
    with pytest.raises(egress.EgressViolation, match="bytes"):
        egress.send("http://c:8000", payload, 3, 1, logs_dir=tmp_path)


def test_non_json_payload_raises(tmp_path, monkeypatch):
    _install_fake_post(monkeypatch)
    np = pytest.importorskip("numpy")
    payload = _valid_update(egress.feature_count())
    payload["delta_coef"] = np.zeros(egress.feature_count(), dtype="float32")
    with pytest.raises(egress.EgressViolation, match="tolist"):
        egress.send("http://c:8000", payload, 4, 1, logs_dir=tmp_path)


def test_summarize_and_tail(tmp_path, monkeypatch):
    _install_fake_post(monkeypatch)
    n = egress.feature_count()
    egress.send("http://c:8000", _valid_update(n), 1, 1, logs_dir=tmp_path)
    egress.send("http://c:8000", _valid_update(n), 1, 2, logs_dir=tmp_path)
    egress.send("http://c:8000", _valid_update(n), 2, 1, logs_dir=tmp_path)
    with pytest.raises(egress.EgressViolation):
        egress.send("http://c:8000", {"data": [1, 2, 3]}, 2, 2, logs_dir=tmp_path)

    s = egress.summarize(tmp_path)
    assert s["per_bank"]["1"]["messages"] == 2
    assert s["per_bank"]["1"]["params_shared"] == 2 * (n + 1)
    assert s["per_bank"]["2"]["messages"] == 1
    assert s["per_bank"]["2"]["blocked"] == 1
    assert s["totals"]["rows_shared"] == 0
    assert s["totals"]["messages"] == 3 and s["totals"]["blocked"] == 1
    assert s["totals"]["banks"] == 2

    t = egress.tail(tmp_path, 2)
    assert len(t) == 2 and t[-1]["kind"] == "blocked"


def test_summarize_missing_dir_is_empty(tmp_path):
    s = egress.summarize(tmp_path / "nope")
    assert s["per_bank"] == {} and s["totals"]["messages"] == 0
