"""Suspicious Activity Report writer (GENAI). CONTRACTS §7:

    python -m fedaml.sar --alert-id A01 [--engine llm|template] [--all]

Outline (fixed): Subject, Summary of activity, Pattern indicators, Institutions involved,
Recommended action, Model attribution. Code writes every section from the alert record; the LLM
adds one "Analyst assessment" paragraph to the summary explaining why the pattern is suspicious,
from qualitative facts only (it never sees an account id or amount). Guardrails:
max 400 tokens, temperature 0.2, 60 s timeout, then automatic template fallback noted in the
footer; any account-like token in the output that is not in the alert JSON forces the fallback.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import re
import sys
import time

from fedaml.llm.client import LlamaClient, LLMUnavailable
from fedaml.llm.facts import extract_facts, fill_placeholders, glossary, template_sections
from fedaml.llm.narrate import SYSTEM_PROMPT, build_user_prompt, parse_response

log = logging.getLogger("fedaml.sar")

INSTRUCTION_ECHO = re.compile(r"under \d+ words|in your own words|\(\d+ sentences|one sentence per|"
                              r"next steps for the officer|return json", re.I)
ACCOUNT_LIKE = re.compile(r"\b(?=[0-9A-Fa-f]*[A-Fa-f])[0-9A-Fa-f]{6,}\b|\b\d{7,}\b")


def load_alerts(path: str) -> list[dict]:
    """Read state/alerts.json: ``{"meta", "alerts"}`` or a bare list (older format)."""
    with open(path) as f:
        data = json.load(f)
    return data["alerts"] if isinstance(data, dict) else data


def find_alert(alerts: list[dict], alert_id: str) -> dict:
    """Return the alert with ``alert_id`` or raise ``KeyError`` listing the valid ids."""
    for a in alerts:
        if str(a["alert_id"]) == alert_id:
            return a
    raise KeyError(f"alert {alert_id!r} not found; valid ids: {[a['alert_id'] for a in alerts]}")


def check_account_ids(text: str, alert: dict) -> list[str]:
    """Return account-like tokens in ``text`` that do not belong to the alert (empty = pass)."""
    allowed = {str(a).lower() for a in alert.get("accounts", [])}
    allowed |= {str(b).lower() for b in alert.get("banks_involved", [])}
    for r in alert.get("rows", []):  # bank codes in real data are long digit strings ("0118180")
        allowed |= {str(r.get(k)).lower() for k in ("from_bank", "to_bank", "from_acct", "to_acct")}
    allowed |= {str(alert.get("model_sha256") or "").lower()}
    bad = []
    for tok in ACCOUNT_LIKE.findall(text):
        t = tok.lower()
        if t in allowed or any(t in a for a in allowed if len(a) >= 40):
            continue
        bad.append(tok)
    return sorted(set(bad))


NUMBER_WORDS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten".split())}
COUNTED = re.compile(r"\b(\d+|zero|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:\w+\s+){0,2}?"
                     r"(payments?|transactions?|accounts?|receivers?|counterpart(?:y|ies)|institutions?|banks?|"
                     r"payers?|transfers?)\b", re.I)


OTHER_PAYMENTS = re.compile(r"\b(\d+|zero|one|two|three|four|five|six|seven|eight|nine|ten)\s+other\s+"
                            r"(?:payments?|transactions?|transfers?)\b", re.I)


def allowed_counts(alert: dict, facts: dict[str, str]) -> set[int]:
    """Every count the code-written sections state: chain counts plus decoded count features."""
    from fedaml.llm.facts import feature_fact

    nums = {int(facts[k]) for k in ("N_SENDER_OTHER", "N_DISTINCT_RECEIVERS", "N_RECEIVER_ONWARD", "N_ROWS", "N_BANKS")
            if str(facts.get(k, "")).isdigit()}
    for f in alert.get("top_features", []):
        nums |= {int(x) for x in re.findall(r"\b\d+\b", feature_fact(f))}
    return nums | {1}  # "one payment" = the trigger itself


def drop_unsupported_counts(text: str, alert: dict, facts: dict[str, str]) -> str:
    """Remove LLM sentences that state a count the facts do not contain (e.g. 'two other payments' when 1)."""
    ok = allowed_counts(alert, facts)
    kept = []
    for sent in re.split(r"(?<=[.!?])\s+", text):
        found = [m.group(1).lower() for m in COUNTED.finditer(sent)]
        vals = [int(x) if x.isdigit() else NUMBER_WORDS[x] for x in found]
        other = [m.group(1).lower() for m in OTHER_PAYMENTS.finditer(sent)]
        other_bad = any((int(x) if x.isdigit() else NUMBER_WORDS[x]) != int(facts.get("N_SENDER_OTHER", -1))
                        for x in other)
        if other_bad or any(v not in ok for v in vals):
            log.info("dropped LLM sentence with unsupported count %s: %s", vals, sent[:120])
            continue
        kept.append(sent)
    return " ".join(kept).strip()


def llm_sections(alert: dict, facts: dict[str, str], *, max_tokens: int, temperature: float,
                 timeout: float, seed: int) -> tuple[dict[str, str], dict]:
    """Code writes the facts; the LLM adds one assessment paragraph. Raises on any guardrail failure."""
    client = LlamaClient()
    if not client.ensure_server():
        raise LLMUnavailable(f"no llama-server reachable at {client.url}")
    try:
        res = client.chat(SYSTEM_PROMPT, build_user_prompt(alert), max_tokens=max_tokens,
                          temperature=temperature, timeout=timeout, seed=seed)
    finally:
        client.stop()
    text = drop_unsupported_counts(fill_placeholders(parse_response(res.text)["assessment"], facts), alert, facts)
    leftover = sorted(set(re.findall(r"\[[A-Z_]+\]", text)))
    if leftover:
        raise ValueError(f"unknown placeholders in LLM output: {leftover}")
    if INSTRUCTION_ECHO.search(text):
        raise ValueError("LLM echoed the prompt instructions")
    if len(text.split()) < 25:
        raise ValueError(f"LLM assessment too short ({len(text.split())} words)")
    bad = check_account_ids(text, alert)
    if bad:
        raise ValueError(f"LLM output contains account-like tokens not in the alert: {bad}")
    tmpl = template_sections(alert, facts)
    sections = dict(tmpl, summary=f"{tmpl['summary']}\n\n**Analyst assessment (LLM).** {text}")
    meta = {"model": res.model, "seconds": round(res.seconds, 2), "completion_tokens": res.completion_tokens,
            "prompt_tokens": res.prompt_tokens, "tokens_per_second": round(res.tokens_per_second, 2),
            "assessment_words": len(text.split())}
    return sections, meta


def institutions_table(alert: dict) -> str:
    """Code-generated table: one row per bank code in the chain with its role and row count."""
    lines = ["| Bank code | Federation label | Role | Chain rows touching it |", "|---|---|---|---|"]
    insts = alert.get("institutions")
    if not insts:  # older alerts.json without the institutions list
        trig = alert["trigger"]
        insts = [{"code": b, "label": None, "rows": sum(1 for r in alert["rows"] if b in (str(r["from_bank"]), str(r["to_bank"]))),
                  "role": ", ".join(x for x, ok in (("sender's bank", b == str(trig["from_bank"])),
                                                    ("receiver's bank", b == str(trig["to_bank"]))) if ok) or "counterparty / downstream"}
                 for b in alert.get("banks_involved", [])]
    for i in insts:
        lines.append(f"| {i['code']} | {i.get('label') or 'outside the federation'} | {i['role']} | {i['rows']} |")
    return "\n".join(lines)


def attribution_table(alert: dict) -> str:
    lines = ["| Feature | Meaning | Value | Weight | Contribution |", "|---|---|---|---|---|"]
    for f in alert.get("top_features", []):
        desc, _ = glossary(f["name"])
        lines.append(f"| `{f['name']}` | {desc} | {f['value']:.4f} | {f['weight']:+.4f} | {f['contribution']:+.4f} |")
    return "\n".join(lines)


def render(alert: dict, facts: dict[str, str], sections: dict[str, str], footer: dict) -> str:
    """Assemble the markdown SAR in the fixed outline."""
    chain = ["| ts | from bank | from acct | to bank | to acct | amount | cur | format | role |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in alert["rows"]:
        chain.append(f"| {r.get('ts')} | {r['from_bank']} | {r['from_acct']} | {r['to_bank']} | {r['to_acct']} | "
                     f"{(r.get('amt_paid') or 0):,.2f} | {r.get('cur_paid')} | {r.get('fmt')} | {r.get('role', '')} |")
    label = ("trigger labelled laundering in the synthetic data" if int(alert["trigger"].get("is_laundering") or 0) == 1
             else "trigger not labelled laundering in the synthetic data")
    gen_note = (f"LLM engine ({os.path.basename(str(footer['model']))}), {footer['seconds']} s, "
                f"{footer['completion_tokens']} tokens"
                if footer["engine"] == "llm" else
                f"template engine" + (f" (fallback: {footer['fallback_reason']})" if footer.get("fallback_reason") else ""))
    return f"""# Suspicious Activity Report — alert {facts['ALERT_ID']}

## Subject
Account **{facts['SENDER']}** (bank {facts['SENDER_BANK']}) → account **{facts['RECEIVER']}** (bank {facts['RECEIVER_BANK']}), {facts['AMT']} {facts['CUR']} by {facts['FMT']} on {facts['TS']}. Federated model score {facts['SCORE']}, rank {facts['RANK']} in the queue ranked for analyst review.

## Summary of activity
{sections['summary']}

## Pattern indicators
{sections['pattern_indicators']}

## Institutions involved
{institutions_table(alert)}

Chain reviewed ({facts['N_ROWS']} rows, regulator-side held-out sample; synthetic IBM AML data):

{chr(10).join(chain)}

## Recommended action
{sections['recommended_action']}

## Model attribution
- Global model sha256: `{facts['MODEL_SHA']}` (round {facts['MODEL_ROUND']}), trained by federated averaging; no raw transaction left any bank.
- Score for the trigger transaction: {facts['SCORE']}, rank {facts['RANK']} in the filtered review queue.
- Ground truth (not known to any bank or to the model): **{label}**.
- Top feature contributions (value × weight):

{attribution_table(alert)}

---
*Generated {footer['generated_at']} by `fedaml.sar` using the {gen_note}. Ground truth: {label}. This alert was ranked for analyst review; it is not a finding of laundering. The LLM narrates, the model decides: every fact, account id, amount, bank id and the model hash above were inserted by code from `state/alerts.json`; the language model wrote only the paragraph marked "Analyst assessment (LLM)" and never saw an account id or amount. Account ids were checked against the alert record. Data are synthetic (IBM AML HI-Small); no real persons are described.*
"""


def write_sar(alert: dict, model: dict | None, engine: str, out_dir: str, *, max_tokens: int = 400,
              temperature: float = 0.2, timeout: float = 60.0, seed: int = 42) -> tuple[str, dict]:
    """Generate one SAR, write ``<out_dir>/<alert_id>.md``, return (path, footer)."""
    facts = extract_facts(alert, model)
    footer: dict = {"engine": "template", "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    sections: dict[str, str] | None = None
    if engine == "llm":
        t0 = time.time()
        try:
            sections, meta = llm_sections(alert, facts, max_tokens=max_tokens, temperature=temperature,
                                          timeout=timeout, seed=seed)
            footer.update(engine="llm", **meta)
        except (LLMUnavailable, ValueError, KeyError, json.JSONDecodeError) as e:
            footer["fallback_reason"] = f"{type(e).__name__}: {e}"[:200]
            footer["llm_seconds_before_fallback"] = round(time.time() - t0, 2)
            log.warning("LLM engine failed after %.1fs, falling back to template: %s", time.time() - t0, e)
    if sections is None:
        sections = template_sections(alert, facts)
    text = render(alert, facts, sections, footer)
    bad = check_account_ids(text, alert)
    if bad:  # cannot happen for the template, but never ship an unverified id
        raise RuntimeError(f"post-check failed on final document: {bad}")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{alert['alert_id']}.md")
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)
    log.info("wrote %s (engine=%s%s)", path, footer["engine"],
             f", fallback: {footer['fallback_reason']}" if footer.get("fallback_reason") else "")
    return path, footer


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write a SAR for a flagged chain")
    ap.add_argument("--alert-id", help="e.g. A01, or 'demo' for meta.demo_alert_id; see --list")
    ap.add_argument("--all", action="store_true", help="generate for every alert")
    ap.add_argument("--list", action="store_true", help="print alert ids and scores and exit")
    ap.add_argument("--engine", choices=["llm", "template"], default="llm")
    ap.add_argument("--alerts", default="state/alerts.json")
    ap.add_argument("--model", default="state/global_final.json")
    ap.add_argument("--out-dir", default="state/sar")
    ap.add_argument("--max-tokens", type=int, default=400)
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--timeout", type=float, default=60.0)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    alerts = load_alerts(args.alerts)
    if args.list:
        for a in alerts:
            lab = int(a["trigger"].get("is_laundering") or 0)
            print(f"{a['alert_id']}  score={a['score']:.4f}  laundering={lab}  banks={a['banks_involved']}  "
                  f"rows={len(a['rows'])}")
        return 0
    model = None
    if os.path.exists(args.model):
        with open(args.model) as f:
            model = json.load(f)
    if args.alert_id == "demo":
        with open(args.alerts) as f:
            data = json.load(f)
        args.alert_id = (data.get("meta", {}) if isinstance(data, dict) else {}).get("demo_alert_id")
        if not args.alert_id:
            ap.error("alerts.json has no demo_alert_id (no labelled-laundering trigger after the filter)")
    targets = alerts if args.all else [find_alert(alerts, args.alert_id or "")]
    if not args.all and not args.alert_id:
        ap.error("--alert-id is required unless --all or --list")
    summary = []
    for a in targets:
        path, footer = write_sar(a, model, args.engine, args.out_dir, max_tokens=args.max_tokens,
                                 temperature=args.temperature, timeout=args.timeout, seed=args.seed)
        summary.append({"alert_id": a["alert_id"], "path": path, **footer})
    with open(os.path.join(args.out_dir, "_runs.jsonl"), "a") as f:
        for s in summary:
            f.write(json.dumps(s) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
