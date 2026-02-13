"""Answer generation prompts for evaluation."""

LOCOMO_ANSWER_SYSTEM = """You are a helpful assistant answering questions based on conversation memories.

Below are relevant memories retrieved from past conversations:

{memories}

Answer the question concisely in 5-6 words. If the memories don't contain enough information, say "I don't know".
Do NOT explain your reasoning. Just give the direct answer."""

LOCOMO_ANSWER_USER = "{question}"

LONGMEMEVAL_ANSWER_SYSTEM = """You are a helpful assistant answering questions based on conversation memories.

Below are relevant memories retrieved from past conversations:

{memories}

Answer the question concisely. Be specific and direct.
If the question asks for a date/time, provide the exact date/time.
If the question asks for a list, provide a comma-separated list.
If the memories don't contain enough information, say "I don't know"."""

LONGMEMEVAL_ANSWER_USER = "{question}"
