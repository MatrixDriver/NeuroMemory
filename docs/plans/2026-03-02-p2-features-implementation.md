# P2 Memory Enhancement Suite — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add 5 transparent memory enhancements: dual timeline, prospective memory lifecycle, procedural memory extraction, Zettelkasten inter-linking, and two-stage reflection.

**Architecture:** All features are additive layers on existing services. Metadata stored in JSONB `metadata_` — no schema migrations. Features integrate into existing ingest/recall/digest flows transparently.

**Tech Stack:** Python 3.13, SQLAlchemy 2.0 async, PostgreSQL + pgvector, pytest (asyncio_mode=auto)

**Test DB:** PostgreSQL on port 5436 (`TEST_DATABASE_URL` in `conftest.py`)

---

### Task 1: Dual Timeline — Extraction (event_time for facts)

**Files:**
- Modify: `neuromem/services/memory_extraction.py:292-403` (zh prompt), `neuromem/services/memory_extraction.py:405-516` (en prompt)
- Modify: `neuromem/services/memory_extraction.py:621-753` (`_store_facts`)
- Test: `tests/test_p2_dual_timeline.py`

**Step 1: Write the failing test**

Create `tests/test_p2_dual_timeline.py`:

```python
"""Tests for P2-3: Dual Timeline — event_time extraction and storage."""

import json
import pytest
from neuromem.providers.llm import LLMProvider
from neuromem.services.conversation import ConversationService
from neuromem.services.memory_extraction import MemoryExtractionService
from sqlalchemy import text


class MockLLMWithEventTime(LLMProvider):
    def __init__(self, response: str):
        self._response = response

    async def chat(self, messages, temperature=0.1, max_tokens=2048) -> str:
        return self._response


@pytest.mark.asyncio
async def test_fact_event_time_stored_in_metadata(db_session, mock_embedding):
    """Facts with event_time from LLM should store it in metadata_.event_time."""
    llm = MockLLMWithEventTime(response=json.dumps({
        "facts": [
            {
                "content": "用户上周三去了北京",
                "category": "location",
                "temporality": "historical",
                "confidence": 0.9,
                "importance": 5,
                "event_time": "2026-02-25",
            }
        ],
        "episodes": [],
    }))

    conv_svc = ConversationService(db_session)
    _, _ = await conv_svc.add_messages_batch(
        user_id="u1",
        messages=[{"role": "user", "content": "我上周三去了北京"}],
    )
    messages = await conv_svc.get_unextracted_messages(user_id="u1")

    svc = MemoryExtractionService(db_session, mock_embedding, llm)
    result = await svc.extract_from_messages(user_id="u1", messages=messages)
    assert result["facts_extracted"] == 1

    row = (await db_session.execute(
        text("SELECT metadata FROM memories WHERE user_id = 'u1' AND memory_type = 'fact' LIMIT 1")
    )).first()
    assert row is not None
    meta = row.metadata
    assert meta.get("event_time") == "2026-02-25"


@pytest.mark.asyncio
async def test_fact_without_event_time_has_no_event_time_key(db_session, mock_embedding):
    """Facts without event_time from LLM should not have event_time in metadata."""
    llm = MockLLMWithEventTime(response=json.dumps({
        "facts": [
            {
                "content": "用户是程序员",
                "category": "work",
                "temporality": "current",
                "confidence": 0.95,
                "importance": 7,
            }
        ],
        "episodes": [],
    }))

    conv_svc = ConversationService(db_session)
    _, _ = await conv_svc.add_messages_batch(
        user_id="u2",
        messages=[{"role": "user", "content": "我是程序员"}],
    )
    messages = await conv_svc.get_unextracted_messages(user_id="u2")

    svc = MemoryExtractionService(db_session, mock_embedding, llm)
    await svc.extract_from_messages(user_id="u2", messages=messages)

    row = (await db_session.execute(
        text("SELECT metadata FROM memories WHERE user_id = 'u2' AND memory_type = 'fact' LIMIT 1")
    )).first()
    assert row is not None
    assert "event_time" not in row.metadata
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_p2_dual_timeline.py -v`
Expected: FAIL — `event_time` not in metadata because `_store_facts` doesn't read it from LLM output yet.

**Step 3: Implement — store event_time in _store_facts**

In `neuromem/services/memory_extraction.py`, in `_store_facts` method, after line 726 (entities handling), add:

```python
                event_time = fact.get("event_time")
                if event_time:
                    meta["event_time"] = event_time
```

**Step 4: Update extraction prompts to request event_time**

In `_build_zh_prompt`, in the Facts format line (around line 332), add `"event_time"` field to the JSON format description. Insert after the temporality description:

```
   - event_time: 事实发生的实际时间（ISO 日期格式如 "2026-02-25"），从对话中的时间表达推算。如果无法确定具体日期则设为 null
```

In `_build_en_prompt`, add the same in English (around line 445):

```
   - event_time: The actual date when the fact occurred (ISO date like "2026-02-25"), computed from time expressions in conversation. Set to null if the date cannot be determined
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_p2_dual_timeline.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add tests/test_p2_dual_timeline.py neuromem/services/memory_extraction.py
git commit -m "feat: P2-3 dual timeline — extract and store event_time for facts"
```

---

### Task 2: Dual Timeline — Recall (event_time-aware recency)

**Files:**
- Modify: `neuromem/services/search.py:375-435` (scored_search SQL)
- Test: `tests/test_p2_dual_timeline.py` (append)

**Step 1: Write the failing test**

Append to `tests/test_p2_dual_timeline.py`:

```python
from datetime import datetime, timezone
from neuromem.services.search import SearchService


@pytest.mark.asyncio
async def test_scored_search_uses_event_time_for_recency(db_session, mock_embedding):
    """When a memory has metadata.event_time, recency bonus should be based on it, not created_at."""
    from neuromem.models.memory import Memory
    import hashlib

    now = datetime.now(timezone.utc)
    content = "用户上个月去了上海出差"
    vec = await mock_embedding.embed(content)

    # Memory created now, but event happened 60 days ago
    mem = Memory(
        user_id="u_recency",
        content=content,
        embedding=vec,
        memory_type="fact",
        metadata_={"event_time": "2026-01-01", "importance": 5},
        valid_from=now,
        content_hash=hashlib.md5(content.encode()).hexdigest(),
        valid_at=now,
    )
    db_session.add(mem)
    await db_session.flush()

    svc = SearchService(db_session, mock_embedding)
    results = await svc.scored_search(user_id="u_recency", query="上海出差", limit=5)

    assert len(results) >= 1
    # The result should have event_time passed through metadata
    assert results[0]["metadata"].get("event_time") == "2026-01-01"
```

**Step 2: Run test to verify it passes (baseline)**

Run: `pytest tests/test_p2_dual_timeline.py::test_scored_search_uses_event_time_for_recency -v`
Expected: PASS (metadata is already returned; this validates the plumbing).

**Step 3: Implement — use event_time for recency calculation in SQL**

In `neuromem/services/search.py`, in the `scored_search` method, modify the recency bonus SQL (around line 403-406).

Replace the recency calculation:
```sql
0.15 * EXP(
    -EXTRACT(EPOCH FROM (NOW() - created_at))
    / (:decay_rate * (1 + COALESCE((metadata->'emotion'->>'arousal')::float, 0) * 0.5))
) AS recency,
```

With event_time-aware version:
```sql
0.15 * EXP(
    -EXTRACT(EPOCH FROM (NOW() - COALESCE(
        (metadata->>'event_time')::timestamp,
        created_at
    )))
    / (:decay_rate * (1 + COALESCE((metadata->'emotion'->>'arousal')::float, 0) * 0.5))
) AS recency,
```

Apply the same change to the recency term inside the final score formula (around line 414-417).

**Step 4: Run all dual timeline tests**

Run: `pytest tests/test_p2_dual_timeline.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add neuromem/services/search.py tests/test_p2_dual_timeline.py
git commit -m "feat: P2-3 dual timeline — recency bonus uses event_time when available"
```

---

### Task 3: Prospective Memory — Recall Penalty + Digest Auto-expire

**Files:**
- Modify: `neuromem/services/search.py:375-435` (scored_search — prospective penalty)
- Modify: `neuromem/services/reflection.py:340-450` (_run_reflection_steps — expire prospective)
- Test: `tests/test_p2_prospective.py`

**Step 1: Write the failing test for recall penalty**

Create `tests/test_p2_prospective.py`:

```python
"""Tests for P2-5: Prospective Memory — recall penalty and auto-expiry."""

import hashlib
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from neuromem.models.memory import Memory
from neuromem.services.search import SearchService


@pytest.mark.asyncio
async def test_expired_prospective_fact_gets_score_penalty(db_session, mock_embedding):
    """Prospective facts with event_time in the past should get 0.5x score penalty."""
    now = datetime.now(timezone.utc)
    content = "用户计划去年考 AWS 认证"
    vec = await mock_embedding.embed(content)

    mem = Memory(
        user_id="u_prosp",
        content=content,
        embedding=vec,
        memory_type="fact",
        metadata_={
            "temporality": "prospective",
            "event_time": "2025-01-01",  # past
            "importance": 7,
        },
        valid_from=now,
        content_hash=hashlib.md5(content.encode()).hexdigest(),
        valid_at=now,
    )
    db_session.add(mem)

    content2 = "用户是 AWS 架构师"
    vec2 = await mock_embedding.embed(content2)
    mem2 = Memory(
        user_id="u_prosp",
        content=content2,
        embedding=vec2,
        memory_type="fact",
        metadata_={"temporality": "current", "importance": 7},
        valid_from=now,
        content_hash=hashlib.md5(content2.encode()).hexdigest(),
        valid_at=now,
    )
    db_session.add(mem2)
    await db_session.flush()

    svc = SearchService(db_session, mock_embedding)
    results = await svc.scored_search(user_id="u_prosp", query="AWS", limit=5)

    # Both should appear, but prospective-expired one should score lower
    assert len(results) >= 1
    # Find each result
    prosp = [r for r in results if "计划" in r["content"]]
    current = [r for r in results if "架构师" in r["content"]]
    if prosp and current:
        assert prosp[0]["score"] < current[0]["score"], \
            "Expired prospective fact should score lower than current fact"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_p2_prospective.py::test_expired_prospective_fact_gets_score_penalty -v`
Expected: May fail if the mock vectors produce identical scores — adjust assertion if needed.

**Step 3: Implement prospective penalty in scored_search**

In `neuromem/services/search.py`, in the `scored_search` final score formula (around line 412-430), wrap the entire score with a prospective penalty multiplier:

After the final `AS score` expression, add a CASE wrapper. Replace the final score calculation block with:

```sql
                   -- prospective_penalty: 0.5x for expired prospective facts
                   CASE
                       WHEN metadata->>'temporality' = 'prospective'
                            AND (metadata->>'event_time') IS NOT NULL
                            AND (metadata->>'event_time')::timestamp < NOW()
                       THEN 0.5
                       ELSE 1.0
                   END
                   *
                   LEAST(vector_score + CASE WHEN bm25_score > 0 THEN 0.05 ELSE 0 END, 1.0)
                   * (1.0
                      ... rest of bonuses ...
                   ) AS score
```

**Step 4: Write test for digest auto-expire**

Append to `tests/test_p2_prospective.py`:

```python
from neuromem.providers.llm import LLMProvider
from neuromem.services.reflection import ReflectionService


class MockReflectionLLM(LLMProvider):
    async def chat(self, messages, temperature=0.1, max_tokens=2048) -> str:
        return json.dumps({
            "new_trends": [], "new_behaviors": [],
            "reinforcements": [], "contradictions": [], "upgrades": [],
        })


@pytest.mark.asyncio
async def test_digest_expires_prospective_to_historical(db_session, mock_embedding):
    """Reflection should mark expired prospective facts as historical."""
    now = datetime.now(timezone.utc)
    content = "用户计划去年学日语"
    vec = await mock_embedding.embed(content)

    mem = Memory(
        user_id="u_expire",
        content=content,
        embedding=vec,
        memory_type="fact",
        metadata_={
            "temporality": "prospective",
            "event_time": "2025-06-01",  # past
            "importance": 5,
        },
        valid_from=now,
        content_hash=hashlib.md5(content.encode()).hexdigest(),
        valid_at=now,
    )
    db_session.add(mem)
    await db_session.flush()

    llm = MockReflectionLLM()
    svc = ReflectionService(db_session, mock_embedding, llm)
    await svc.reflect(user_id="u_expire", force=True)

    row = (await db_session.execute(
        text("SELECT metadata FROM memories WHERE user_id = 'u_expire' AND memory_type = 'fact' LIMIT 1")
    )).first()
    assert row is not None
    assert row.metadata.get("temporality") == "historical"
```

**Step 5: Implement auto-expire in reflection**

In `neuromem/services/reflection.py`, in `_run_reflection_steps`, add a new step after the trend expiry block (after line 358, before `if not new_memories`):

```python
        # Step: Expire prospective facts whose event_time has passed
        await self._expire_prospective_facts(user_id)
```

Add the private method to `ReflectionService`:

```python
    async def _expire_prospective_facts(self, user_id: str) -> int:
        """Mark prospective facts as historical when their event_time has passed."""
        result = await self.db.execute(
            sql_text(
                "UPDATE memories SET metadata = jsonb_set(metadata, '{temporality}', '\"historical\"') "
                "WHERE user_id = :uid AND memory_type = 'fact' "
                "AND metadata->>'temporality' = 'prospective' "
                "AND (metadata->>'event_time') IS NOT NULL "
                "AND (metadata->>'event_time')::timestamp < NOW() "
                "RETURNING id"
            ),
            {"uid": user_id},
        )
        rows = result.fetchall()
        if rows:
            logger.info("Expired %d prospective facts to historical for user=%s", len(rows), user_id)
        return len(rows)
```

**Step 6: Run all prospective tests**

Run: `pytest tests/test_p2_prospective.py -v`
Expected: PASS

**Step 7: Commit**

```bash
git add tests/test_p2_prospective.py neuromem/services/search.py neuromem/services/reflection.py
git commit -m "feat: P2-5 prospective memory — recall penalty for expired + auto-expire in digest"
```

---

### Task 4: Procedural Memory — Extraction Enhancement

**Files:**
- Modify: `neuromem/services/memory_extraction.py:292-403` (zh prompt), `neuromem/services/memory_extraction.py:405-516` (en prompt)
- Modify: `neuromem/services/memory_extraction.py:621-753` (`_store_facts`)
- Test: `tests/test_p2_procedural.py`

**Step 1: Write the failing test**

Create `tests/test_p2_procedural.py`:

```python
"""Tests for P2-4: Procedural Memory — workflow extraction."""

import json
import pytest
from sqlalchemy import text

from neuromem.providers.llm import LLMProvider
from neuromem.services.conversation import ConversationService
from neuromem.services.memory_extraction import MemoryExtractionService


class MockLLMProcedural(LLMProvider):
    def __init__(self, response: str):
        self._response = response

    async def chat(self, messages, temperature=0.1, max_tokens=2048) -> str:
        return self._response


@pytest.mark.asyncio
async def test_workflow_fact_has_procedure_steps(db_session, mock_embedding):
    """Workflow facts should have procedure_steps in metadata."""
    llm = MockLLMProcedural(response=json.dumps({
        "facts": [
            {
                "content": "用户写代码前先画架构图 → 写 POC → 跑测试 → 提 PR",
                "category": "workflow",
                "temporality": "current",
                "confidence": 0.85,
                "importance": 6,
                "procedure_steps": ["画架构图", "写 POC", "跑测试", "提 PR"],
            }
        ],
        "episodes": [],
    }))

    conv_svc = ConversationService(db_session)
    _, _ = await conv_svc.add_messages_batch(
        user_id="u_proc",
        messages=[{"role": "user", "content": "我写代码前总是先画架构图，然后写POC，跑测试，最后提PR"}],
    )
    messages = await conv_svc.get_unextracted_messages(user_id="u_proc")

    svc = MemoryExtractionService(db_session, mock_embedding, llm)
    result = await svc.extract_from_messages(user_id="u_proc", messages=messages)
    assert result["facts_extracted"] == 1

    row = (await db_session.execute(
        text("SELECT metadata FROM memories WHERE user_id = 'u_proc' AND memory_type = 'fact' LIMIT 1")
    )).first()
    assert row is not None
    meta = row.metadata
    assert meta.get("category") == "workflow"
    assert meta.get("procedure_steps") == ["画架构图", "写 POC", "跑测试", "提 PR"]


@pytest.mark.asyncio
async def test_non_workflow_fact_has_no_procedure_steps(db_session, mock_embedding):
    """Normal facts should not have procedure_steps."""
    llm = MockLLMProcedural(response=json.dumps({
        "facts": [
            {
                "content": "用户喜欢 Python",
                "category": "skill",
                "temporality": "current",
                "confidence": 0.9,
                "importance": 5,
            }
        ],
        "episodes": [],
    }))

    conv_svc = ConversationService(db_session)
    _, _ = await conv_svc.add_messages_batch(
        user_id="u_proc2",
        messages=[{"role": "user", "content": "我喜欢Python"}],
    )
    messages = await conv_svc.get_unextracted_messages(user_id="u_proc2")

    svc = MemoryExtractionService(db_session, mock_embedding, llm)
    await svc.extract_from_messages(user_id="u_proc2", messages=messages)

    row = (await db_session.execute(
        text("SELECT metadata FROM memories WHERE user_id = 'u_proc2' AND memory_type = 'fact' LIMIT 1")
    )).first()
    assert row is not None
    assert "procedure_steps" not in row.metadata
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_p2_procedural.py -v`
Expected: FAIL — `_store_facts` doesn't read `procedure_steps` or `workflow` category.

**Step 3: Implement — store procedure_steps in _store_facts**

In `neuromem/services/memory_extraction.py`, `_store_facts`, after the `event_time` block added in Task 1, add:

```python
                procedure_steps = fact.get("procedure_steps")
                if procedure_steps and isinstance(procedure_steps, list):
                    meta["procedure_steps"] = procedure_steps
```

**Step 4: Update extraction prompts**

In `_build_zh_prompt`, add to the Facts category list (around line 333):

After `values` in the category options, add `workflow`. Then add this description line after the temporality section:

```
   - procedure_steps: 如果 category 为 "workflow"，提取操作步骤列表（如 ["步骤1", "步骤2", "步骤3"]）。非 workflow 类别不需要此字段
```

In `_build_en_prompt`, add equivalent (around line 447):

After `values` in category options, add `workflow`. Then:

```
   - procedure_steps: If category is "workflow", extract the step list (e.g. ["step1", "step2", "step3"]). Not needed for other categories
```

**Step 5: Run tests**

Run: `pytest tests/test_p2_procedural.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add tests/test_p2_procedural.py neuromem/services/memory_extraction.py
git commit -m "feat: P2-4 procedural memory — extract workflow steps in facts"
```

---

### Task 5: Zettelkasten — Link Creation in Reflection

**Files:**
- Modify: `neuromem/services/reflection.py:59-157` (prompt template)
- Modify: `neuromem/services/reflection.py:340-450` (_run_reflection_steps)
- Test: `tests/test_p2_zettelkasten.py`

**Step 1: Write the failing test**

Create `tests/test_p2_zettelkasten.py`:

```python
"""Tests for P2-1: Zettelkasten — memory inter-linking during reflection."""

import hashlib
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from neuromem.models.memory import Memory
from neuromem.providers.llm import LLMProvider
from neuromem.services.reflection import ReflectionService


class MockZettelLLM(LLMProvider):
    """Mock LLM that returns links in reflection output."""

    def __init__(self, main_response: str):
        self._main_response = main_response
        self._call_count = 0

    async def chat(self, messages, temperature=0.1, max_tokens=2048) -> str:
        self._call_count += 1
        return self._main_response


@pytest.mark.asyncio
async def test_reflection_creates_memory_links(db_session, mock_embedding):
    """Reflection should create bidirectional links between related memories."""
    now = datetime.now(timezone.utc)

    # Create two related memories
    mems = []
    for content in ["用户在 Google 工作", "用户负责搜索团队"]:
        vec = await mock_embedding.embed(content)
        m = Memory(
            user_id="u_zett",
            content=content,
            embedding=vec,
            memory_type="fact",
            metadata_={"importance": 7},
            valid_from=now,
            content_hash=hashlib.md5(content.encode()).hexdigest(),
            valid_at=now,
        )
        db_session.add(m)
        mems.append(m)
    await db_session.flush()

    id0, id1 = str(mems[0].id), str(mems[1].id)

    llm_response = json.dumps({
        "new_trends": [],
        "new_behaviors": [],
        "reinforcements": [],
        "contradictions": [],
        "upgrades": [],
        "links": [
            {"source_id": id0, "target_id": id1, "relation": "same topic"},
        ],
    })

    llm = MockZettelLLM(main_response=llm_response)
    svc = ReflectionService(db_session, mock_embedding, llm)
    await svc.reflect(user_id="u_zett", force=True)

    # Check bidirectional links
    row0 = (await db_session.execute(
        text("SELECT metadata FROM memories WHERE id = :id"),
        {"id": mems[0].id},
    )).first()
    row1 = (await db_session.execute(
        text("SELECT metadata FROM memories WHERE id = :id"),
        {"id": mems[1].id},
    )).first()

    assert row0 is not None
    related0 = row0.metadata.get("related_memories", [])
    assert any(r["id"] == id1 for r in related0)

    assert row1 is not None
    related1 = row1.metadata.get("related_memories", [])
    assert any(r["id"] == id0 for r in related1)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_p2_zettelkasten.py -v`
Expected: FAIL — reflection doesn't process `links` from LLM output.

**Step 3: Implement link creation in reflection**

In `neuromem/services/reflection.py`:

1. Add to `REFLECTION_PROMPT_TEMPLATE` (before the closing ```json block, around line 148), add `links` to the output format:

```
  "links": [
    {{
      "source_id": "记忆ID-A",
      "target_id": "记忆ID-B",
      "relation": "关联类型（如: elaborates, contradicts, same_topic, causal）"
    }}
  ]
```

2. Add instructions in the prompt (after the upgrades section, around line 110):

```
### 6. 记忆关联检测 (links)
- 检查新增记忆之间、以及新增记忆与已有记忆之间是否存在语义关联
- 关联类型: elaborates（补充说明）、contradicts（矛盾）、same_topic（同主题）、causal（因果）
- 只标注有明确关联的记忆对，不要过度关联
```

3. In `_run_reflection_steps`, after processing upgrades (around line 425), add link processing:

```python
        # Step: Process memory links (Zettelkasten)
        for link in llm_result.get("links", []):
            await self._create_memory_link(
                source_id=link.get("source_id"),
                target_id=link.get("target_id"),
                relation=link.get("relation", "related"),
            )
```

4. Add the helper method to `ReflectionService`:

```python
    async def _create_memory_link(
        self,
        source_id: str | None,
        target_id: str | None,
        relation: str = "related",
    ) -> None:
        """Create bidirectional link between two memories via metadata."""
        if not source_id or not target_id:
            return
        try:
            # Add target to source's related_memories
            await self.db.execute(
                sql_text(
                    """UPDATE memories
                    SET metadata = jsonb_set(
                        COALESCE(metadata, '{}'),
                        '{related_memories}',
                        COALESCE(metadata->'related_memories', '[]'::jsonb) || :link_json::jsonb
                    )
                    WHERE id = :id
                    AND NOT (COALESCE(metadata->'related_memories', '[]'::jsonb) @> :link_json::jsonb)"""
                ),
                {"id": source_id, "link_json": json.dumps([{"id": target_id, "relation": relation}])},
            )
            # Add source to target's related_memories (reverse direction)
            await self.db.execute(
                sql_text(
                    """UPDATE memories
                    SET metadata = jsonb_set(
                        COALESCE(metadata, '{}'),
                        '{related_memories}',
                        COALESCE(metadata->'related_memories', '[]'::jsonb) || :link_json::jsonb
                    )
                    WHERE id = :id
                    AND NOT (COALESCE(metadata->'related_memories', '[]'::jsonb) @> :link_json::jsonb)"""
                ),
                {"id": target_id, "link_json": json.dumps([{"id": source_id, "relation": relation}])},
            )
        except Exception as e:
            logger.warning("Failed to create memory link %s↔%s: %s", source_id, target_id, e)
```

**Step 5: Run tests**

Run: `pytest tests/test_p2_zettelkasten.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add tests/test_p2_zettelkasten.py neuromem/services/reflection.py
git commit -m "feat: P2-1 zettelkasten — create bidirectional memory links during reflection"
```

---

### Task 6: Zettelkasten — Recall Enhancement (1-hop expansion)

**Files:**
- Modify: `neuromem/services/search.py` (new method `expand_related_memories`)
- Modify: `neuromem/_core.py:1169-1222` (recall merge step)
- Test: `tests/test_p2_zettelkasten.py` (append)

**Step 1: Write the failing test**

Append to `tests/test_p2_zettelkasten.py`:

```python
from neuromem.services.search import SearchService


@pytest.mark.asyncio
async def test_recall_expands_related_memories(db_session, mock_embedding):
    """Recall should fetch 1-hop related memories and add them with a small bonus."""
    now = datetime.now(timezone.utc)

    # Create memory A with a link to memory B
    content_a = "用户在 Google 工作"
    content_b = "用户负责搜索团队的后端架构"
    vec_a = await mock_embedding.embed(content_a)
    vec_b = await mock_embedding.embed(content_b)

    mem_a = Memory(
        user_id="u_expand",
        content=content_a,
        embedding=vec_a,
        memory_type="fact",
        metadata_={"importance": 7},
        valid_from=now,
        content_hash=hashlib.md5(content_a.encode()).hexdigest(),
        valid_at=now,
    )
    db_session.add(mem_a)
    await db_session.flush()
    id_a = str(mem_a.id)

    mem_b = Memory(
        user_id="u_expand",
        content=content_b,
        embedding=vec_b,
        memory_type="fact",
        metadata_={"importance": 7},
        valid_from=now,
        content_hash=hashlib.md5(content_b.encode()).hexdigest(),
        valid_at=now,
    )
    db_session.add(mem_b)
    await db_session.flush()
    id_b = str(mem_b.id)

    # Set up link: A -> B
    mem_a.metadata_ = {**mem_a.metadata_, "related_memories": [{"id": id_b, "relation": "elaborates"}]}
    await db_session.flush()

    svc = SearchService(db_session, mock_embedding)
    results = await svc.scored_search(user_id="u_expand", query="Google 工作", limit=5)

    # At minimum, the direct hit should be in results
    assert len(results) >= 1
```

**Step 2: Implement related memory expansion in _core.py**

In `neuromem/_core.py`, after the vector results dedup loop (around line 1222, before conversation merge), add:

```python
        # Zettelkasten: 1-hop related memory expansion
        related_ids_to_fetch: list[str] = []
        for r in list(merged):
            related = (r.get("metadata") or {}).get("related_memories", [])
            for link in related[:3]:  # Max 3 links per memory
                linked_id = link.get("id")
                if linked_id and linked_id not in seen_contents:
                    related_ids_to_fetch.append(linked_id)

        if related_ids_to_fetch:
            # Limit total expansion to 3 memories
            related_ids_to_fetch = related_ids_to_fetch[:3]
            try:
                placeholders = ", ".join(f":rid_{i}" for i in range(len(related_ids_to_fetch)))
                params = {f"rid_{i}": rid for i, rid in enumerate(related_ids_to_fetch)}
                params["user_id"] = user_id
                from sqlalchemy import text as sql_text
                result = await session.execute(
                    sql_text(
                        f"SELECT id, content, memory_type, metadata, created_at, extracted_timestamp "
                        f"FROM memories WHERE id IN ({placeholders}) AND user_id = :user_id"
                    ),
                    params,
                )
                for row in result.fetchall():
                    content = row.content
                    if content not in seen_contents:
                        seen_contents.add(content)
                        merged.append({
                            "id": str(row.id),
                            "content": content,
                            "memory_type": row.memory_type,
                            "metadata": row.metadata,
                            "created_at": row.created_at,
                            "score": 0.03,  # Small bonus for linked memories
                            "source": "linked",
                        })
            except Exception as e:
                logger.warning("Zettelkasten expansion failed: %s", e)
```

Note: The exact placement in `_core.py` needs to be inside the `recall` method's session context. Check the session variable name — it may use `self._db.session()` context manager. The expansion query should use the same session as the recall method. Look at how `_fetch_vector_memories` gets its session.

Actually, since `recall()` in `_core.py` doesn't directly hold a session (it delegates to `_fetch_vector_memories` which creates its own), the expansion should be done as a post-processing step in the `recall()` method using `self._db.session()`:

```python
        # Zettelkasten: 1-hop related memory expansion
        related_ids_to_fetch: list[str] = []
        for r in list(merged):
            related = (r.get("metadata") or {}).get("related_memories", [])
            for link in related[:3]:
                linked_id = link.get("id")
                if linked_id:
                    # Check by ID, not content
                    existing_ids = {r.get("id") for r in merged}
                    if linked_id not in existing_ids:
                        related_ids_to_fetch.append(linked_id)

        if related_ids_to_fetch:
            related_ids_to_fetch = list(set(related_ids_to_fetch))[:3]
            try:
                async with self._db.session() as sess:
                    placeholders = ", ".join(f":rid_{i}" for i in range(len(related_ids_to_fetch)))
                    params = {f"rid_{i}": rid for i, rid in enumerate(related_ids_to_fetch)}
                    params["user_id"] = user_id
                    from sqlalchemy import text as sql_text
                    result = await sess.execute(
                        sql_text(
                            f"SELECT id, content, memory_type, metadata, created_at, extracted_timestamp "
                            f"FROM memories WHERE id IN ({placeholders}) AND user_id = :user_id"
                        ),
                        params,
                    )
                    for row in result.fetchall():
                        content = row.content
                        if content not in seen_contents:
                            seen_contents.add(content)
                            merged.append({
                                "id": str(row.id),
                                "content": content,
                                "memory_type": row.memory_type,
                                "metadata": row.metadata,
                                "created_at": row.created_at,
                                "score": 0.03,
                                "source": "linked",
                            })
            except Exception as e:
                logger.warning("Zettelkasten expansion failed: %s", e)
```

**Step 3: Run tests**

Run: `pytest tests/test_p2_zettelkasten.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add neuromem/_core.py tests/test_p2_zettelkasten.py
git commit -m "feat: P2-1 zettelkasten — 1-hop related memory expansion in recall"
```

---

### Task 7: Two-Stage Reflection

**Files:**
- Modify: `neuromem/services/reflection.py`
- Test: `tests/test_p2_two_stage_reflection.py`

**Step 1: Write the failing test**

Create `tests/test_p2_two_stage_reflection.py`:

```python
"""Tests for P2-2: Two-Stage Reflection — question-then-evidence approach."""

import hashlib
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from neuromem.models.memory import Memory
from neuromem.providers.embedding import EmbeddingProvider
from neuromem.providers.llm import LLMProvider
from neuromem.services.reflection import ReflectionService


class MockTwoStageLLM(LLMProvider):
    """Mock LLM that tracks calls for two-stage verification."""

    def __init__(self, stage1_response: str, stage2_response: str):
        self._responses = [stage1_response, stage2_response]
        self._call_count = 0
        self.call_history: list[list[dict]] = []

    async def chat(self, messages, temperature=0.1, max_tokens=2048) -> str:
        self._call_count += 1
        self.call_history.append(messages)
        if self._call_count <= len(self._responses):
            return self._responses[self._call_count - 1]
        return '{"new_trends":[],"new_behaviors":[],"reinforcements":[],"contradictions":[],"upgrades":[],"links":[]}'


@pytest.mark.asyncio
async def test_two_stage_reflection_makes_two_llm_calls(db_session, mock_embedding):
    """When importance_accumulated trigger fires, reflection should use two-stage (2 LLM calls)."""
    now = datetime.now(timezone.utc)

    # Insert enough high-importance memories to trigger importance_accumulated
    for i in range(6):
        content = f"用户讨论了重要的技术决策 {i}"
        vec = await mock_embedding.embed(content)
        m = Memory(
            user_id="u_2stage",
            content=content,
            embedding=vec,
            memory_type="fact",
            metadata_={"importance": 8},
            valid_from=now,
            content_hash=hashlib.md5(content.encode()).hexdigest(),
            valid_at=now,
        )
        db_session.add(m)
    await db_session.flush()

    stage1_response = json.dumps({
        "questions": [
            "用户的技术栈偏好有变化吗？",
            "用户最近的工作重心是什么？",
        ]
    })
    stage2_response = json.dumps({
        "new_trends": [
            {
                "content": "频繁讨论技术决策",
                "evidence_ids": [],
                "window_days": 30,
                "context": "work",
            }
        ],
        "new_behaviors": [],
        "reinforcements": [],
        "contradictions": [],
        "upgrades": [],
        "links": [],
    })

    llm = MockTwoStageLLM(stage1_response, stage2_response)
    svc = ReflectionService(db_session, mock_embedding, llm)

    result = await svc.reflect(user_id="u_2stage", force=False)

    # Should have triggered (importance >= 30: 6 * 8 = 48)
    assert result["triggered"] is True
    assert result["trigger_type"] == "importance_accumulated"
    # Two-stage: should have made 2 LLM calls
    assert llm._call_count == 2
    assert result["traits_created"] >= 1


@pytest.mark.asyncio
async def test_single_stage_for_non_important_reflection(db_session, mock_embedding):
    """Non-important reflections (force=True, first_time) should use single-stage (1 LLM call)."""
    now = datetime.now(timezone.utc)

    content = "用户喜欢咖啡"
    vec = await mock_embedding.embed(content)
    m = Memory(
        user_id="u_1stage",
        content=content,
        embedding=vec,
        memory_type="fact",
        metadata_={"importance": 3},
        valid_from=now,
        content_hash=hashlib.md5(content.encode()).hexdigest(),
        valid_at=now,
    )
    db_session.add(m)
    await db_session.flush()

    single_response = json.dumps({
        "new_trends": [],
        "new_behaviors": [],
        "reinforcements": [],
        "contradictions": [],
        "upgrades": [],
        "links": [],
    })

    llm = MockTwoStageLLM(single_response, single_response)
    svc = ReflectionService(db_session, mock_embedding, llm)
    # force=True with low importance → single-stage
    result = await svc.reflect(user_id="u_1stage", force=True)

    assert result["triggered"] is True
    # force trigger → single-stage → 1 LLM call
    assert llm._call_count == 1
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_p2_two_stage_reflection.py -v`
Expected: FAIL — currently all reflections use single-stage, so the importance_accumulated test will show 1 LLM call, not 2.

**Step 3: Implement two-stage reflection**

In `neuromem/services/reflection.py`:

1. In `_run_reflection_steps`, change the LLM call section (around line 367-368) to branch on trigger type:

```python
        # Step 2: LLM call — two-stage for important reflections, single-stage otherwise
        existing_traits = await self._load_existing_traits(user_id)

        use_two_stage = trigger_type in ("importance_accumulated",)
        if use_two_stage:
            llm_result = await self._two_stage_reflect(user_id, new_memories, existing_traits)
        else:
            llm_result = await self._call_reflection_llm(new_memories, existing_traits)
```

2. Add the `_two_stage_reflect` method:

```python
    async def _two_stage_reflect(
        self,
        user_id: str,
        new_memories: list[dict],
        existing_traits: list[dict],
    ) -> dict | None:
        """Two-stage reflection: generate questions, retrieve evidence, then analyze.

        Stage 1: LLM generates 3-5 key questions about the user.
        Stage 2: Questions + retrieved evidence + new memories → trait analysis.
        """
        # Stage 1: Generate questions
        memory_summary = json.dumps(
            [{"id": m["id"], "content": m["content"]} for m in new_memories[:20]],
            ensure_ascii=False,
        )
        question_prompt = (
            f"根据以下用户近期记忆，生成 3-5 个关键问题来深入了解该用户。\n\n"
            f"记忆:\n{memory_summary}\n\n"
            f"只返回 JSON:\n```json\n{{\"questions\": [\"问题1\", \"问题2\", ...]}}\n```"
        )
        try:
            q_result = await self._llm.chat(
                messages=[
                    {"role": "system", "content": "你是一个用户分析引擎。生成关于用户的关键问题。只返回 JSON。"},
                    {"role": "user", "content": question_prompt},
                ],
                temperature=0.3,
                max_tokens=512,
            )
            questions = self._parse_questions(q_result)
        except Exception as e:
            logger.warning("Two-stage reflection stage 1 failed: %s, falling back to single-stage", e)
            return await self._call_reflection_llm(new_memories, existing_traits)

        if not questions:
            return await self._call_reflection_llm(new_memories, existing_traits)

        # Stage 2: Retrieve evidence for each question
        from neuromem.services.search import SearchService
        search_svc = SearchService(self.db, self._embedding)
        evidence: list[dict] = []
        seen_ids: set[str] = set()
        for q in questions[:5]:
            try:
                hits = await search_svc.scored_search(user_id=user_id, query=q, limit=3)
                for h in hits:
                    if h["id"] not in seen_ids:
                        seen_ids.add(h["id"])
                        evidence.append({"id": h["id"], "content": h["content"], "score": h["score"]})
            except Exception:
                pass

        # Build enriched prompt with evidence
        enriched_memories = new_memories + [
            {"id": e["id"], "content": f"[历史证据] {e['content']}", "memory_type": "evidence"}
            for e in evidence[:10]
        ]

        return await self._call_reflection_llm(enriched_memories, existing_traits)

    def _parse_questions(self, result_text: str) -> list[str]:
        """Parse question generation result."""
        try:
            t = result_text.strip()
            if "```json" in t:
                start = t.find("```json") + 7
                end = t.find("```", start)
                t = t[start:end].strip()
            elif "```" in t:
                start = t.find("```") + 3
                end = t.find("```", start)
                t = t[start:end].strip()
            result = json.loads(t)
            questions = result.get("questions", [])
            return [q for q in questions if isinstance(q, str)]
        except Exception as e:
            logger.warning("Failed to parse questions: %s", e)
            return []
```

**Step 4: Run tests**

Run: `pytest tests/test_p2_two_stage_reflection.py -v`
Expected: PASS

**Step 5: Run the full test suite to check for regressions**

Run: `pytest tests/ -v -m "not slow" --timeout=60`
Expected: All existing tests pass.

**Step 6: Commit**

```bash
git add tests/test_p2_two_stage_reflection.py neuromem/services/reflection.py
git commit -m "feat: P2-2 two-stage reflection — question-then-evidence for important reflections"
```

---

### Task 8: Integration Test + Final Verification

**Files:**
- Test: `tests/test_p2_integration.py`

**Step 1: Write integration test**

Create `tests/test_p2_integration.py`:

```python
"""Integration tests — verify P2 features work together end-to-end."""

import hashlib
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from neuromem.models.memory import Memory
from neuromem.providers.llm import LLMProvider
from neuromem.services.conversation import ConversationService
from neuromem.services.memory_extraction import MemoryExtractionService


class MockE2ELLM(LLMProvider):
    def __init__(self, response: str):
        self._response = response

    async def chat(self, messages, temperature=0.1, max_tokens=2048) -> str:
        return self._response


@pytest.mark.asyncio
async def test_prospective_workflow_with_event_time(db_session, mock_embedding):
    """A prospective workflow fact should have event_time, procedure_steps, and temporality."""
    llm = MockE2ELLM(response=json.dumps({
        "facts": [
            {
                "content": "用户计划下个月按照 设计 → 开发 → 测试 流程重构系统",
                "category": "workflow",
                "temporality": "prospective",
                "confidence": 0.8,
                "importance": 7,
                "event_time": "2026-04-01",
                "procedure_steps": ["设计", "开发", "测试"],
            }
        ],
        "episodes": [],
    }))

    conv_svc = ConversationService(db_session)
    _, _ = await conv_svc.add_messages_batch(
        user_id="u_integ",
        messages=[{"role": "user", "content": "我计划下个月按照设计、开发、测试的流程重构系统"}],
    )
    messages = await conv_svc.get_unextracted_messages(user_id="u_integ")

    svc = MemoryExtractionService(db_session, mock_embedding, llm)
    result = await svc.extract_from_messages(user_id="u_integ", messages=messages)
    assert result["facts_extracted"] == 1

    row = (await db_session.execute(
        text("SELECT metadata FROM memories WHERE user_id = 'u_integ' AND memory_type = 'fact' LIMIT 1")
    )).first()
    meta = row.metadata
    assert meta["temporality"] == "prospective"
    assert meta["event_time"] == "2026-04-01"
    assert meta["category"] == "workflow"
    assert meta["procedure_steps"] == ["设计", "开发", "测试"]
```

**Step 2: Run integration test**

Run: `pytest tests/test_p2_integration.py -v`
Expected: PASS

**Step 3: Run full test suite**

Run: `pytest tests/ -m "not slow" -v --timeout=60`
Expected: All tests pass, no regressions.

**Step 4: Final commit**

```bash
git add tests/test_p2_integration.py
git commit -m "test: add P2 integration tests for cross-feature interactions"
```
