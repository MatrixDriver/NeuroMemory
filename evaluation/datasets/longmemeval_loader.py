"""Load and parse LongMemEval dataset."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class LongMemEvalMessage:
    role: str
    content: str


@dataclass
class LongMemEvalSession:
    session_idx: int
    timestamp: datetime | None
    messages: list[LongMemEvalMessage] = field(default_factory=list)


@dataclass
class LongMemEvalQuestion:
    question_id: str
    question: str
    answer: str
    question_type: str
    answer_sessions: list[int] = field(default_factory=list)
    sessions: list[LongMemEvalSession] = field(default_factory=list)


def _parse_timestamp(raw: str | None) -> datetime | None:
    if not raw:
        return None
    for fmt in [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%B %d, %Y, %I:%M %p",
        "%B %d, %Y",
    ]:
        try:
            return datetime.strptime(raw.strip(), fmt)
        except ValueError:
            continue
    return None


def load_longmemeval(path: str) -> list[LongMemEvalQuestion]:
    """Load LongMemEval JSON and return structured questions."""
    with open(path) as f:
        raw = json.load(f)

    questions = []
    for item in raw:
        qid = str(item.get("question_id", item.get("id", "")))
        question = item.get("question", item.get("query", ""))
        answer = item.get("answer", item.get("gold_answer", ""))
        qtype = item.get("question_type", item.get("type", "knowledge"))
        answer_sessions = item.get("answer_sessions", [])

        # Parse haystack sessions
        sessions = []
        haystack = item.get("haystack_sessions", item.get("sessions", []))
        dates = item.get("haystack_dates", item.get("dates", []))

        for idx, sess_data in enumerate(haystack):
            ts = _parse_timestamp(dates[idx] if idx < len(dates) else None)
            messages = []
            if isinstance(sess_data, list):
                for msg in sess_data:
                    if isinstance(msg, dict):
                        messages.append(LongMemEvalMessage(
                            role=msg.get("role", "user"),
                            content=msg.get("content", ""),
                        ))
                    elif isinstance(msg, list) and len(msg) >= 2:
                        messages.append(LongMemEvalMessage(role=msg[0], content=msg[1]))
            elif isinstance(sess_data, dict):
                for msg in sess_data.get("messages", []):
                    messages.append(LongMemEvalMessage(
                        role=msg.get("role", "user"),
                        content=msg.get("content", ""),
                    ))

            sessions.append(LongMemEvalSession(
                session_idx=idx, timestamp=ts, messages=messages,
            ))

        questions.append(LongMemEvalQuestion(
            question_id=qid,
            question=question,
            answer=answer,
            question_type=qtype,
            answer_sessions=answer_sessions,
            sessions=sessions,
        ))

    return questions
