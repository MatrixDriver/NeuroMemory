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


def _parse_timestamp(session_key: str, conv_data: dict) -> datetime | None:
    """Try to extract timestamp from session date_time field."""
    date_key = f"{session_key}_date_time"
    raw = conv_data.get(date_key, "")
    if not raw:
        return None
    try:
        # Formats seen in LoCoMo: "November 20, 2023, 6:00 PM" etc.
        for fmt in [
            "%B %d, %Y, %I:%M %p",
            "%B %d, %Y, %H:%M",
            "%B %d, %Y",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]:
            try:
                return datetime.strptime(raw.strip(), fmt)
            except ValueError:
                continue
    except Exception:
        pass
    return None


def _parse_messages(session_data: list[list[str]]) -> list[LoCoMoMessage]:
    """Parse session message list: each item is [speaker, text]."""
    messages = []
    for item in session_data:
        if isinstance(item, list) and len(item) >= 2:
            messages.append(LoCoMoMessage(speaker=item[0], text=item[1]))
        elif isinstance(item, dict):
            messages.append(LoCoMoMessage(
                speaker=item.get("speaker", ""),
                text=item.get("text", item.get("content", "")),
            ))
    return messages


def load_locomo(path: str) -> list[LoCoMoConversation]:
    """Load locomo10.json and return structured conversations."""
    with open(path) as f:
        raw = json.load(f)

    conversations = []
    for conv_idx, conv_data in enumerate(raw):
        speaker_a = conv_data.get("speaker_a", conv_data.get("PersonA", f"PersonA"))
        speaker_b = conv_data.get("speaker_b", conv_data.get("PersonB", f"PersonB"))

        # Parse sessions
        sessions = []
        session_keys = sorted(
            k for k in conv_data.keys() if re.match(r"session_\d+$", k)
        )
        for idx, key in enumerate(session_keys):
            ts = _parse_timestamp(key, conv_data)
            msgs = _parse_messages(conv_data[key])
            sessions.append(LoCoMoSession(
                session_key=key, session_idx=idx, timestamp=ts, messages=msgs,
            ))

        # Parse QA pairs
        qa_pairs = []
        for qa in conv_data.get("qa_pairs", conv_data.get("QA", [])):
            cat = qa.get("category", qa.get("cat", 0))
            if isinstance(cat, str):
                cat = int(cat) if cat.isdigit() else 0
            qa_pairs.append(LoCoMoQA(
                question=qa.get("question", qa.get("Q", "")),
                answer=qa.get("answer", qa.get("A", "")),
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
