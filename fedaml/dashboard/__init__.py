"""fedaml.dashboard — the regulator view (CONTRACTS §6, AUDIT brief task 3).

Flask app on :8050.  ``GET /`` serves one HTML page that polls
``GET /api/state`` every 3 s.  The API merges ``state/status.json``,
``state/redteam.json``, ``state/baselines.json``, ``state/footprint.json`` and
the egress audit summary from ``logs/egress``.  Every file is read
defensively: a missing or half-written file becomes ``null`` and the page shows
"waiting", it never crashes.

Run: ``python -m fedaml.dashboard --port 8050``
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, send_from_directory

from fedaml import egress

__all__ = ["create_app", "build_state", "load_json", "STATE_FILES"]

log = logging.getLogger("fedaml.dashboard")

STATIC_DIR = Path(__file__).resolve().parent / "static"
DEFAULT_STATE_DIR = Path(os.environ.get("FEDAML_STATE_DIR", "state"))
DEFAULT_LOGS_DIR = egress.DEFAULT_LOGS_DIR
#: Optional *policy* budget shown as a tick on the privacy meter; off unless set
#: (MASTER 16:10: the meter compares ε spent with the run's planned total, not a budget).
_eb = os.environ.get("FEDAML_EPS_BUDGET", "").strip()
DEFAULT_EPS_BUDGET: float | None = float(_eb) if _eb else None
TAIL_LINES = 10

#: api key -> file name under the state dir.  The rogue comparison files are
#: optional (FEDERATION writes them for the defense off/on demo).
STATE_FILES: dict[str, str] = {
    "status": "status.json",
    "redteam": "redteam.json",
    "baselines": "baselines.json",
    "footprint": "footprint.json",
    "status_rogue_on": "status_rogue_on.json",
    "status_rogue_off": "status_rogue_off.json",
    "alerts": "alerts.json",
}


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
    return {
        "present": True,
        "mtime": mtime.isoformat(timespec="seconds"),
        "age_s": round((_now() - mtime).total_seconds(), 1),
        "bytes": st.st_size,
    }


def build_state(state_dir: Path = DEFAULT_STATE_DIR, logs_dir: Path = DEFAULT_LOGS_DIR,
                eps_budget: float | None = DEFAULT_EPS_BUDGET) -> dict:
    """Everything the page needs in one JSON document."""
    out: dict[str, Any] = {
        "now": _now().isoformat(timespec="seconds"),
        "eps_budget": eps_budget,
        "state_dir": str(state_dir),
        "logs_dir": str(logs_dir),
        "files": {},
    }
    for key, name in STATE_FILES.items():
        path = state_dir / name
        out[key] = load_json(path)
        out["files"][name] = file_info(path)
    try:
        summary = egress.summarize(logs_dir)
        summary["tail"] = egress.tail(logs_dir, TAIL_LINES)
    except Exception as exc:  # the audit trail must never take the page down
        log.warning("egress summary failed: %s", exc)
        summary = {"per_bank": {}, "totals": {}, "tail": [], "error": str(exc)}
    out["egress"] = summary
    out["files"]["logs/egress"] = {
        "present": logs_dir.is_dir(),
        "n_files": len(list(logs_dir.glob("bank_*.jsonl"))) if logs_dir.is_dir() else 0,
    }
    return out


def create_app(state_dir: Path = DEFAULT_STATE_DIR, logs_dir: Path = DEFAULT_LOGS_DIR,
               eps_budget: float | None = DEFAULT_EPS_BUDGET) -> Flask:
    """Build the Flask app (kept separate from ``run`` so tests can use it)."""
    app = Flask("fedaml.dashboard", static_folder=None)
    app.config["JSON_SORT_KEYS"] = False
    state_dir, logs_dir = Path(state_dir), Path(logs_dir)

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

    @app.get("/api/health")
    def api_health():
        return jsonify({"ok": True, "now": _now().isoformat(timespec="seconds")})

    return app
