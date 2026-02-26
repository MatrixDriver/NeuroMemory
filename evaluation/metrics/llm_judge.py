"""LLM-based binary judge using OpenAI-compatible API."""

from __future__ import annotations

import json
import logging

from neuromem.providers.openai_llm import OpenAILLM

from evaluation.prompts.judge import LOCOMO_JUDGE_PROMPT, LONGMEMEVAL_JUDGE_PROMPT

logger = logging.getLogger(__name__)


async def judge_locomo(
    llm: OpenAILLM,
    question: str,
    gold_answer: str,
    predicted: str,
) -> float:
    """Binary judge for LoCoMo: returns 1.0 (CORRECT) or 0.0 (WRONG)."""
    prompt = LOCOMO_JUDGE_PROMPT.format(
        question=question, gold_answer=gold_answer, predicted=predicted
    )
    return await _call_judge(llm, prompt)


async def judge_longmemeval(
    llm: OpenAILLM,
    question_type: str,
    question: str,
    gold_answer: str,
    predicted: str,
) -> float:
    """Binary judge for LongMemEval with question-type awareness."""
    prompt = LONGMEMEVAL_JUDGE_PROMPT.format(
        question_type=question_type,
        question=question,
        gold_answer=gold_answer,
        predicted=predicted,
    )
    return await _call_judge(llm, prompt)


async def _call_judge(llm: OpenAILLM, prompt: str) -> float:
    """Call judge LLM and parse binary label."""
    try:
        response = await llm.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=64,
        )
        response = response.strip()
        # Try JSON parsing first
        if "{" in response:
            start = response.index("{")
            end = response.rindex("}") + 1
            data = json.loads(response[start:end])
            label = data.get("label", "").upper()
        else:
            label = response.strip().upper()

        return 1.0 if label == "CORRECT" else 0.0
    except Exception as e:
        logger.warning("Judge call failed: %s", e)
        return 0.0
