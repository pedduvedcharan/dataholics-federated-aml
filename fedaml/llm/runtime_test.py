"""Runtime benchmark: time a 100-token generation and write ``state/llm_runtime.json``.

    python -m fedaml.llm.runtime_test --tokens 100 --out state/llm_runtime.json

Every number in docs/GENAI.md about speed comes from this file.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import sys
import tempfile
import time

from fedaml.llm.client import LlamaClient, LLMUnavailable

log = logging.getLogger("fedaml.llm.runtime_test")

SYSTEM = "You are a concise financial-crime compliance analyst."
USER = ("In about 120 words, explain to a bank compliance officer why a customer who sends many "
        "round-amount wire transfers to many different receivers in a short period may warrant review.")


def write_json_atomic(path: str, obj: dict) -> None:
    """Write JSON to a temp file in the same directory, then rename (CONTRACTS §6)."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(obj, f, indent=2)
    os.chmod(tmp, 0o644)  # mkstemp creates 0600; dashboard and host readers need read access
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tokens", type=int, default=100)
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--out", default="state/llm_runtime.json")
    ap.add_argument("--runs", type=int, default=1)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    client = LlamaClient()
    result: dict = {
        "arch": platform.machine(),
        "engine": "llama.cpp llama-server",
        "model_path": os.environ.get("LLM_MODEL_PATH"),
        "url": client.url,
        "threads": int(os.environ.get("LLM_THREADS", "3")),
        "requested_tokens": args.tokens,
        "runs": [],
        "verdict": "template",
    }
    t_start = time.time()
    if not client.ensure_server(wait_s=120):
        result["error"] = "no llama-server reachable or spawnable"
        write_json_atomic(args.out, result)
        log.error("verdict: template (no server)")
        return 1
    result["server_startup_s"] = round(time.time() - t_start, 2)
    try:
        for i in range(args.runs):
            r = client.chat(SYSTEM, USER, max_tokens=args.tokens, temperature=0.2, timeout=args.timeout)
            run = {"run": i, "model": r.model, "prompt_tokens": r.prompt_tokens,
                   "completion_tokens": r.completion_tokens, "seconds": round(r.seconds, 2),
                   "tokens_per_second": round(r.tokens_per_second, 2),
                   "sample": r.text[:300]}
            result["runs"].append(run)
            log.info("run %d: %d tokens in %.1fs = %.2f tok/s", i, r.completion_tokens, r.seconds,
                     r.tokens_per_second)
    except LLMUnavailable as e:
        result["error"] = str(e)
        write_json_atomic(args.out, result)
        log.error("verdict: template (%s)", e)
        return 1
    finally:
        client.stop()
    tps = [x["tokens_per_second"] for x in result["runs"]]
    result["tokens_per_second_mean"] = round(sum(tps) / len(tps), 2) if tps else 0.0
    result["verdict"] = "llm"
    write_json_atomic(args.out, result)
    log.info("verdict: llm, %.2f tok/s, written to %s", result["tokens_per_second_mean"], args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
