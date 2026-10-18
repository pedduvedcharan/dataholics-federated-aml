"""fedaml.dashboard — the regulator view (CONTRACTS §6) and the bank-scoped views (CONTRACTS §9.2).

Flask app on :8050.  ``GET /`` serves one HTML page.

Central (coordinator / regulator) API — aggregates only:
  ``GET /api/state`` merges ``state/status.json``, ``redteam.json``, ``baselines.json``,
  ``footprint.json``, the rogue comparison files, the egress audit summary, and
  ``alerts_aggregate`` (= ``state/bank_local/summary.json``, whitelisted fields).  It never
  carries per-transaction fields: as a last line of defence every key in
  :data:`CENTRAL_FORBIDDEN_KEYS` is stripped at any depth, and the egress audit line's own
  timestamp is renamed ``logged_at``.

Bank-scoped API — the "inside bank <b>" view of the demo:
  ``GET /api/bank/<b>/alerts``, ``/api/bank/<b>/demo``, ``/api/bank/<b>/sar/<alert_id>``
  with ``<b>`` in {1,2,3,4} and ``alert_id`` matching ``^B<b>-A[0-9]{2}$``.  Responses are the
  files byte for byte; anything else is a JSON 404.

Honest boundary: banks and regulator share one VM and this one process, so the bank boundary is a
*logical* access boundary (separate route prefix, separate files, tests), not network isolation.

Every file is read defensively: a missing or half-written file becomes ``null`` or a 404, never a crash.
Run: ``python -m fedaml.dashboard --port 8050``
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, send_from_directory

from fedaml import egress

__all__ = ["create_app", "build_state", "load_json", "STATE_FILES", "CENTRAL_FORBIDDEN_KEYS",
           "BANK_IDS", "bank_file", "scrub_central", "aggregate_alerts"]

log = logging.getLogger("fedaml.dashboard")

STATIC_DIR = Path(__file__).resolve().parent / "static"
DEFAULT_STATE_DIR = Path(os.environ.get("FEDAML_STATE_DIR", "state"))
DEFAULT_LOGS_DIR = egress.DEFAULT_LOGS_DIR
#: Optional *policy* budget shown as a tick on the privacy meter; off unless set.
_eb = os.environ.get("FEDAML_EPS_BUDGET", "").strip()
DEFAULT_EPS_BUDGET: float | None = float(_eb) if _eb else None
TAIL_LINES = 10
MAX_BANK_FILE_BYTES = 256 * 1024
BANK_IDS = ("1", "2", "3", "4")

#: api key -> file name under the state dir (central, model-level files only).
STATE_FILES: dict[str, str] = {
    "status": "status.json",
    "redteam": "redteam.json",
    "baselines": "baselines.json",
    "footprint": "footprint.json",
    "status_rogue_on": "status_rogue_on.json",
    "status_rogue_off": "status_rogue_off.json",
}

#: Per-transaction fields that must never appear in the central API (CONTRACTS §9.2), plus the
#: containers that carry them in other agents' files (e.g. redteam's target_row_txn).
CENTRAL_FORBIDDEN_KEYS = frozenset({
    "ts", "from_acct", "to_acct", "amt_paid", "amt_recv", "cur_paid", "cur_recv",
    "from_bank", "to_bank", "accounts", "account", "target_row_txn", "transaction", "trigger",
})

#: The only fields of state/bank_local/summary.json that reach the regulator.
_AGG_TOP = ("generated_at", "model_sha256", "model_round", "model_file")
_AGG_PER_BANK = ("n_scored", "k", "n_alerts", "labelled_in_top_k", "reports_written", "prevalence", "threshold_rule")


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def load_json(path: Path) -> Any | None:
    """Parse a JSON file; ``None`` if it is missing, mid-rename or invalid."""
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        if path.exists():
            log.debug("could not parse %s: %s", path, exc)
        return None


def file_info(path: Path) -> dict:
    """Presence, size and age of a file, for the page's freshness pills."""
    try:
        st = path.stat()
    except OSError:
        return {"present": False, "mtime": None, "age_s": None, "bytes": 0}
    mtime = _dt.datetime.fromtimestamp(st.st_mtime, _dt.timezone.utc)
    return {"present": True, "mtime": mtime.isoformat(timespec="seconds"),
            "age_s": round((_now() - mtime).total_seconds(), 1), "bytes": st.st_size}


# --------------------------------------------------------------------------- central (aggregate only)
def scrub_central(obj: Any) -> Any:
    """Copy of ``obj`` with every CENTRAL_FORBIDDEN_KEYS key removed at any depth."""
    if isinstance(obj, dict):
        return {k: scrub_central(v) for k, v in obj.items() if str(k).lower() not in CENTRAL_FORBIDDEN_KEYS}
    if isinstance(obj, list):
        return [scrub_central(v) for v in obj]
    return obj


def aggregate_alerts(summary: Any) -> dict | None:
    """Whitelisted view of state/bank_local/summary.json: counts only, no ids/amounts/accounts."""
    if not isinstance(summary, dict):
        return None
    out: dict[str, Any] = {k: summary[k] for k in _AGG_TOP if k in summary and not isinstance(summary[k], (dict, list))}
    per = summary.get("per_bank") if isinstance(summary.get("per_bank"), dict) else {}
    out["per_bank"] = {}
    for b, v in per.items():
        if str(b) in BANK_IDS and isinstance(v, dict):
            out["per_bank"][str(b)] = {k: v[k] for k in _AGG_PER_BANK if k in v and not isinstance(v[k], (dict, list))}
    return out


def _egress_for_regulator(logs_dir: Path) -> dict:
    try:
        summary = egress.summarize(logs_dir)
        tail = []
        for r in egress.tail(logs_dir, TAIL_LINES):
            r = dict(r)
            r["logged_at"] = r.pop("ts", None)   # audit-line time, not a transaction time
            tail.append(r)
        summary["tail"] = tail
    except Exception as exc:  # the audit trail must never take the page down
        log.warning("egress summary failed: %s", exc)
        summary = {"per_bank": {}, "totals": {}, "tail": [], "error": str(exc)}
    return summary


def build_state(state_dir: Path = DEFAULT_STATE_DIR, logs_dir: Path = DEFAULT_LOGS_DIR,
                eps_budget: float | None = DEFAULT_EPS_BUDGET) -> dict:
    """Everything the regulator page needs in one JSON document (aggregates only)."""
    out: dict[str, Any] = {
        "now": _now().isoformat(timespec="seconds"),
        "eps_budget": eps_budget,
        "state_dir": str(state_dir),
        "logs_dir": str(logs_dir),
        "boundary": "logical: banks and regulator share one VM and one dashboard process",
        "files": {},
    }
    for key, name in STATE_FILES.items():
        path = state_dir / name
        out[key] = load_json(path)
        out["files"][name] = file_info(path)
    summary_path = state_dir / "bank_local" / "summary.json"
    out["alerts_aggregate"] = aggregate_alerts(load_json(summary_path))
    out["files"]["bank_local/summary.json"] = file_info(summary_path)
    out["egress"] = _egress_for_regulator(logs_dir)
    out["files"]["logs/egress"] = {
        "present": logs_dir.is_dir(),
        "n_files": len(list(logs_dir.glob("bank_*.jsonl"))) if logs_dir.is_dir() else 0,
    }
    return scrub_central(out)


# --------------------------------------------------------------------------- bank-scoped
def bank_file(state_dir: Path, bank: str, kind: str, alert_id: str | None = None) -> Path | None:
    """Path of a bank-local file, or None unless every check passes.

    ``bank`` must be one of BANK_IDS; ``kind`` is alerts | demo | sar; a sar id must match
    ``^B<bank>-A[0-9]{2}$`` (a bank can only read its own ids).  The resolved path must sit directly in
    ``state/bank_local/bank_<bank>/`` (or its ``sar/``), so symlinks and traversal are refused.
    """
    if bank not in BANK_IDS:
        return None
    bank_dir = (state_dir / "bank_local" / f"bank_{bank}").resolve()
    if kind in ("alerts", "demo"):
        expected_dir, name = bank_dir, f"{kind}.json"
    elif kind == "sar":
        if not isinstance(alert_id, str) or not re.fullmatch(rf"B{bank}-A[0-9]{{2}}", alert_id):
            return None
        expected_dir, name = bank_dir / "sar", f"{alert_id}.md"
    else:
        return None
    path = (expected_dir / name).resolve()
    if path.parent != expected_dir or path.name != name or not path.is_file():
        return None
    return path


def _read_capped(path: Path) -> bytes | None:
    try:
        with path.open("rb") as fh:
            data = fh.read(MAX_BANK_FILE_BYTES + 1)
    except OSError:
        return None
    return None if len(data) > MAX_BANK_FILE_BYTES else data


def _not_found():
    resp = jsonify({"error": "not found"})
    resp.status_code = 404
    resp.headers["Cache-Control"] = "no-store"
    return resp


def create_app(state_dir: Path = DEFAULT_STATE_DIR, logs_dir: Path = DEFAULT_LOGS_DIR,
               eps_budget: float | None = DEFAULT_EPS_BUDGET) -> Flask:
    """Build the Flask app (kept separate from ``run`` so tests can use it)."""
    app = Flask("fedaml.dashboard", static_folder=None)
    app.config["JSON_SORT_KEYS"] = False
    state_dir, logs_dir = Path(state_dir), Path(logs_dir)

    @app.errorhandler(404)
    def _404(_e):
        return _not_found()

    @app.get("/")
    def index():
        resp = send_from_directory(STATIC_DIR, "index.html")
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.get("/api/state")
    def api_state():
        resp = jsonify(build_state(state_dir, logs_dir, eps_budget))
        resp.headers["Cache-Control"] = "no-store"
        return resp

    def _serve(bank: str, kind: str, alert_id: str | None = None):
        path = bank_file(state_dir, bank, kind, alert_id)
        data = _read_capped(path) if path else None
        if data is None:
            return _not_found()
        mime = "text/markdown; charset=utf-8" if kind == "sar" else "application/json"
        resp = Response(data, status=200, headers={"Content-Type": mime, "Cache-Control": "no-store",
                                                   "X-Fedaml-Scope": f"bank {bank} (logical boundary)"})
        return resp

    @app.get("/api/bank/<bank>/alerts")
    def api_bank_alerts(bank: str):
        return _serve(bank, "alerts")

    @app.get("/api/bank/<bank>/demo")
    def api_bank_demo(bank: str):
        return _serve(bank, "demo")

    @app.get("/api/bank/<bank>/sar/<alert_id>")
    def api_bank_sar(bank: str, alert_id: str):
        return _serve(bank, "sar", alert_id)

    @app.get("/api/health")
    def api_health():
        return jsonify({"ok": True, "now": _now().isoformat(timespec="seconds")})

    return app
