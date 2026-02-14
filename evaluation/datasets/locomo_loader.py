"""Load and parse LoCoMo dataset (locomo10.json)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class LoCoMoMessage:
    speaker: str
    text: str


@dataclass
class LoCoMoSession:
    session_key: str  # e.g. "session_1"
    session_idx: int
    timestamp: datetime | None
    messages: list[LoCoMoMessage] = field(default_factory=list)


@dataclass
class LoCoMoQA:
    question: str
    answer: str
    category: int
    evidence: list[str] = field(default_factory=list)


@dataclass
class LoCoMoConversation:
    conv_idx: int
    speaker_a: str
    speaker_b: str
    sessions: list[LoCoMoSession] = field(default_factory=list)
    qa_pairs: list[LoCoMoQA] = field(default_factory=list)


def _parse_timestamp(raw: str) -> datetime | None:
    """Parse LoCoMo timestamp strings like '1:56 pm on 8 May, 2023'."""
    if not raw:
        return None
    raw = raw.strip()
    for fmt in [
        # "1:56 pm on 8 May, 2023"
        "%I:%M %p on %d %B, %Y",
        # "1:56 PM on 8 May, 2023"
        "%I:%M %p on %d %B, %Y",
        # "November 20, 2023, 6:00 PM"
        "%B %d, %Y, %I:%M %p",
        "%B %d, %Y, %H:%M",
        "%B %d, %Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _parse_messages(session_data: list) -> list[LoCoMoMessage]:
    """Parse session message list: each item is {speaker, text, dia_id}."""
    messages = []
    for item in session_data:
        if isinstance(item, dict):
            messages.append(LoCoMoMessage(
                speaker=item.get("speaker", ""),
                text=item.get("text", item.get("content", "")),
            ))
        elif isinstance(item, list) and len(item) >= 2:
            messages.append(LoCoMoMessage(speaker=item[0], text=item[1]))
    return messages


def load_locomo(path: str) -> list[LoCoMoConversation]:
    """Load locomo10.json and return structured conversations.

    Data format: [{conversation: {speaker_a, speaker_b, session_N, session_N_date_time}, qa: [...]}]
    """
    with open(path) as f:
        raw = json.load(f)

    conversations = []
    for conv_idx, item in enumerate(raw):
        # conversation data is nested under "conversation" key
        conv_data = item.get("conversation", item)
        speaker_a = conv_data.get("speaker_a", "PersonA")
        speaker_b = conv_data.get("speaker_b", "PersonB")

        # Parse sessions
        sessions = []
        session_keys = sorted(
            (k for k in conv_data.keys() if re.match(r"session_\d+$", k)),
            key=lambda k: int(re.search(r"\d+", k).group()),
        )
        for idx, key in enumerate(session_keys):
            date_key = f"{key}_date_time"
            ts = _parse_timestamp(conv_data.get(date_key, ""))
            msgs = _parse_messages(conv_data[key])
            sessions.append(LoCoMoSession(
                session_key=key, session_idx=idx, timestamp=ts, messages=msgs,
            ))

        # Parse QA pairs — key is "qa" or "qa_pairs"
        qa_raw = item.get("qa", item.get("qa_pairs", []))
        qa_pairs = []
        for qa in qa_raw:
            cat = qa.get("category", 0)
            if isinstance(cat, str):
                cat = int(cat) if cat.isdigit() else 0
            qa_pairs.append(LoCoMoQA(
                question=qa.get("question", ""),
                answer=qa.get("answer", ""),
                category=cat,
                evidence=qa.get("evidence", []),
            ))

        conversations.append(LoCoMoConversation(
            conv_idx=conv_idx,
            speaker_a=speaker_a,
            speaker_b=speaker_b,
            sessions=sessions,
            qa_pairs=qa_pairs,
        ))

    return conversations
