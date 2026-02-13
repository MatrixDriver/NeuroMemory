"""Token-level F1 score (no external dependencies)."""

from __future__ import annotations

import re


def _tokenize(text: str) -> list[str]:
    """Lowercase, remove punctuation, split on whitespace."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    return text.split()


def compute_f1(prediction: str, gold: str) -> float:
    """Compute token-level F1 between prediction and gold answer."""
    pred_tokens = _tokenize(prediction)
    gold_tokens = _tokenize(gold)
    if not pred_tokens or not gold_tokens:
        return 1.0 if pred_tokens == gold_tokens else 0.0
    common = set(pred_tokens) & set(gold_tokens)
    if not common:
        return 0.0
    precision = len(common) / len(pred_tokens)
    recall = len(common) / len(gold_tokens)
    return 2 * precision * recall / (precision + recall)
