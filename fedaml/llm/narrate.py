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
    "sentences. Answer with the SUMMARY and ACTION paragraphs only."
)

EXAMPLE = (
    "SUMMARY: On [TS] account [SENDER] at bank [SENDER_BANK] sent [AMT] [CUR] by [FMT] to account [RECEIVER] at "
    "bank [RECEIVER_BANK]. The sender [SENDER_ACTIVITY], and the receiver [RECEIVER_ACTIVITY]. Taken together, the "
    "[N_ROWS] linked transactions worth [TOTAL_AMT] across [N_BANKS] institutions resemble funds being split and "
    "passed between banks so that no single bank sees the whole movement.\n"
    "ACTION: Escalate account [SENDER] for enhanced due diligence and obtain source-of-funds documentation. "
    "Request information from banks [BANKS] on account [RECEIVER] and preserve the records pending a filing decision."
)


def build_user_prompt(alert: dict) -> str:
    """User turn: placeholder facts, qualitative indicators, one example of the expected two-paragraph answer."""
    lines = indicator_lines(alert)
    indicators = "\n".join(f"- {s}" for s in lines) or "- no dominant indicator"
    return (
        "Facts (tokens in square brackets stand for real values; copy the tokens exactly):\n"
        "- On [TS] account [SENDER] at bank [SENDER_BANK] paid [AMT] [CUR] by [FMT] to account [RECEIVER] at bank "
        "[RECEIVER_BANK].\n"
        "- The sender [SENDER_ACTIVITY]. The receiver [RECEIVER_ACTIVITY].\n"
        "- Linked chain: [N_ROWS] transactions, [TOTAL_AMT] in total, [N_BANKS] institutions (banks [BANKS]).\n"
        "- The jointly trained cross-bank model ranks this transaction [RANK] of the sample.\n"
        f"Why the model flagged it, strongest reason first:\n{indicators}\n\n"
        "Write two short paragraphs in this exact format, explaining the reasons above in your own words:\n"
        "SUMMARY: <three or four sentences>\nACTION: <two sentences>\n\n"
        f"Example of the format for a different case:\n{EXAMPLE}"
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


def _labelled(text: str) -> dict | None:
    """Parse ``SUMMARY: ... ACTION: ...`` plain text; None if the labels are absent."""
    m = re.search(r"SUMMARY\s*:\s*(.+?)\s*(?:\n|^|\s)ACTION\s*:\s*(.+)", text, flags=re.S | re.I)
    if not m:
        return None
    action = re.split(r"\n\s*\n|\n\s*(?:Example|SUMMARY)\b", m.group(2).strip(), flags=re.I)[0]
    return {"summary": m.group(1).strip(), "recommended_action": action.strip(), "pattern_indicators": []}


def parse_response(text: str) -> dict[str, str]:
    """Parse labelled plain text (preferred) or a JSON object. Raises ValueError.

    ``pattern_indicators`` may be empty: code then supplies the indicator bullets.
    """
    obj = _labelled(text) or _load_json_lenient(text)
    out: dict[str, str] = {}
    for key in ("summary", "pattern_indicators", "recommended_action"):
        v = obj.get(key)
        if v is None or (key == "pattern_indicators" and not v):
            if key == "pattern_indicators":
                out[key] = ""
                continue
            raise ValueError(f"LLM output missing key {key!r}")
        if isinstance(v, list):
            v = "\n".join(f"- {str(x).strip()}" for x in v if str(x).strip())
        out[key] = _dedupe_sentences(str(v).strip())
        if not out[key]:
            raise ValueError(f"LLM output has empty {key!r}")
    for tok in ("[SENDER]", "[RECEIVER]"):
        if tok not in out["summary"]:
            raise ValueError(f"LLM summary does not reference {tok}")
    if _norm(out["summary"]).startswith(_norm(EXAMPLE.split("ACTION:")[0].replace("SUMMARY:", ""))[:120]):
        raise ValueError("LLM copied the example summary verbatim")
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
