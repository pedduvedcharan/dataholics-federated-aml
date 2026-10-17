"""Facts, glossary and template sentences for a SAR. Pure Python, always works.

The *facts* dict holds every number and identifier that may appear in a SAR. Both engines
read it: the template engine prints the values; the LLM engine only ever sees the
placeholder names (``[SENDER]``, ``[TOTAL_AMT]`` ...) and code substitutes the values
afterwards. That is how "LLM narrates, model decides" is enforced rather than hoped for.
"""
from __future__ import annotations

import re

# feature name -> (plain-English one-liner, what a positive contribution means)
FEATURE_GLOSSARY: dict[str, tuple[str, str]] = {
    "log_amt": ("log of the amount paid", "the amount is large for this model"),
    "is_usd": ("payment currency is US Dollar", "USD-denominated transfer"),
    "cur_mismatch": ("payment and receiving currency differ", "cross-currency transfer"),
    "same_bank": ("sender and receiver at the same bank", "an in-house transfer"),
    "round_amt": ("amount is a round multiple of 100", "a round-amount transfer"),
    "hour_sin": ("time of day (sine)", "unusual time of day"),
    "hour_cos": ("time of day (cosine)", "unusual time of day"),
    "dow_sin": ("day of week (sine)", "unusual day of week"),
    "dow_cos": ("day of week (cosine)", "unusual day of week"),
    "fmt_ach": ("payment format ACH", "ACH payment"),
    "fmt_credit_card": ("payment format Credit Card", "card payment"),
    "fmt_cheque": ("payment format Cheque", "cheque payment"),
    "fmt_wire": ("payment format Wire", "wire transfer"),
    "fmt_reinvestment": ("payment format Reinvestment", "reinvestment"),
    "fmt_bitcoin": ("payment format Bitcoin", "crypto-currency payment"),
    "fmt_cash": ("payment format Cash", "cash payment"),
    "snd_txn_cnt_log": ("log of the sender's transaction count at its bank",
                        "the sender transacts very frequently"),
    "snd_uniq_rcv_log": ("log of the sender's number of distinct receivers",
                         "the sender pays many different counterparties (fan-out)"),
    "rcv_in_deg_log": ("log of the receiver's incoming transaction count",
                       "the receiver collects from many payers (fan-in)"),
    "snd_amt_mean_log": ("log of the sender's mean amount paid", "the sender's typical amount is high"),
}


def glossary(name: str) -> tuple[str, str]:
    """Look up a feature by name, tolerant to case and spaces (``fmt_Credit Card``)."""
    key = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return FEATURE_GLOSSARY.get(key, (name, f"{name} is high"))


def _fmt_amt(v: float | None) -> str:
    return f"{v:,.2f}" if isinstance(v, (int, float)) else "n/a"


def extract_facts(alert: dict, model: dict | None = None) -> dict[str, str]:
    """Flatten an alert into the placeholder -> value map used by both engines."""
    trig = alert["trigger"]
    rows = alert["rows"]
    receivers = {str(r["to_acct"]) for r in rows if r.get("role") in ("trigger", "sender_other")}
    ts = sorted(str(r["ts"]) for r in rows if r.get("ts"))
    cs = alert.get("chain_summary", {})
    return {
        "ALERT_ID": str(alert["alert_id"]),
        "SENDER": str(trig["from_acct"]),
        "RECEIVER": str(trig["to_acct"]),
        "SENDER_BANK": str(trig["from_bank"]),
        "RECEIVER_BANK": str(trig["to_bank"]),
        "AMT": _fmt_amt(trig.get("amt_paid")),
        "CUR": str(trig.get("cur_paid")),
        "FMT": str(trig.get("fmt")),
        "TS": str(trig.get("ts")),
        "TS_FIRST": ts[0] if ts else "n/a",
        "TS_LAST": ts[-1] if ts else "n/a",
        "N_ROWS": str(cs.get("n_rows", len(rows))),
        "TOTAL_AMT": _fmt_amt(cs.get("total_amt_paid")),
        "N_SENDER_OTHER": str(cs.get("sender_other_txns", 0)),
        "N_RECEIVER_ONWARD": str(cs.get("receiver_onward_txns", 0)),
        "N_DISTINCT_RECEIVERS": str(len(receivers)),
        "BANKS": ", ".join(str(b) for b in alert.get("banks_involved", [])),
        "N_BANKS": str(cs.get("n_banks", len(alert.get("banks_involved", [])))),
        "SCORE": f"{float(alert['score']):.4f}",
        "SCORE_PCT": f"{100 * float(alert['score']):.1f}%",
        "RANK": str(alert.get("rank", "")),
        "MODEL_SHA": str(alert.get("model_sha256") or (model or {}).get("sha256") or "unknown"),
        "MODEL_ROUND": str(alert.get("model_round") or (model or {}).get("round") or "final"),
    }


def fill_placeholders(text: str, facts: dict[str, str]) -> str:
    """Replace ``[NAME]`` tokens with values; unknown tokens are left as-is for the post-check."""
    return re.sub(r"\[([A-Z_]+)\]", lambda m: facts.get(m.group(1), m.group(0)), text)


def indicator_lines(alert: dict) -> list[str]:
    """One qualitative line per top feature, suitable for the LLM (no raw values)."""
    out = []
    for f in alert.get("top_features", []):
        desc, meaning = glossary(f["name"])
        direction = "raises" if f.get("contribution", 0) > 0 else "lowers"
        out.append(f"{desc}: {meaning}; this {direction} the laundering score")
    return out


def template_sections(alert: dict, facts: dict[str, str]) -> dict[str, str]:
    """Template engine: the three prose sections, filled from facts and top features."""
    summary = (
        "Account [SENDER] at bank [SENDER_BANK] paid [AMT] [CUR] by [FMT] to account [RECEIVER] "
        "at bank [RECEIVER_BANK] on [TS]. In the regulator's held-out sample the sender made "
        "[N_SENDER_OTHER] other payments to [N_DISTINCT_RECEIVERS] distinct receivers and the receiver "
        "moved funds onward in [N_RECEIVER_ONWARD] payments. The chain of [N_ROWS] transactions reviewed "
        "here totals [TOTAL_AMT] and touches [N_BANKS] institution(s) (bank ids [BANKS]). The federated "
        "model scored the trigger transaction [SCORE] (rank [RANK] of the sample)."
    )
    bullets = []
    for f in alert.get("top_features", []):
        desc, meaning = glossary(f["name"])
        sign = "+" if f.get("contribution", 0) >= 0 else ""
        bullets.append(f"- **{f['name']}** ({desc}): {meaning}; contribution {sign}{f['contribution']:.3f}.")
    indicators = "\n".join(bullets) if bullets else "- No single dominant indicator; the score is spread across features."
    action = (
        "Place a review hold on account [SENDER] at bank [SENDER_BANK] and request the account-opening "
        "and source-of-funds records. Send a 314(b)-style information request to the other institutions "
        "in the chain (bank ids [BANKS]) about account [RECEIVER] and its onward payments. If the pattern is "
        "confirmed, file a Suspicious Activity Report within the statutory window and retain this model "
        "attribution as the audit trail."
    )
    return {
        "summary": fill_placeholders(summary, facts),
        "pattern_indicators": indicators,
        "recommended_action": fill_placeholders(action, facts),
    }
