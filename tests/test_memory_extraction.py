"""Tests for memory extraction with LLM classifier."""

import pytest
from neuromem.providers.llm import LLMProvider
from neuromem.services.conversation import ConversationService
from neuromem.services.memory_extraction import MemoryExtractionService
from neuromem.services.kv import KVService


class MockLLMProvider(LLMProvider):
    """Mock LLM that returns predictable classification results."""

    def __init__(self, response: str = ""):
        self._response = response

    async def chat(self, messages, temperature=0.1, max_tokens=2048) -> str:
        return self._response


@pytest.mark.asyncio
async def test_extract_memories_from_conversations(db_session, mock_embedding):
    """Test extracting memories from conversation messages."""
    # Add conversation messages
    conv_svc = ConversationService(db_session)
    _, msg_ids = await conv_svc.add_messages_batch(
        user_id="test_user",
        messages=[
            {"role": "user", "content": "我在 Google 工作，主要做后端开发"},
            {"role": "assistant", "content": "很高兴认识您！"},
            {"role": "user", "content": "我喜欢蓝色，平时喜欢看科幻电影"},
            {"role": "assistant", "content": "了解了您的偏好！"},
        ],
    )

    # Get messages for extraction
    messages = await conv_svc.get_unextracted_messages(user_id="test_user")

    # Mock LLM response
    mock_llm = MockLLMProvider(response="""```json
{
  "facts": [
    {"content": "在 Google 工作", "category": "work", "confidence": 0.98},
    {"content": "主要做后端开发", "category": "skill", "confidence": 0.95}
  ],
  "episodes": [],
  "profile_updates": {
    "preferences": ["喜欢蓝色", "看科幻电影"]
  }
}
```""")

    extraction_svc = MemoryExtractionService(db_session, mock_embedding, mock_llm)
    result = await extraction_svc.extract_from_messages(
        user_id="test_user",
        messages=messages,
    )

    assert result["messages_processed"] == 4
    assert result["facts_extracted"] == 2
    assert result["episodes_extracted"] == 0

    # Verify preferences stored in profile namespace
    kv_svc = KVService(db_session)
    prefs = await kv_svc.get("profile", "test_user", "preferences")
    assert prefs is not None
    assert len(prefs.value) >= 2


@pytest.mark.asyncio
async def test_extract_with_no_messages(db_session, mock_embedding):
    """Test extraction when there are no messages."""
    mock_llm = MockLLMProvider()
    extraction_svc = MemoryExtractionService(db_session, mock_embedding, mock_llm)
    result = await extraction_svc.extract_from_messages(
        user_id="nonexistent_user",
        messages=[],
    )

    assert result["messages_processed"] == 0
    assert result["facts_extracted"] == 0


@pytest.mark.asyncio
async def test_parse_classification_result():
    """Test classifier JSON parsing with various formats."""
    mock_llm = MockLLMProvider()
    svc = MemoryExtractionService.__new__(MemoryExtractionService)

    # With markdown code block
    result1 = svc._parse_classification_result("""
```json
{
  "facts": [{"content": "test fact", "category": "work", "confidence": 0.9}],
  "episodes": []
}
```
    """)
    assert len(result1["facts"]) == 1
    assert result1["facts"][0]["content"] == "test fact"

    # Without markdown
    result2 = svc._parse_classification_result("""
{
  "facts": [{"content": "test", "category": "work", "confidence": 0.8}],
  "episodes": []
}
    """)
    assert len(result2["facts"]) == 1

    # Invalid JSON
    result3 = svc._parse_classification_result("not json")
    assert result3 == {"facts": [], "episodes": [], "triples": [], "profile_updates": {}}


@pytest.mark.asyncio
async def test_extract_with_graph_triples(db_session, mock_embedding):
    """Test extraction with graph_enabled=True stores triples."""
    conv_svc = ConversationService(db_session)
    _, msg_ids = await conv_svc.add_messages_batch(
        user_id="test_user",
        messages=[
            {"role": "user", "content": "我在 Google 工作，主要做后端开发"},
            {"role": "assistant", "content": "很高兴认识您！"},
        ],
    )
    messages = await conv_svc.get_unextracted_messages(user_id="test_user")

    mock_llm = MockLLMProvider(response="""```json
{
  "facts": [
    {"content": "在 Google 工作", "category": "work", "confidence": 0.98}
  ],
  "episodes": [],
  "triples": [
    {"subject": "user", "subject_type": "user", "relation": "works_at",
     "object": "Google", "object_type": "organization",
     "content": "在 Google 工作", "confidence": 0.98},
    {"subject": "user", "subject_type": "user", "relation": "has_skill",
     "object": "后端开发", "object_type": "skill",
     "content": "主要做后端开发", "confidence": 0.95}
  ]
}
```""")

    extraction_svc = MemoryExtractionService(
        db_session, mock_embedding, mock_llm, graph_enabled=True,
    )
    result = await extraction_svc.extract_from_messages(
        user_id="test_user",
        messages=messages,
    )

    assert result["facts_extracted"] == 1
    assert result["triples_extracted"] == 2
    assert result["messages_processed"] == 2


@pytest.mark.asyncio
async def test_extract_without_graph_ignores_triples(db_session, mock_embedding):
    """Test extraction with graph_enabled=False does not store triples."""
    conv_svc = ConversationService(db_session)
    _, _ = await conv_svc.add_messages_batch(
        user_id="test_user2",
        messages=[
            {"role": "user", "content": "我在 Google 工作"},
        ],
    )
    messages = await conv_svc.get_unextracted_messages(user_id="test_user2")

    mock_llm = MockLLMProvider(response="""```json
{
  "facts": [{"content": "在 Google 工作", "category": "work", "confidence": 0.98}],
  "episodes": [],
  "triples": [
    {"subject": "user", "subject_type": "user", "relation": "works_at",
     "object": "Google", "object_type": "organization",
     "content": "在 Google 工作", "confidence": 0.98}
  ]
}
```""")

    extraction_svc = MemoryExtractionService(
        db_session, mock_embedding, mock_llm, graph_enabled=False,
    )
    result = await extraction_svc.extract_from_messages(
        user_id="test_user2",
        messages=messages,
    )

    assert result["facts_extracted"] == 1
    assert result["triples_extracted"] == 0  # graph disabled


@pytest.mark.asyncio
async def test_parse_classification_with_triples():
    """Test parser handles triples field."""
    svc = MemoryExtractionService.__new__(MemoryExtractionService)

    result = svc._parse_classification_result("""```json
{
  "facts": [{"content": "在 Google 工作", "category": "work", "confidence": 0.98}],
  "episodes": [],
  "triples": [
    {"subject": "user", "subject_type": "user", "relation": "works_at",
     "object": "Google", "object_type": "organization",
     "content": "在 Google 工作", "confidence": 0.98}
  ]
}
```""")
    assert len(result["triples"]) == 1
    assert result["triples"][0]["relation"] == "works_at"


@pytest.mark.asyncio
async def test_extract_with_emotion_and_importance(db_session, mock_embedding):
    """Test extraction stores emotion and importance in metadata."""
    from sqlalchemy import text

    conv_svc = ConversationService(db_session)
    _, _ = await conv_svc.add_messages_batch(
        user_id="emotion_user",
        messages=[
            {"role": "user", "content": "今天被裁员了，很难过"},
            {"role": "assistant", "content": "很抱歉听到这个消息"},
        ],
    )
    messages = await conv_svc.get_unextracted_messages(user_id="emotion_user")

    mock_llm = MockLLMProvider(response="""```json
{
  "facts": [
    {
      "content": "被公司裁员",
      "category": "work",
      "confidence": 0.95,
      "importance": 9,
      "emotion": {"valence": -0.8, "arousal": 0.7, "label": "悲伤"}
    }
  ],
  "episodes": [
    {
      "content": "今天被裁员了",
      "timestamp": null,
      "confidence": 0.95,
      "importance": 9,
      "emotion": {"valence": -0.8, "arousal": 0.7, "label": "悲伤"}
    }
  ]
}
```""")

    extraction_svc = MemoryExtractionService(db_session, mock_embedding, mock_llm)
    result = await extraction_svc.extract_from_messages(
        user_id="emotion_user", messages=messages,
    )

    assert result["facts_extracted"] == 1
    assert result["episodes_extracted"] == 1

    # Verify metadata in DB
    rows = await db_session.execute(
        text("SELECT metadata FROM embeddings WHERE user_id = :uid"),
        {"uid": "emotion_user"},
    )
    for row in rows.fetchall():
        meta = row.metadata
        assert meta["importance"] == 9
        assert meta["emotion"]["valence"] == -0.8
        assert meta["emotion"]["arousal"] == 0.7
        assert meta["emotion"]["label"] == "悲伤"


@pytest.mark.asyncio
async def test_extract_without_emotion_backward_compatible(db_session, mock_embedding):
    """Test that extraction works without emotion fields (backward compatibility)."""
    conv_svc = ConversationService(db_session)
    _, _ = await conv_svc.add_messages_batch(
        user_id="compat_user",
        messages=[{"role": "user", "content": "我喜欢编程"}],
    )
    messages = await conv_svc.get_unextracted_messages(user_id="compat_user")

    # LLM response without emotion/importance (old format)
    mock_llm = MockLLMProvider(response="""```json
{
  "facts": [
    {"content": "喜欢编程", "category": "hobby", "confidence": 0.9}
  ],
  "episodes": []
}
```""")

    extraction_svc = MemoryExtractionService(db_session, mock_embedding, mock_llm)
    result = await extraction_svc.extract_from_messages(
        user_id="compat_user", messages=messages,
    )

    assert result["facts_extracted"] == 1


@pytest.mark.asyncio
async def test_language_detection_and_persistence(db_session, mock_embedding):
    """Test that language is auto-detected and saved to KV on first extraction."""
    conv_svc = ConversationService(db_session)
    kv_svc = KVService(db_session)

    # First extraction with English conversation
    _, _ = await conv_svc.add_messages_batch(
        user_id="lang_user_en",
        messages=[
            {"role": "user", "content": "I work at Google as a backend engineer"},
            {"role": "assistant", "content": "Nice to meet you!"},
        ],
    )
    messages = await conv_svc.get_unextracted_messages(user_id="lang_user_en")

    mock_llm = MockLLMProvider(response="""```json
{
  "facts": [{"content": "Works at Google", "category": "work", "confidence": 0.95}],
  "episodes": []
}
```""")

    extraction_svc = MemoryExtractionService(db_session, mock_embedding, mock_llm)
    await extraction_svc.extract_from_messages(
        user_id="lang_user_en",
        messages=messages,
    )

    # Verify language was saved as "en"
    lang_kv = await kv_svc.get("profile", "lang_user_en", "language")
    assert lang_kv is not None
    assert lang_kv.value == "en"


@pytest.mark.asyncio
async def test_language_preference_reused(db_session, mock_embedding):
    """Test that saved language preference is reused when conversation is mixed-language (low confidence)."""
    kv_svc = KVService(db_session)
    conv_svc = ConversationService(db_session)

    # Manually set language preference to Chinese
    await kv_svc.set("profile", "lang_user_zh", "language", "zh")

    # Add Chinese conversation (prefer zh stays zh)
    _, _ = await conv_svc.add_messages_batch(
        user_id="lang_user_zh",
        messages=[{"role": "user", "content": "我喜欢编程和人工智能"}],
    )
    messages = await conv_svc.get_unextracted_messages(user_id="lang_user_zh")

    # Track which prompt was used
    prompt_used = None

    class PromptCapturingLLM(LLMProvider):
        async def chat(self, messages, temperature=0.1, max_tokens=2048):
            nonlocal prompt_used
            prompt_used = messages[0]["content"]
            return """```json
{"preferences": [], "facts": [{"content": "爱编程", "category": "hobby", "confidence": 0.9}], "episodes": []}
```"""

    extraction_svc = MemoryExtractionService(db_session, mock_embedding, PromptCapturingLLM())
    await extraction_svc.extract_from_messages(
        user_id="lang_user_zh",
        messages=messages,
    )

    # Verify Chinese prompt was used (contains Chinese characters)
    assert prompt_used is not None
    chinese_chars = sum(1 for c in prompt_used if '\u4e00' <= c <= '\u9fff')
    assert chinese_chars > 50  # Should have significant Chinese text


@pytest.mark.asyncio
async def test_language_switch_with_high_confidence(db_session, mock_embedding):
    """Test language preference updates when conversation switches to another language."""
    kv_svc = KVService(db_session)
    conv_svc = ConversationService(db_session)

    # Set initial preference to zh
    await kv_svc.set("profile", "lang_switch_user", "language", "zh")

    # Add pure English conversation (high confidence)
    _, _ = await conv_svc.add_messages_batch(
        user_id="lang_switch_user",
        messages=[
            {"role": "user", "content": "I am switching to English now. This is a test."},
            {"role": "assistant", "content": "Sure, I understand you're using English."},
        ],
    )
    messages = await conv_svc.get_unextracted_messages(user_id="lang_switch_user")

    mock_llm = MockLLMProvider(response="""```json
{
  "facts": [{"content": "Prefers English", "category": "personal", "confidence": 0.9}],
  "episodes": []
}
```""")

    extraction_svc = MemoryExtractionService(db_session, mock_embedding, mock_llm)
    await extraction_svc.extract_from_messages(
        user_id="lang_switch_user",
        messages=messages,
    )

    # Verify language was updated to "en"
    lang_kv = await kv_svc.get("profile", "lang_switch_user", "language")
    assert lang_kv.value == "en"


@pytest.mark.asyncio
async def test_language_switch_low_confidence_no_update(db_session, mock_embedding):
    """Test language preference does NOT update with mixed-language conversation."""
    kv_svc = KVService(db_session)
    conv_svc = ConversationService(db_session)

    # Set initial preference to zh
    await kv_svc.set("profile", "lang_mixed_user", "language", "zh")

    # Add mixed-language conversation (low confidence)
    _, _ = await conv_svc.add_messages_batch(
        user_id="lang_mixed_user",
        messages=[
            {"role": "user", "content": "我喜欢 Python programming 和 AI"},
            {"role": "assistant", "content": "了解了您的兴趣"},
        ],
    )
    messages = await conv_svc.get_unextracted_messages(user_id="lang_mixed_user")

    mock_llm = MockLLMProvider(response="""```json
{
  "facts": [{"content": "喜欢 Python 和 AI", "category": "hobby", "confidence": 0.9}],
  "episodes": []
}
```""")

    extraction_svc = MemoryExtractionService(db_session, mock_embedding, mock_llm)
    await extraction_svc.extract_from_messages(
        user_id="lang_mixed_user",
        messages=messages,
    )

    # Verify language stayed as "zh" (not enough confidence to switch)
    lang_kv = await kv_svc.get("profile", "lang_mixed_user", "language")
    assert lang_kv.value == "zh"


@pytest.mark.asyncio
async def test_detect_language_confidence():
    """Test language detection confidence calculation."""
    svc = MemoryExtractionService.__new__(MemoryExtractionService)

    # Pure Chinese (high confidence)
    confidence_zh = svc._detect_language_confidence("我在谷歌工作，主要做后端开发")
    assert confidence_zh > 0.9

    # Pure English (high confidence)
    confidence_en = svc._detect_language_confidence("I work at Google as a backend engineer")
    assert confidence_en > 0.9

    # Mixed language (medium confidence)
    confidence_mixed = svc._detect_language_confidence("我喜欢 Python programming")
    assert 0.5 < confidence_mixed < 0.9  # Should be between pure and random

    # Empty text
    confidence_empty = svc._detect_language_confidence("")
    assert confidence_empty == 0.5


@pytest.mark.asyncio
async def test_english_prompt_generation():
    """Test that English prompt is generated correctly."""
    svc = MemoryExtractionService.__new__(MemoryExtractionService)
    svc._graph_enabled = False

    prompt = svc._build_en_prompt("USER: I work at Google\nASSISTANT: Nice!")

    # Should contain English instructions
    assert "Extract structured memory information" in prompt
    assert "Facts" in prompt
    assert "Episodes" in prompt
    assert "JSON format" in prompt

    # Should NOT contain Chinese
    chinese_chars = sum(1 for c in prompt if '\u4e00' <= c <= '\u9fff')
    assert chinese_chars == 0


@pytest.mark.asyncio
async def test_chinese_prompt_generation():
    """Test that Chinese prompt is generated correctly."""
    svc = MemoryExtractionService.__new__(MemoryExtractionService)
    svc._graph_enabled = False

    prompt = svc._build_zh_prompt("USER: 我在谷歌工作\nASSISTANT: 很好！")

    # Should contain Chinese instructions
    assert "分析以下对话" in prompt
    assert "Facts" in prompt or "事实" in prompt
    assert "Episodes" in prompt or "情景" in prompt

    # Should have significant Chinese content
    chinese_chars = sum(1 for c in prompt if '\u4e00' <= c <= '\u9fff')
    assert chinese_chars > 50


@pytest.mark.asyncio
async def test_auto_extract_on_add_message(mock_embedding):
    """Test that auto_extract=True automatically extracts memories on add_message."""
    from neuromem import NeuroMemory
    from sqlalchemy import text

    # Mock LLM for extraction
    class MockExtractionLLM(LLMProvider):
        async def chat(self, messages, temperature=0.1, max_tokens=2048):
            return """```json
{
  "facts": [{"content": "Works at Google", "category": "work", "confidence": 0.95, "importance": 8}],
  "episodes": []
}
```"""

    # Use full NeuroMemory instance with auto_extract
    nm = NeuroMemory(
        database_url="postgresql+asyncpg://neuromem:neuromem@localhost:5436/neuromem",
        embedding=mock_embedding,
        llm=MockExtractionLLM(),
        auto_extract=True,  # Enable auto-extraction
    )
    await nm.init()

    # Add a single message
    msg = await nm.conversations.add_message(
        user_id="auto_user",
        role="user",
        content="I work at Google as a software engineer",
    )

    # Wait for background extraction task to complete
    import asyncio
    await asyncio.sleep(0.3)

    # Verify memories were automatically extracted
    async with nm._db.session() as session:
        result = await session.execute(
            text("SELECT content, memory_type FROM embeddings WHERE user_id = :uid"),
            {"uid": "auto_user"},
        )
        rows = list(result.fetchall())
        assert len(rows) >= 1
        assert any(row.memory_type == "fact" for row in rows)

    await nm.close()


@pytest.mark.asyncio
async def test_auto_extract_disabled(db_session, mock_embedding):
    """Test that auto_extract=False does not extract on add_message."""
    from neuromem._core import ConversationsFacade
    from neuromem.db import Database
    from sqlalchemy import text

    db = Database.__new__(Database)
    db.engine = db_session.bind
    db.session_factory = lambda: db_session

    facade = ConversationsFacade(
        db,
        _auto_extract=False,  # Disable auto-extraction
        _embedding=mock_embedding,
        _llm=MockLLMProvider(),
        _graph_enabled=False,
    )

    # Add a message
    await facade.add_message(
        user_id="manual_user",
        role="user",
        content="I work at Google",
    )

    # Wait for background embedding task to complete (but no extraction)
    import asyncio
    await asyncio.sleep(0.1)

    # Verify NO memories were extracted
    result = await db_session.execute(
        text("SELECT COUNT(*) FROM embeddings WHERE user_id = :uid"),
        {"uid": "manual_user"},
    )
    count = result.scalar()
    assert count == 0  # No auto-extraction


@pytest.mark.asyncio
async def test_auto_extract_batch_messages(db_session, mock_embedding):
    """Test that auto_extract works with add_messages_batch."""
    from neuromem._core import ConversationsFacade
    from neuromem.db import Database
    from sqlalchemy import text

    class MockBatchLLM(LLMProvider):
        async def chat(self, messages, temperature=0.1, max_tokens=2048):
            return """```json
{
  "facts": [
    {"content": "Works at Google", "category": "work", "confidence": 0.95},
    {"content": "Likes Python programming", "category": "hobby", "confidence": 0.9}
  ],
  "episodes": []
}
```"""

    db = Database.__new__(Database)
    db.engine = db_session.bind
    db.session_factory = lambda: db_session

    facade = ConversationsFacade(
        db,
        _auto_extract=True,
        _embedding=mock_embedding,
        _llm=MockBatchLLM(),
        _graph_enabled=False,
    )

    # Add batch messages
    sid, ids = await facade.add_messages_batch(
        user_id="batch_user",
        messages=[
            {"role": "user", "content": "I work at Google"},
            {"role": "assistant", "content": "Great!"},
            {"role": "user", "content": "I love Python programming"},
        ],
    )

    # Verify memories were extracted
    result = await db_session.execute(
        text("SELECT COUNT(*) FROM embeddings WHERE user_id = :uid AND memory_type = 'fact'"),
        {"uid": "batch_user"},
    )
    count = result.scalar()
    assert count >= 1  # At least some facts extracted
