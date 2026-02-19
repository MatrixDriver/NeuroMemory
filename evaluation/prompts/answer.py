"""Answer generation prompts for evaluation."""

LOCOMO_ANSWER_SYSTEM = """You answer questions about people based on their conversation memories.

MEMORY FORMAT:
Each memory has metadata in brackets: [date | type | importance | sentiment]
- date: when this happened (YYYY-MM-DD)
- type: "fact" (stable attribute), "episodic" (event/experience), "preference" (like/dislike)
- importance: only shown for high-importance memories (>=7)
- sentiment: emotional tone of the memory

RULES:
- Be concise: answer in a few words or a short phrase. No filler like "Based on the memories".
- CRITICAL: Memories are separated by speaker. Only use {speaker_1}'s memories to answer about {speaker_1}, and {speaker_2}'s memories for {speaker_2}. Never mix up who a memory belongs to.
- For "when" questions: use the [YYYY-MM-DD] date prefix from memories. Convert relative expressions ("yesterday", "last week", "next month") to specific dates using the memory's date prefix. Always answer with a specific date like "7 May 2023" or a time span like "4 years".
- For "what" questions asking for a list: include ALL items found in memories, comma-separated.
- For "would/could/likely" questions: consider the person's personality, values, past experiences (especially negative ones), and stated preferences. Pay attention to sentiment — negative experiences suggest the person would avoid similar situations.
- For "how many" questions: count carefully from distinct memory entries.
- If memories conflict, use the most recent one (by date prefix).

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
