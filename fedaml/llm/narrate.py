"""Prompt construction and response parsing for the LLM engine.

The LLM never sees an account number, an amount, a bank id, or the model hash: the prompt
describes the case with placeholder tokens and qualitative indicator lines. It must return
JSON with three prose fields that reuse the tokens; code fills the values afterwards.
"""
from __future__ import annotations

import json
import logging
import re

from fedaml.llm.facts import indicator_lines

log = logging.getLogger("fedaml.llm.narrate")

SYSTEM_PROMPT = (
    "You are a senior anti-money-laundering compliance analyst writing the narrative of a "
    "Suspicious Activity Report. Write in formal, neutral English. Never state that a crime "
    "occurred; describe indicators and recommend review. You must not invent any account number, "
    "amount, date, bank name or statistic: refer to them ONLY with the placeholder tokens given in "
    "square brackets, exactly as written. Treat the transaction as high-risk: the cross-bank model ranked it "
    "among the most suspicious in the sample, and your recommendation is always to review it. Do not repeat "
    "sentences. Output must be a single JSON object and nothing else."
)

PLACEHOLDER_HELP = (
    "[SENDER] sender account, [RECEIVER] receiver account, [SENDER_BANK] sender's bank id, "
    "[RECEIVER_BANK] receiver's bank id, [AMT] trigger amount, [CUR] currency, [FMT] payment format, "
    "[TS] trigger timestamp, [N_SENDER_OTHER] number of other payments by the sender, "
    "[N_DISTINCT_RECEIVERS] distinct receivers paid by the sender, [N_RECEIVER_ONWARD] onward payments "
    "by the receiver, [N_ROWS] transactions in the chain, [TOTAL_AMT] total amount of the chain, "
    "[N_BANKS] number of institutions, [BANKS] list of bank ids, [SCORE] model score, [RANK] rank"
)


def build_user_prompt(alert: dict) -> str:
    """User turn: the case described with placeholders plus the qualitative indicators."""
    lines = indicator_lines(alert)
    indicators = "\n".join(f"- {s}" for s in lines) or "- no dominant indicator"
    return (
        "Case facts (use the tokens, not values):\n"
        "- Trigger: account [SENDER] at bank [SENDER_BANK] paid [AMT] [CUR] by [FMT] to account [RECEIVER] "
        "at bank [RECEIVER_BANK] on [TS].\n"
        "- Sender made [N_SENDER_OTHER] other payments to [N_DISTINCT_RECEIVERS] distinct receivers in the "
        "review sample; receiver made [N_RECEIVER_ONWARD] onward payments.\n"
        "- Chain reviewed: [N_ROWS] transactions, total [TOTAL_AMT], across [N_BANKS] institutions (bank ids [BANKS]).\n"
        "- The jointly trained cross-bank model scored the trigger [SCORE] (rank [RANK] of the sample).\n"
        f"Model indicators, strongest first:\n{indicators}\n\n"
        f"Token meanings: {PLACEHOLDER_HELP}.\n\n"
        "Return JSON with exactly these keys:\n"
        '{"summary": "Account [SENDER] at bank [SENDER_BANK] ... <3 sentences: what was paid to [RECEIVER] at bank '
        "[RECEIVER_BANK], what the sender and receiver did around it ([N_SENDER_OTHER], [N_DISTINCT_RECEIVERS], "
        '[N_RECEIVER_ONWARD]), and the size of the chain ([N_ROWS] transactions, [TOTAL_AMT], [N_BANKS] institutions)>",\n'
        ' "pattern_indicators": ["<one plain-English sentence per indicator above, for a compliance officer, '
        'in your own words>", ...],\n'
        ' "recommended_action": "<2-3 sentences of concrete next steps for the compliance officer at bank '
        '[SENDER_BANK], mentioning account [SENDER] and the other institutions [BANKS]>"}'
    )


def echoes_input(bullets: str, alert: dict) -> bool:
    """True when most LLM indicator bullets are verbatim copies of the prompt's indicator lines."""
    inputs = {_norm(x) for x in indicator_lines(alert)}
    outs = [_norm(b.lstrip("- ").strip()) for b in bullets.splitlines() if b.strip()]
    if not outs:
        return True
    copied = sum(1 for o in outs if o in inputs or any(o and (o in i or i in o) for i in inputs))
    return copied >= max(1, (len(outs) + 1) // 2)


def _norm(s: str) -> str:
    return re.sub(r"\W+", " ", s).strip().lower()


def parse_response(text: str) -> dict[str, str]:
    """Extract the JSON object; join list fields into markdown bullets. Raises ValueError."""
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        raise ValueError("no JSON object in LLM output")
    obj = json.loads(m.group(0))
    out: dict[str, str] = {}
    for key in ("summary", "pattern_indicators", "recommended_action"):
        v = obj.get(key)
        if v is None:
            raise ValueError(f"LLM output missing key {key!r}")
        if isinstance(v, list):
            v = "\n".join(f"- {str(x).strip()}" for x in v if str(x).strip())
        out[key] = _dedupe_sentences(str(v).strip())
        if not out[key]:
            raise ValueError(f"LLM output has empty {key!r}")
    for tok in ("[SENDER]", "[RECEIVER]"):
        if tok not in out["summary"]:
            raise ValueError(f"LLM summary does not reference {tok}")
    return out


def _dedupe_sentences(text: str) -> str:
    """Drop exact repeats of a sentence (small models loop); keeps order and bullets."""
    seen: set[str] = set()
    kept: list[str] = []
    for part in re.split(r"(?<=[.!?])\s+", text):
        key = re.sub(r"\W+", " ", part).strip().lower()
        if key and key in seen:
            continue
        seen.add(key)
        kept.append(part)
    return " ".join(kept).strip()
