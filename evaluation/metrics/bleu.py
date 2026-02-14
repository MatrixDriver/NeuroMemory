"""BLEU-1 (unigram) score with brevity penalty (no external dependencies)."""

from __future__ import annotations

import math
import re
from collections import Counter


def _tokenize(text: str) -> list[str]:
    text = str(text).lower()
    text = re.sub(r"[^\w\s]", "", text)
    return text.split()


def compute_bleu1(prediction: str, gold: str) -> float:
    """Compute BLEU-1 (unigram precision with brevity penalty)."""
    pred_tokens = _tokenize(prediction)
    gold_tokens = _tokenize(gold)
    if not pred_tokens:
        return 0.0
    if not gold_tokens:
        return 0.0

    pred_counts = Counter(pred_tokens)
    gold_counts = Counter(gold_tokens)

    clipped = sum(min(pred_counts[t], gold_counts[t]) for t in pred_counts)
    precision = clipped / len(pred_tokens)

    # Brevity penalty
    bp = 1.0
    if len(pred_tokens) < len(gold_tokens):
        bp = math.exp(1 - len(gold_tokens) / len(pred_tokens))

    return bp * precision
