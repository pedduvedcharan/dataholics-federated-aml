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

def build_user_prompt(alert: dict) -> str:
    """User turn: the case described with placeholders plus the qualitative indicators (kept short)."""
    lines = indicator_lines(alert)
    indicators = "\n".join(f"- {s}" for s in lines) or "- no dominant indicator"
    return (
        "Case (tokens stand for values; use them verbatim):\n"
        "- Account [SENDER] at bank [SENDER_BANK] paid [AMT] [CUR] by [FMT] to account [RECEIVER] at bank "
        "[RECEIVER_BANK] on [TS].\n"
        "- The sender made [N_SENDER_OTHER] other payments to [N_DISTINCT_RECEIVERS] receivers; the receiver made "
        "[N_RECEIVER_ONWARD] onward payments.\n"
        "- Chain: [N_ROWS] transactions, total [TOTAL_AMT], [N_BANKS] institutions (bank ids [BANKS]).\n"
        "- Cross-bank model score [SCORE], rank [RANK] in the sample.\n"
        f"Indicators, strongest first:\n{indicators}\n\n"
        "Return JSON only:\n"
        '{"summary": "Account [SENDER] at bank [SENDER_BANK] ... (3 sentences, under 70 words, mention [RECEIVER], '
        'the sender/receiver activity and the chain size)",\n'
        ' "pattern_indicators": ["one sentence under 15 words per indicator, in your own words", ...],\n'
        ' "recommended_action": "under 50 words: next steps for the officer at bank [SENDER_BANK] about account '
        '[SENDER] and the institutions [BANKS]"}'
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
    obj = _load_json_lenient(text)
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


def _load_json_lenient(text: str) -> dict:
    """Parse the first JSON object; if generation was cut off at max_tokens, try to close it."""
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object in LLM output")
    body = text[start:]
    end = body.rfind("}")
    candidates = [body[:end + 1]] if end > 0 else []
    stripped = body.rstrip().rstrip(",")
    candidates += [stripped + suffix for suffix in ('"}', '"]}', "}", "]}", '"}}')]
    for c in candidates:
        try:
            obj = json.loads(c)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    raise ValueError("unparseable or truncated JSON in LLM output")


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
