"""OpenAI-compatible LLM provider (works with OpenAI, DeepSeek, etc.)."""

import httpx

from neuromemory.providers.llm import LLMProvider


class OpenAILLM(LLMProvider):
    """OpenAI-compatible LLM provider for memory classification."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
    ):
        self._api_key = api_key
        self._model = model
        self._base_url = base_url

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> str:
        is_reasoner = "reasoner" in self._model

        # Reasoner models: merge system+user into single user message, skip temperature
        if is_reasoner:
            converted = []
            for msg in messages:
                role = "user" if msg["role"] == "system" else msg["role"]
                # Merge consecutive user messages
                if converted and converted[-1]["role"] == "user" and role == "user":
                    converted[-1]["content"] += "\n\n" + msg["content"]
                else:
                    converted.append({"role": role, "content": msg["content"]})
            messages = converted

        body = {
            "model": self._model,
            "messages": messages,
        }
        if is_reasoner:
            # Reasoner needs more tokens: reasoning_tokens + content tokens
            body["max_tokens"] = max(max_tokens, 4096)
        else:
            body["max_tokens"] = max_tokens
            body["temperature"] = temperature

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
            msg = data["choices"][0]["message"]
            content = msg.get("content") or ""
            # Reasoner models may put the answer in reasoning_content
            if is_reasoner and not content.strip():
                reasoning = msg.get("reasoning_content") or ""
                # Extract last paragraph as the answer
                lines = [l.strip() for l in reasoning.strip().split("\n") if l.strip()]
                content = lines[-1] if lines else ""
            return content
