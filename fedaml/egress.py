"""fedaml.egress — the only door out of a bank (CONTRACTS §5).

Every bank sends its model update through :func:`send` and nothing else.
The function refuses anything that looks like transaction data (forbidden
column names, lists longer than one model-weight vector, oversized bodies),
writes one audit line per attempt to ``logs/egress/bank_<id>.jsonl`` and only
then POSTs the update to the coordinator.  Blocked attempts are logged too, so
the regulator dashboard can show them.

Audit line (success)::

    {"ts": iso, "bank_id": 1, "round": 3, "kind": "model_update", "bytes": N,
     "sha256": "...", "keys": [...], "rows_shared": 0, "params_shared": n}

Audit line (violation)::

    {"ts": iso, "bank_id": 1, "round": 3, "kind": "blocked", "reason": "...",
     "bytes": N | null, "keys": [...], "rows_shared": 0, "params_shared": 0}
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Iterator

import requests

__all__ = [
    "FORBIDDEN_KEYS", "MAX_BYTES", "EgressViolation",
    "feature_count", "max_list_len", "validate", "send",
    "iter_records", "summarize", "tail",
]

log = logging.getLogger("fedaml.egress")

#: Column names of the raw dataset plus generic container names.  A payload
#: carrying any of these (case-insensitive, at any nesting depth) is refused.
FORBIDDEN_KEYS: frozenset[str] = frozenset({
    "ts", "from_acct", "to_acct", "amt_paid", "amt_recv", "cur_paid",
    "cur_recv", "fmt", "is_laundering", "rows", "records", "data",
})
#: Hard cap on the serialised JSON body.
MAX_BYTES: int = 64 * 1024
#: Deepest nesting we are willing to inspect; anything deeper is refused.
MAX_DEPTH: int = 8
REQUEST_TIMEOUT_S: float = 30.0
DEFAULT_LOGS_DIR = Path(os.environ.get("FEDAML_EGRESS_LOGS", "logs/egress"))

# CONTRACTS §3: 9 scalar features + 7 payment-format one-hots + 4 graph
# features.  Used only while fedaml.features is not importable (early in the
# build, or in containers that do not ship the models module).
_CONTRACT_FEATURE_COUNT = 20


class EgressViolation(ValueError):
    """Raised when a payload must not leave the bank."""


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #
def feature_count() -> int:
    """Length of ``FEATURE_NAMES`` from ``fedaml.features``; contract fallback."""
    try:
        from fedaml.features import FEATURE_NAMES  # type: ignore
        return len(FEATURE_NAMES)
    except Exception:  # module missing or half-built: stay on the contract
        return _CONTRACT_FEATURE_COUNT


def max_list_len() -> int:
    """Longest list allowed anywhere in a payload: one coefficient vector + 1."""
    return feature_count() + 1


def _walk(value: Any, path: str, depth: int, limit: int) -> int:
    """Check keys and list lengths recursively; return numeric list elements."""
    if depth > MAX_DEPTH:
        raise EgressViolation(f"payload nested deeper than {MAX_DEPTH} at {path}")
    params = 0
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise EgressViolation(f"non-string key {key!r} at {path or 'top level'}")
            if key.strip().lower() in FORBIDDEN_KEYS:
                raise EgressViolation(
                    f"forbidden key '{key}' at {path or 'top level'} (looks like raw data)"
                )
            params += _walk(item, f"{path}.{key}" if path else key, depth + 1, limit)
    elif isinstance(value, (list, tuple)):
        if len(value) > limit:
            raise EgressViolation(
                f"list '{path}' has {len(value)} items; max is {limit} "
                f"(len(FEATURE_NAMES)+1) — that is more than one weight vector"
            )
        for i, item in enumerate(value):
            if isinstance(item, bool):
                continue
            if isinstance(item, (int, float)):
                params += 1
            else:
                params += _walk(item, f"{path}[{i}]", depth + 1, limit)
    return params


def validate(payload: Any) -> tuple[bytes, int, list[str]]:
    """Return ``(body, params_shared, top_level_keys)`` or raise EgressViolation.

    ``body`` is the exact compact JSON that will be sent, so its sha256 is the
    sha256 of what crossed the wire.
    """
    if not isinstance(payload, dict):
        raise EgressViolation(f"payload must be a dict, got {type(payload).__name__}")
    params = _walk(payload, "", 0, max_list_len())
    try:
        body = json.dumps(payload, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise EgressViolation(
            f"payload is not plain JSON ({exc}); convert numpy arrays with .tolist()"
        ) from exc
    if len(body) > MAX_BYTES:
        raise EgressViolation(f"payload is {len(body)} bytes; max is {MAX_BYTES}")
    return body, params, [str(k) for k in payload]


# --------------------------------------------------------------------------- #
# audit log
# --------------------------------------------------------------------------- #
def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="milliseconds")


def _append(logs_dir: Path, bank_id: Any, record: dict) -> None:
    logs_dir.mkdir(parents=True, exist_ok=True)
    path = logs_dir / f"bank_{bank_id}.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, separators=(",", ":")) + "\n")


def _update_url(coordinator_url: str) -> str:
    url = coordinator_url.rstrip("/")
    return url if url.endswith("/update") else url + "/update"


# --------------------------------------------------------------------------- #
# the door
# --------------------------------------------------------------------------- #
def send(coordinator_url: str, payload: dict, bank_id: Any, round: int, *,
         logs_dir: str | os.PathLike | None = None,
         timeout: float = REQUEST_TIMEOUT_S) -> dict:
    """Validate, audit-log and POST one model update; return the JSON reply.

    Raises :class:`EgressViolation` (after logging a ``blocked`` line) when the
    payload must not leave the bank, and ``requests.RequestException`` when the
    coordinator cannot be reached (logged as ``send_failed``).
    """
    round_no = round
    logs = Path(logs_dir) if logs_dir is not None else DEFAULT_LOGS_DIR
    attempted_keys = [str(k) for k in payload] if isinstance(payload, dict) else []
    try:
        body, params, keys = validate(payload)
    except EgressViolation as exc:
        try:
            nbytes: int | None = len(json.dumps(payload, default=str).encode("utf-8"))
        except Exception:
            nbytes = None
        _append(logs, bank_id, {
            "ts": _now(), "bank_id": bank_id, "round": round_no, "kind": "blocked",
            "reason": str(exc), "bytes": nbytes, "keys": attempted_keys,
            "rows_shared": 0, "params_shared": 0,
        })
        log.error("bank %s round %s: egress BLOCKED — %s", bank_id, round_no, exc)
        raise

    digest = hashlib.sha256(body).hexdigest()
    _append(logs, bank_id, {
        "ts": _now(), "bank_id": bank_id, "round": round_no, "kind": "model_update",
        "bytes": len(body), "sha256": digest, "keys": keys,
        "rows_shared": 0, "params_shared": params,
    })
    log.info("bank %s round %s: sending %d params, %d bytes, rows_shared=0",
             bank_id, round_no, params, len(body))

    url = _update_url(coordinator_url)
    try:
        resp = requests.post(url, data=body, timeout=timeout,
                             headers={"Content-Type": "application/json"})
        resp.raise_for_status()
    except requests.RequestException as exc:
        _append(logs, bank_id, {
            "ts": _now(), "bank_id": bank_id, "round": round_no, "kind": "send_failed",
            "sha256": digest, "error": str(exc)[:300],
        })
        log.error("bank %s round %s: POST %s failed: %s", bank_id, round_no, url, exc)
        raise
    try:
        return resp.json()
    except ValueError:
        return {"status_code": resp.status_code, "text": resp.text[:500]}


# --------------------------------------------------------------------------- #
# reading the audit trail
# --------------------------------------------------------------------------- #
def iter_records(logs_dir: str | os.PathLike | None = None) -> Iterator[dict]:
    """Yield every parseable audit record from ``bank_*.jsonl`` (bad lines skipped)."""
    logs = Path(logs_dir) if logs_dir is not None else DEFAULT_LOGS_DIR
    if not logs.is_dir():
        return
    for path in sorted(logs.glob("bank_*.jsonl")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict):
                yield rec


_COUNTERS = ("messages", "bytes", "params_shared", "rows_shared", "blocked", "send_failed")


def summarize(logs_dir: str | os.PathLike | None = None) -> dict:
    """Per-bank and total egress counters.

    ``{"per_bank": {id: {"messages","bytes","params_shared","rows_shared",
    "blocked","send_failed","last_ts"}}, "totals": {...}}``
    """
    per_bank: dict[str, dict] = {}
    for rec in iter_records(logs_dir):
        bid = str(rec.get("bank_id"))
        entry = per_bank.setdefault(bid, {k: 0 for k in _COUNTERS} | {"last_ts": None})
        kind = rec.get("kind")
        if kind == "model_update":
            entry["messages"] += 1
            entry["bytes"] += int(rec.get("bytes") or 0)
            entry["params_shared"] += int(rec.get("params_shared") or 0)
            entry["rows_shared"] += int(rec.get("rows_shared") or 0)
        elif kind == "blocked":
            entry["blocked"] += 1
        elif kind == "send_failed":
            entry["send_failed"] += 1
        ts = rec.get("ts")
        if isinstance(ts, str) and (entry["last_ts"] is None or ts > entry["last_ts"]):
            entry["last_ts"] = ts
    totals = {k: sum(e[k] for e in per_bank.values()) for k in _COUNTERS}
    totals["banks"] = len(per_bank)
    return {"per_bank": dict(sorted(per_bank.items())), "totals": totals}


def tail(logs_dir: str | os.PathLike | None = None, n: int = 10) -> list[dict]:
    """The last ``n`` audit records across all banks, oldest first."""
    recs = [r for r in iter_records(logs_dir) if isinstance(r.get("ts"), str)]
    recs.sort(key=lambda r: r["ts"])
    return recs[-n:]


def _main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Print the egress audit summary.")
    ap.add_argument("--logs-dir", default=str(DEFAULT_LOGS_DIR))
    ap.add_argument("--tail", type=int, default=0, help="also print the last N lines")
    args = ap.parse_args(argv)
    out = summarize(args.logs_dir)
    if args.tail:
        out["tail"] = tail(args.logs_dir, args.tail)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    _main()
