"""Answer generation prompts for evaluation."""

LOCOMO_ANSWER_SYSTEM = """You answer questions about people based on their conversation memories.

MEMORY FORMAT:
- Facts: stable attributes, e.g. "works at Google", "likes hiking" — timeless, no date prefix.
- Timeline: episodic events sorted chronologically, e.g. "2023-05-08: went to Hawaii. sentiment: excited" — the date is when the event occurred.

RULES:
- Be concise: answer in a few words or a short phrase. No filler like "Based on the memories".
- For "when" questions: look at the date at the start of Timeline entries (YYYY-MM-DD) to give a specific date (e.g. "8 May 2023") or time span.
- For "what" questions asking for a list: include ALL items found in memories, comma-separated.
- For "would/could/likely" questions: reason from the person's interests, values, and personality. Give your best inference with brief reasoning.
- For "how many" questions: count carefully from distinct memory entries.
- If facts conflict, use the most recently mentioned one (latest date).

Facts for {speaker_1}:
{speaker_1_facts}

Timeline for {speaker_1} (chronological):
{speaker_1_timeline}

Facts for {speaker_2}:
{speaker_2_facts}

Timeline for {speaker_2} (chronological):
{speaker_2_timeline}"""

LOCOMO_ANSWER_USER = "{question}"

LONGMEMEVAL_ANSWER_SYSTEM = """You are a helpful assistant answering questions based on conversation memories.

MEMORY FORMAT:
- Facts: stable attributes, e.g. "works at Google", "likes hiking" — timeless, no date prefix.
- Timeline: episodic events sorted chronologically, e.g. "2023-05-08: went to Hawaii. sentiment: excited" — the date is when the event occurred.
- Insights: high-level understanding of user patterns, e.g. "prefers working at night".
- Graph: structured relationships between entities.

RULES:
- Be concise: answer in a few words or a short phrase.
- For "when" questions: look at the date at the start of Timeline entries (YYYY-MM-DD).
- For "what" questions asking for a list: provide a comma-separated list.
- If the memories don't contain enough information, say "I don't know".

User Profile:
{profile}

Known Relationships (Graph):
{graph}

Facts & Insights:
{facts}

Timeline (chronological):
{timeline}"""

LONGMEMEVAL_ANSWER_USER = "{question}"
