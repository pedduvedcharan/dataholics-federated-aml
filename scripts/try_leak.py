#!/usr/bin/env python3
"""Demo hook: try to push five raw transaction rows through the egress door.

The egress function must refuse, log a ``blocked`` line in
``logs/egress/bank_<id>.jsonl`` and the dashboard's "Blocked attempts" counter
must tick up.  Exit code 0 means the leak was blocked (good); 1 means it got
through (bad).

    python scripts/try_leak.py [--bank-id 1] [--coordinator http://localhost:8000]
                               [--variant rows|nested|oversize]

The rows are synthetic and shaped like the IBM AML dataset after INFRA's
column rename; no real data is involved.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root

from fedaml import egress  # noqa: E402

RAW_ROWS = [
    {"ts": "2022-09-01 00:02:00", "from_bank": 10, "from_acct": "8000EBD30",
     "to_bank": 10, "to_acct": "8000EBD30", "amt_recv": 3697.34, "cur_recv": "US Dollar",
     "amt_paid": 3697.34, "cur_paid": "US Dollar", "fmt": "Reinvestment", "is_laundering": 0},
    {"ts": "2022-09-01 00:04:00", "from_bank": 3208, "from_acct": "8000F4580",
     "to_bank": 1, "to_acct": "8000F5340", "amt_recv": 0.01, "cur_recv": "US Dollar",
     "amt_paid": 0.01, "cur_paid": "US Dollar", "fmt": "Cheque", "is_laundering": 0},
    {"ts": "2022-09-01 00:06:00", "from_bank": 3209, "from_acct": "8000F4670",
     "to_bank": 3209, "to_acct": "8000F4670", "amt_recv": 14675.57, "cur_recv": "US Dollar",
     "amt_paid": 14675.57, "cur_paid": "US Dollar", "fmt": "Reinvestment", "is_laundering": 0},
    {"ts": "2022-09-01 00:08:00", "from_bank": 12, "from_acct": "8000F5030",
     "to_bank": 12, "to_acct": "8000F5030", "amt_recv": 2806.97, "cur_recv": "US Dollar",
     "amt_paid": 2806.97, "cur_paid": "US Dollar", "fmt": "Reinvestment", "is_laundering": 0},
    {"ts": "2022-09-01 00:09:00", "from_bank": 11, "from_acct": "8000F5200",
     "to_bank": 11, "to_acct": "8000F5200", "amt_recv": 36682.97, "cur_recv": "US Dollar",
     "amt_paid": 36682.97, "cur_paid": "US Dollar", "fmt": "Reinvestment", "is_laundering": 1},
]


def build_payload(variant: str, bank_id: int, round_no: int) -> dict:
    """Three ways a careless (or malicious) bank might try to leak rows."""
    base = {"bank_id": bank_id, "round": round_no, "n_samples": 5}
    if variant == "rows":            # the obvious one: a 'rows' key
        return base | {"rows": RAW_ROWS}
    if variant == "nested":          # hide the columns one level down
        return base | {"delta_coef": [0.0] * 5, "extra": {"batch": RAW_ROWS}}
    if variant == "oversize":        # no forbidden key, but far too many numbers
        return base | {"delta_coef": [r["amt_paid"] for r in RAW_ROWS] * 50}
    raise SystemExit(f"unknown variant {variant}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bank-id", type=int, default=1)
    ap.add_argument("--round", type=int, default=0)
    ap.add_argument("--coordinator", default="http://localhost:8000")
    ap.add_argument("--variant", choices=["rows", "nested", "oversize"], default="rows")
    ap.add_argument("--logs-dir", default=None, help="default: logs/egress")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    payload = build_payload(args.variant, args.bank_id, args.round)
    print(f"[try_leak] bank {args.bank_id}: attempting to send {len(RAW_ROWS)} raw rows "
          f"(variant={args.variant}) through egress.send ...")
    try:
        reply = egress.send(args.coordinator, payload, args.bank_id, args.round,
                            logs_dir=args.logs_dir)
    except egress.EgressViolation as exc:
        print(f"[try_leak] BLOCKED by egress: {exc}")
        last = egress.tail(args.logs_dir, 1)
        if last:
            print(f"[try_leak] audit line: {last[-1]}")
        return 0
    except Exception as exc:  # network error means it passed validation: still a leak
        print(f"[try_leak] NOT BLOCKED (validation passed, POST failed: {exc})")
        return 1
    print(f"[try_leak] NOT BLOCKED — coordinator replied {reply}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
