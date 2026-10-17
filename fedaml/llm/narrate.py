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
    "square brackets, exactly as written. Output must be a single JSON object and nothing else."
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
        '{"summary": "<2-4 sentences describing the activity using the tokens>",\n'
        ' "pattern_indicators": ["<one sentence per indicator above, in plain English>", ...],\n'
        ' "recommended_action": "<2-3 sentences of concrete next steps for the compliance officer>"}'
    )


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
        out[key] = str(v).strip()
        if not out[key]:
            raise ValueError(f"LLM output has empty {key!r}")
    return out
