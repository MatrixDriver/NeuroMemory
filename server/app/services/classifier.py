"""LLM-based memory classifier service using DeepSeek"""

import json
import logging
from typing import Dict, List, Optional

from server.app.core.config import get_settings

logger = logging.getLogger(__name__)


class MemoryClassifier:
    """LLM-based classifier for extracting memories from conversations

    Uses DeepSeek API (OpenAI-compatible) to analyze conversation messages and extract:
    - Preferences: User likes, dislikes, habits, settings
    - Facts: Objective information about user (work, skills, hobbies)
    - Episodes: Events, experiences, temporal information
    """

    def __init__(self):
        self.settings = get_settings()
        self._client = None

    def _get_client(self):
        """Lazy initialization of OpenAI client (for DeepSeek)"""
        if self._client is None:
            try:
                from openai import OpenAI

                if not self.settings.deepseek_api_key:
                    logger.warning("DEEPSEEK_API_KEY not configured, classifier disabled")
                    return None

                self._client = OpenAI(
                    api_key=self.settings.deepseek_api_key,
                    base_url=self.settings.deepseek_base_url,
                )
            except ImportError:
                logger.error("openai package not installed")
                return None
        return self._client

    def classify_messages(
        self,
        messages: List[Dict],
        user_id: str,
    ) -> Dict[str, List[Dict]]:
        """Classify and extract memories from a list of messages

        Args:
            messages: List of message dicts with 'role' and 'content'
            user_id: User identifier for context

        Returns:
            Dict with extracted memories:
            {
                "preferences": [{"key": "...", "value": "...", "confidence": 0.9}, ...],
                "facts": [{"content": "...", "category": "work", "confidence": 0.95}, ...],
                "episodes": [{"content": "...", "timestamp": "...", "confidence": 0.85}, ...]
            }
        """
        client = self._get_client()
        if not client:
            logger.warning("Classifier not available, returning empty results")
            return {"preferences": [], "facts": [], "episodes": []}

        # Format conversation for prompt
        conversation_text = self._format_conversation(messages)

        # Build classification prompt
        prompt = self._build_classification_prompt(conversation_text, user_id)

        try:
            # Call DeepSeek API (OpenAI-compatible)
            response = client.chat.completions.create(
                model=self.settings.deepseek_model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,  # Low temperature for more consistent extraction
                max_tokens=2048,
            )

            # Parse response
            result_text = response.choices[0].message.content
            extracted = self._parse_classification_result(result_text)

            logger.info(
                f"Classified {len(messages)} messages for user {user_id}: "
                f"{len(extracted['preferences'])} preferences, "
                f"{len(extracted['facts'])} facts, "
                f"{len(extracted['episodes'])} episodes"
            )

            return extracted

        except Exception as e:
            logger.error(f"Classification failed: {e}", exc_info=True)
            return {"preferences": [], "facts": [], "episodes": []}

    def _format_conversation(self, messages: List[Dict]) -> str:
        """Format messages into readable conversation text"""
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown").upper()
            content = msg.get("content", "")
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    def _build_classification_prompt(self, conversation: str, user_id: str) -> str:
        """Build the classification prompt for DeepSeek"""
        return f"""分析以下对话，提取用户的记忆信息。请严格按照 JSON 格式返回结果。

对话内容：
```
{conversation}
```

请提取以下三类记忆：

1. **Preferences（偏好）**: 用户的喜好、习惯、设置
   - 格式: {{"key": "偏好名称", "value": "偏好值", "confidence": 0.0-1.0}}
   - 示例: {{"key": "favorite_color", "value": "蓝色", "confidence": 0.95}}
   - key 应该用英文，value 可以是中文

2. **Facts（事实）**: 用户的客观信息
   - 格式: {{"content": "事实描述", "category": "分类", "confidence": 0.0-1.0}}
   - category 可选: work, skill, hobby, personal, education, location
   - 示例: {{"content": "在 Google 工作", "category": "work", "confidence": 0.98}}

3. **Episodes（情景）**: 事件、经历、时间相关信息
   - 格式: {{"content": "事件描述", "timestamp": "时间信息或null", "confidence": 0.0-1.0}}
   - 示例: {{"content": "上周去了北京旅行", "timestamp": "上周", "confidence": 0.90}}

要求：
- 只提取明确提到的信息，不要推测
- confidence 表示提取的确信度 (0.0-1.0)
- 如果某类没有信息，返回空列表
- 必须返回有效的 JSON 格式，不要有其他文字说明

返回格式（只返回 JSON，不要其他内容）：
```json
{{
  "preferences": [...],
  "facts": [...],
  "episodes": [...]
}}
```"""

    def _parse_classification_result(self, result_text: str) -> Dict[str, List[Dict]]:
        """Parse DeepSeek's classification result

        Args:
            result_text: Raw text response from DeepSeek

        Returns:
            Structured extraction result
        """
        try:
            # Try to find JSON in the response
            # DeepSeek might wrap it in markdown code blocks
            text = result_text.strip()

            # Remove markdown code blocks if present
            if "```json" in text:
                start = text.find("```json") + 7
                end = text.find("```", start)
                text = text[start:end].strip()
            elif "```" in text:
                start = text.find("```") + 3
                end = text.find("```", start)
                text = text[start:end].strip()

            # Parse JSON
            result = json.loads(text)

            # Validate structure
            if not isinstance(result, dict):
                raise ValueError("Result is not a dictionary")

            # Ensure all required keys exist
            preferences = result.get("preferences", [])
            facts = result.get("facts", [])
            episodes = result.get("episodes", [])

            # Validate types
            if not isinstance(preferences, list):
                preferences = []
            if not isinstance(facts, list):
                facts = []
            if not isinstance(episodes, list):
                episodes = []

            return {
                "preferences": preferences,
                "facts": facts,
                "episodes": episodes,
            }

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from classification result: {e}")
            logger.debug(f"Result text: {result_text}")
            return {"preferences": [], "facts": [], "episodes": []}
        except Exception as e:
            logger.error(f"Error parsing classification result: {e}")
            return {"preferences": [], "facts": [], "episodes": []}


# Singleton instance
_classifier_instance: Optional[MemoryClassifier] = None


def get_classifier() -> MemoryClassifier:
    """Get or create the classifier singleton"""
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = MemoryClassifier()
    return _classifier_instance
