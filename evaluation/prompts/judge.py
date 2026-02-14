"""LLM Judge prompts for LoCoMo and LongMemEval."""

LOCOMO_JUDGE_PROMPT = """You are a generous judge evaluating the correctness of an answer to a question about past conversations.

Question: {question}
Gold answer: {gold_answer}
Predicted answer: {predicted}

Evaluate whether the predicted answer is consistent with the gold answer.
- Be generous with grading: as long as the predicted answer touches on the same topic and key information as the gold answer, mark it as CORRECT.
- Minor wording differences, abbreviations, and paraphrasing are all acceptable (e.g., "New York" vs "NYC", "working out" vs "exercise").
- Partial answers that capture the main point are CORRECT.
- "I don't know", empty answers, or completely irrelevant answers are WRONG.

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
