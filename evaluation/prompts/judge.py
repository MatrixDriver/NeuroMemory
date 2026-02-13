"""LLM Judge prompts for LoCoMo and LongMemEval."""

LOCOMO_JUDGE_PROMPT = """You are an impartial judge evaluating the correctness of an answer to a question about past conversations.

Question: {question}
Gold answer: {gold_answer}
Predicted answer: {predicted}

Evaluate whether the predicted answer conveys the same meaning as the gold answer.
- Minor wording differences are acceptable (e.g., "New York" vs "NYC").
- The predicted answer must capture the key facts from the gold answer.
- "I don't know" or irrelevant answers are WRONG.

Respond with a JSON object containing a single key "label" with value "CORRECT" or "WRONG".
Example: {{"label": "CORRECT"}}"""

LONGMEMEVAL_JUDGE_PROMPT = """You are an impartial judge evaluating the correctness of an answer about past conversations.

Question type: {question_type}
Question: {question}
Gold answer: {gold_answer}
Predicted answer: {predicted}

Evaluation rules by question type:
- For "temporal" questions: Accept equivalent date formats (e.g., "Jan 15" vs "January 15, 2024"). The core temporal fact must match.
- For "knowledge" questions: The key facts must match. Minor wording differences are acceptable.
- For "event_order" questions: The ordering/sequence must be correct.
- For "counting" questions: The number must be exactly correct.
- For "reasoning" questions: The conclusion must match the gold answer's meaning.

If the predicted answer is "I don't know" or doesn't address the question, mark as WRONG.

Respond with a JSON object: {{"label": "CORRECT"}} or {{"label": "WRONG"}}"""
