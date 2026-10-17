"""Prompt construction and response parsing for the LLM engine.

The LLM never sees an account number, an amount, a bank id, or the model hash. It gets
qualitative facts and the model's top reasons, and returns one "ASSESSMENT:" paragraph that
explains why the pattern is suspicious. Every factual sentence in the SAR is written by code.
"""
from __future__ import annotations

import logging
import re

from fedaml.llm.facts import indicator_lines

log = logging.getLogger("fedaml.llm.narrate")

SYSTEM_PROMPT = (
    "You are a senior anti-money-laundering compliance analyst writing the narrative of a "
    "Suspicious Activity Report. Write in formal, neutral English. Never state that a crime "
    "occurred and never say the payment is, or is likely to be, money laundering: the alert is only ranked for "
    "analyst review. Describe indicators, name the typology it resembles, and recommend review. Never write an account number, amount, date, "
    "bank id or statistic; the report's code inserts those. Treat the transaction as high-risk: the cross-bank model ranked it "
    "among the most suspicious in the sample, and your recommendation is always to review it. Do not repeat "
    "sentences. Answer with the ASSESSMENT paragraph only."
)

EXAMPLE = (
    "ASSESSMENT: The transfer was a round amount sent by wire to a receiver that collects payments from many "
    "unrelated payers, which is typical of a collection or mule account. The sender rarely transacts, so a single "
    "large outgoing payment is out of character. Because the counterparties sit at different banks, no single "
    "institution would see the full pattern on its own. The activity is consistent with layering and merits review."
)


def build_user_prompt(alert: dict) -> str:
    """User turn: qualitative facts and model reasons only (no ids, no amounts), one example answer."""
    lines = indicator_lines(alert)
    indicators = "\n".join(f"- {s}" for s in lines) or "- no dominant indicator"
    return (
        "A cross-bank laundering detector, trained jointly by several banks without sharing their data, flagged "
        "one payment as one of the most suspicious in the sample.\n"
        "Facts:\n"
        "- Payment format: [FMT]. Currency: [CUR].\n"
        "- The sender [SENDER_ACTIVITY]. The receiver [RECEIVER_ACTIVITY].\n"
        "- The linked chain spans [N_BANKS] institutions.\n"
        f"Why the model flagged it, strongest reason first:\n{indicators}\n\n"
        "Write one paragraph for a compliance officer explaining, in your own words, why this pattern is suspicious "
        "and what typology it may fit. Use three or four sentences. Do not mention account numbers, bank ids, "
        "amounts or dates. Start with ASSESSMENT:\n\n"
        f"Example for a different case:\n{EXAMPLE}"
    )


def _norm(s: str) -> str:
    return re.sub(r"\W+", " ", s).strip().lower()


# Sentences that turn "ranked for review" into a verdict are dropped (MASTER wording rule, Oct 17 16:26).
VERDICT = re.compile(r"\b(likelihood|likely|probabl\w*|evidence|proves?|confirm\w*)\b[^.]*\blaundering\b|"
                     r"\b(is|was|constitutes|consistent with|indicat\w*|suggest\w*)\b[^.]*\bmoney laundering\b", re.I)


def parse_response(text: str) -> dict[str, str]:
    """Extract the ``ASSESSMENT:`` paragraph (label optional). Raises ValueError on unusable output."""
    m = re.search(r"ASSESSMENT\s*:\s*(.+)", text, flags=re.S | re.I)
    body = (m.group(1) if m else text).strip()
    body = re.split(r"\n\s*\n|\n\s*(?:Example|ASSESSMENT)\b", body, flags=re.I)[0].strip()
    body = _dedupe_sentences(" ".join(body.split()))
    body = _drop_copied(body, EXAMPLE.replace("ASSESSMENT:", ""))
    body = " ".join(x for x in re.split(r"(?<=[.!?])\s+", body) if not VERDICT.search(x)).strip()
    if not body:
        raise ValueError("empty LLM assessment (after removing sentences copied from the example)")
    return {"assessment": body}


def _drop_copied(text: str, source: str) -> str:
    """Remove sentences the model lifted (nearly) verbatim from ``source`` (the one-shot example)."""
    src = [_norm(x) for x in re.split(r"(?<=[.!?])\s+", source) if x.strip()]
    kept = []
    for sent in re.split(r"(?<=[.!?])\s+", text):
        n = _norm(sent)
        if n and any(n == x or (len(n) > 30 and (n in x or x in n)) for x in src):
            continue
        kept.append(sent)
    return " ".join(kept).strip()


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
