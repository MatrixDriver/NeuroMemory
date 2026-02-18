"""Answer generation prompts for evaluation."""

LOCOMO_ANSWER_SYSTEM = """You answer questions about people based on their conversation memories.

RULES:
- Be concise: answer in a few words or a short phrase. No filler like "Based on the memories".
- For "when" questions: give a specific date (e.g. "7 May 2023") or time span (e.g. "4 years").
- For "what" questions asking for a list: include ALL items found in memories, comma-separated.
- For "would/could/likely" questions: reason from what you know about the person's interests, values, and personality from the memories. Give your best inference with brief reasoning.
- For "how many" questions: count carefully from distinct memory entries.
- If memories conflict, use the most recent one.

Memories for {speaker_1}:
{speaker_1_memories}

Memories for {speaker_2}:
{speaker_2_memories}"""

LOCOMO_ANSWER_USER = "{question}"

LONGMEMEVAL_ANSWER_SYSTEM = """You are a helpful assistant answering questions based on conversation memories.

Below are relevant memories retrieved from past conversations:

{memories}

Answer the question concisely. Be specific and direct.
If the question asks for a date/time, provide the exact date/time.
If the question asks for a list, provide a comma-separated list.
If the memories don't contain enough information, say "I don't know"."""

LONGMEMEVAL_ANSWER_USER = "{question}"
