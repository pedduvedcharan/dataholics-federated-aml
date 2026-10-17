"""``python -m fedaml.dashboard --port 8050`` — serve the regulator view.

Binds 127.0.0.1 on a workstation; inside a container (``/.dockerenv`` present)
it binds 0.0.0.0 so compose can publish it on the VM's 127.0.0.1:8050.  From
the Mac: ``ssh -L 8050:localhost:8050 dataholics`` then http://localhost:8050.
"""
from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from fedaml.dashboard import (DEFAULT_EPS_BUDGET, DEFAULT_LOGS_DIR, DEFAULT_STATE_DIR,
                              create_app)


def _default_host() -> str:
    if os.environ.get("DASHBOARD_HOST"):
        return os.environ["DASHBOARD_HOST"]
    return "0.0.0.0" if Path("/.dockerenv").exists() else "127.0.0.1"


def main() -> None:
    ap = argparse.ArgumentParser(description="Regulator dashboard for fedaml.")
    ap.add_argument("--port", type=int, default=8050)
    ap.add_argument("--host", default=_default_host(),
                    help="default 127.0.0.1, or 0.0.0.0 inside a container")
    ap.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    ap.add_argument("--logs-dir", default=str(DEFAULT_LOGS_DIR))
    ap.add_argument("--eps-budget", type=float, default=DEFAULT_EPS_BUDGET,
                    help="privacy budget shown on the meter (default 8)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    logging.getLogger("werkzeug").setLevel(logging.WARNING)  # one line per poll is noise
    app = create_app(Path(args.state_dir), Path(args.logs_dir), args.eps_budget)
    logging.getLogger("fedaml.dashboard").info(
        "serving on http://%s:%d  state=%s logs=%s", args.host, args.port,
        args.state_dir, args.logs_dir)
    app.run(host=args.host, port=args.port, debug=False, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
