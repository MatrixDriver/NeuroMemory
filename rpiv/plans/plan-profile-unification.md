---
description: "功能实施计划: Profile 统一架构"
status: completed
created_at: 2026-03-02T21:30:00
updated_at: 2026-03-03T06:25:00
archived_at: null
related_files:
  - rpiv/requirements/prd-profile-unification.md
---

# 功能：Profile 统一架构

以下计划应该是完整的，但在开始实施之前，验证文档和代码库模式以及任务合理性非常重要。

特别注意现有工具、类型和模型的命名。从正确的文件导入等。

## 功能描述

将三套平行用户画像机制（KV Profile、Emotion Profile、V2 Trait）统一为 fact + trait + 计算视图的单一数据流架构。消除 `_store_profile_updates()` 和 `_update_emotion_profile()` 两条数据路径，新增 `profile_view()` 方法从 memories 表实时组装用户画像，watermark 迁入 reflection_cycles 表。

## 用户故事

作为 neuromem SDK 开发者，
我想要从 `recall()` 和 `profile_view()` 获取统一且可信的用户画像视图，
以便用一致的数据源组装更好的 LLM prompt，不再困惑于三套平行画像数据。

## 问题陈述

系统存在三套平行的用户画像机制：KV Profile（单次 LLM 推断，r=0.27）、Emotion Profile（独立表持久化）、V2 Trait（反思引擎归纳）。数据分裂、质量参差，KV Profile 违背 V2 核心原则"trait 必须由反思引擎归纳产生"。

## 解决方案陈述

1. Identity/occupation 等身份信息降级为带 category 标注的普通 fact
2. 情绪宏观模式归入 trait，由反思引擎归纳产生
3. 近期情绪状态改为 recall 时从 episodic emotion metadata 实时聚合
4. 新增 `profile_view()` 方法提供统一画像视图
5. 提供迁移脚本处理历史数据

## 功能元数据

**功能类型**：重构
**估计复杂度**：高
**主要受影响的系统**：neuromem SDK（_core.py, services/memory_extraction.py, services/reflection.py）、neuromem-cloud（core.py, extraction_prompt.py, schemas.py, mcp/tools.py）
**依赖项**：无新增外部依赖

---

## 上下文参考

### 相关代码库文件 重要：在实施之前必须阅读这些文件！

**SDK 核心文件：**
- `D:/CODE/NeuroMem/neuromem/_core.py` (第 1370-1388 行) - `_fetch_user_profile()` 方法，需替换为 `profile_view()`
- `D:/CODE/NeuroMem/neuromem/_core.py` (第 1070-1092 行) - `recall()` 中并行调用 `_fetch_user_profile`，需改为 `profile_view`
- `D:/CODE/NeuroMem/neuromem/_core.py` (第 1214-1221 行) - `recall()` 返回值中的 `user_profile` 字段
- `D:/CODE/NeuroMem/neuromem/_core.py` (第 1486-1659 行) - `digest()` 和 `_digest_impl()` 方法，watermark 逻辑
- `D:/CODE/NeuroMem/neuromem/services/memory_extraction.py` (第 141-148 行) - profile_updates 调用点
- `D:/CODE/NeuroMem/neuromem/services/memory_extraction.py` (第 294-423 行) - `_build_zh_prompt()` 含 profile_section_zh
- `D:/CODE/NeuroMem/neuromem/services/memory_extraction.py` (第 425-547 行) - `_build_en_prompt()` 含 profile_section_en
- `D:/CODE/NeuroMem/neuromem/services/memory_extraction.py` (第 549-595 行) - `_parse_classification_result()` 解析 profile_updates
- `D:/CODE/NeuroMem/neuromem/services/memory_extraction.py` (第 893-948 行) - `_store_profile_updates()` 及常量
- `D:/CODE/NeuroMem/neuromem/services/reflection.py` (第 553-579 行) - `digest()` backward-compat 方法
- `D:/CODE/NeuroMem/neuromem/services/reflection.py` (第 738-925 行) - `_update_emotion_profile()` 及辅助方法
- `D:/CODE/NeuroMem/neuromem/services/reflection.py` (第 528-549 行) - `_update_watermark()` 方法
- `D:/CODE/NeuroMem/neuromem/services/reflection.py` (第 127-199 行) - `should_reflect()` watermark 查询
- `D:/CODE/NeuroMem/neuromem/services/reflection.py` (第 398-438 行) - `_scan_new_memories()` watermark 查询
- `D:/CODE/NeuroMem/neuromem/models/emotion_profile.py` - 完整文件，待废弃
- `D:/CODE/NeuroMem/neuromem/models/memory.py` (第 87-93 行) - 现有索引定义
- `D:/CODE/NeuroMem/neuromem/models/reflection_cycle.py` - 完整文件，watermark 迁移目标
- `D:/CODE/NeuroMem/neuromem/models/kv.py` - KV 表结构，迁移源
- `D:/CODE/NeuroMem/neuromem/services/trait_engine.py` - trait 创建模式参考

**Cloud 文件：**
- `D:/CODE/neuromem-cloud/server/src/neuromem_cloud/core.py` (第 143-268 行) - `do_ingest_extracted()` 含 profile_updates 处理
- `D:/CODE/neuromem-cloud/server/src/neuromem_cloud/core.py` (第 327-372 行) - `do_digest()` 返回 profile_updated
- `D:/CODE/neuromem-cloud/server/src/neuromem_cloud/extraction_prompt.py` (第 48-95 行) - `_build_en_extraction_prompt` 含 Profile Updates
- `D:/CODE/neuromem-cloud/server/src/neuromem_cloud/extraction_prompt.py` (第 98-145 行) - `_build_zh_extraction_prompt` 含 Profile Updates
- `D:/CODE/neuromem-cloud/server/src/neuromem_cloud/schemas.py` (第 19-30 行) - `IngestExtractedRequest/Response`
- `D:/CODE/neuromem-cloud/server/src/neuromem_cloud/schemas.py` (第 53-56 行) - `DigestResponse` 含 profile_updated
- `D:/CODE/neuromem-cloud/server/src/neuromem_cloud/mcp/tools.py` (第 134-141 行) - MCP ingest_extracted 错误消息和统计

### 要创建的新文件

- `D:/CODE/NeuroMem/scripts/migrate_profile_unification.py` - 数据迁移脚本

### 要遵循的模式

**Memory 创建模式**（参考 `memory_extraction.py:748-758`）：
```python
from neuromem.models.memory import Memory
from datetime import datetime, timezone

now = datetime.now(timezone.utc)
embedding_obj = Memory(
    user_id=user_id,
    content=content,
    embedding=embedding_vector,
    memory_type="fact",  # 或 "trait"
    metadata_=meta,
    extracted_timestamp=resolved_ts,
    valid_from=now,
    content_hash=content_hash,
    valid_at=now,
)
session.add(embedding_obj)
```

**Trait 创建模式**（参考 `trait_engine.py` 的 `create_trend`/`create_behavior`）：
```python
Memory(
    user_id=user_id,
    content=content,
    embedding=vector,
    memory_type="trait",
    trait_subtype="behavior",
    trait_stage="trend",
    trait_confidence=0.2,
    trait_context="general",
    trait_first_observed=now,
    trait_window_start=now,
    trait_window_end=now + timedelta(days=30),
    metadata_={"source": "migration", "evidence_ids": []},
)
```

**SQL 查询模式**（参考 `_core.py` 和 `reflection.py`）：
```python
from sqlalchemy import text as sql_text
result = await session.execute(
    sql_text("SELECT ... FROM memories WHERE user_id = :uid AND ..."),
    {"uid": user_id},
)
rows = result.fetchall()
```

**日志模式**：
```python
logger = logging.getLogger(__name__)
logger.info("操作说明: key=%s count=%d", key, count)
logger.error("操作失败: %s", error, exc_info=True)
```

---

## 实施计划

### 阶段 1：Ingest 流程改造（消除 profile_updates）

消除 extraction prompt 中的 profile_updates 块和相关存储逻辑。这是最独立、风险最低的改动。

### 阶段 2：profile_view() + Recall 改造

新增 `profile_view()` 方法，替换 `_fetch_user_profile()`。

### 阶段 3：Digest/Reflect 改造 + Watermark 迁移

删除 emotion profile 更新逻辑，将 watermark 从 `conversation_sessions`/`emotion_profiles` 迁入 `reflection_cycles`。

### 阶段 4：Cloud 适配

同步修改 Cloud 端的 extraction prompt、core.py、schemas.py、MCP tools。

### 阶段 5：数据迁移脚本

编写独立迁移脚本，将历史 KV profile 和 emotion profile 数据转化为 fact/trait。

### 阶段 6：清理 + 测试

删除废弃代码和模型，运行全套测试。

---

## 逐步任务

重要：按顺序从上到下执行每个任务。每个任务都是原子的且可独立测试。

---

### 任务 1: UPDATE `neuromem/services/memory_extraction.py` — 删除 profile_updates 相关代码

**IMPLEMENT**：

1. **删除常量**（第 893-896 行）：
   ```python
   # 删除以下两行
   _PROFILE_OVERWRITE_KEYS = {"identity", "occupation"}
   _PROFILE_APPEND_KEYS = {"interests", "values", "relationships", "personality", "preferences"}
   ```

2. **删除 `_store_profile_updates()` 方法**（第 898-948 行）：完整删除该方法

3. **删除 `extract_from_messages()` 中的 profile_updates 调用**（第 141-148 行）：
   ```python
   # 删除以下代码块
   profile_updates = classified.get("profile_updates", {})
   if profile_updates:
       try:
           await self._store_profile_updates(user_id, profile_updates)
           logger.info(f"✅ 存储 profile_updates 成功: {list(profile_updates.keys())}")
       except Exception as e:
           logger.error(f"❌ 存储 profile_updates 失败: {e}", exc_info=True)
   ```

4. **修改 `_parse_classification_result()`**（第 579-587 行）：
   - 不再主动解析 `profile_updates`，但保留兼容处理（LLM 可能仍返回该字段）
   - 将返回值从 `{"facts": [...], "episodes": [...], "triples": [...], "profile_updates": {...}}` 改为 `{"facts": [...], "episodes": [...], "triples": [...]}`
   - 具体修改：删除第 579-581 行的 `profile_updates` 解析和第 587 行返回值中的 `"profile_updates": profile_updates`

5. **修改 `_build_zh_prompt()`**（第 301-423 行）：
   - 删除 `profile_section_zh` 变量定义（第 332-340 行）及其在 prompt 模板中的引用 `{profile_section_zh}`（第 407 行）
   - 删除 `profile_num` 变量及相关逻辑（第 305-307 行）
   - 在 fact 的 category 说明中增加 `identity` 和 `values` 选项。将第 355 行的：
     ```
     category 可选: work, skill, hobby, personal, education, location, health, relationship, finance
     ```
     改为：
     ```
     category 可选: identity, work, skill, hobby, personal, education, location, health, relationship, finance, values
     ```
   - 将返回格式中的 `"profile_updates": {{...}}` 删除（第 421 行）

6. **修改 `_build_en_prompt()`**（第 425-547 行）：
   - 同 zh prompt 的对称修改：删除 `profile_section_en`、删除 `profile_num`
   - fact category 增加 `identity` 和 `values`
   - 返回格式删除 `"profile_updates": {{...}}`

7. **由于删除了 `_store_profile_updates()` 方法中对 KVService 的使用，检查 `from neuromem.services.kv import KVService` 导入**：
   - `_get_extraction_language()` 仍使用 KVService，所以 **保留** 该导入

**IMPORTS**：无变化
**GOTCHA**：删除 `profile_section_zh`/`profile_section_en` 时注意 f-string 模板中对 `{profile_section_zh}` 的引用也必须同步删除
**VALIDATE**：`cd D:/CODE/NeuroMem && uv run python -c "from neuromem.services.memory_extraction import MemoryExtractionService; print('OK')"`

---

### 任务 2: UPDATE `neuromem/_core.py` — 新增 `profile_view()` 方法

**IMPLEMENT**：

在 `_fetch_user_profile()` 方法之后（约第 1389 行）添加 `profile_view()` 公共方法：

```python
async def profile_view(self, user_id: str) -> dict:
    """获取用户画像视图。

    从 fact + trait + 近期 episodic emotion metadata 实时组装用户画像。
    每次调用实时查询，不缓存。

    Args:
        user_id: 用户 ID

    Returns:
        {
            "facts": {category: value, ...},
            "traits": [{content, subtype, stage, confidence, context}, ...],
            "recent_mood": {valence_avg, arousal_avg, sample_count, period} | None,
        }
    """
    from sqlalchemy import text as sql_text
    import asyncio

    async def _fetch_facts() -> dict:
        """从 memories 表查询 fact 类型记忆，按 category 分组取最新。"""
        async with self._db.session() as session:
            result = await session.execute(
                sql_text(
                    "SELECT content, metadata->>'category' AS category, created_at "
                    "FROM memories "
                    "WHERE user_id = :uid AND memory_type = 'fact' "
                    "AND valid_until IS NULL "
                    "ORDER BY created_at DESC"
                ),
                {"uid": user_id},
            )
            rows = result.fetchall()

        # 按 category 分组
        # 单值 category（identity, occupation, location）取最新一条
        # 列表 category（hobby, skill, relationship, work, personal, values 等）取最新若干条
        single_categories = {"identity", "occupation", "location"}
        facts: dict = {}
        list_seen: dict[str, set] = {}

        for row in rows:
            cat = row.category or "general"
            content = row.content

            if cat in single_categories:
                if cat not in facts:
                    facts[cat] = content
            else:
                if cat not in facts:
                    facts[cat] = []
                    list_seen[cat] = set()
                content_lower = content.lower()
                if content_lower not in list_seen.get(cat, set()):
                    list_seen.setdefault(cat, set()).add(content_lower)
                    facts[cat].append(content)

        return facts

    async def _fetch_traits() -> list[dict]:
        """从 memories 表查询活跃 trait（emerging 及以上阶段）。"""
        async with self._db.session() as session:
            result = await session.execute(
                sql_text(
                    "SELECT content, trait_subtype, trait_stage, trait_confidence, trait_context "
                    "FROM memories "
                    "WHERE user_id = :uid AND memory_type = 'trait' "
                    "AND trait_stage NOT IN ('trend', 'dissolved') "
                    "ORDER BY trait_confidence DESC NULLS LAST "
                    "LIMIT 30"
                ),
                {"uid": user_id},
            )
            return [
                {
                    "content": r.content,
                    "subtype": r.trait_subtype,
                    "stage": r.trait_stage,
                    "confidence": float(r.trait_confidence) if r.trait_confidence else 0.0,
                    "context": r.trait_context,
                }
                for r in result.fetchall()
            ]

    async def _fetch_recent_mood() -> dict | None:
        """从近期 episodic 记忆的 emotion metadata 实时聚合情绪状态。"""
        async with self._db.session() as session:
            result = await session.execute(
                sql_text(
                    "SELECT "
                    "  AVG((metadata->'emotion'->>'valence')::float) AS valence_avg, "
                    "  AVG((metadata->'emotion'->>'arousal')::float) AS arousal_avg, "
                    "  COUNT(*) AS sample_count "
                    "FROM memories "
                    "WHERE user_id = :uid "
                    "  AND memory_type = 'episodic' "
                    "  AND metadata->'emotion' IS NOT NULL "
                    "  AND (metadata->'emotion'->>'valence') IS NOT NULL "
                    "  AND created_at > NOW() - INTERVAL '14 days'"
                ),
                {"uid": user_id},
            )
            row = result.first()

        if not row or not row.sample_count or row.sample_count == 0:
            return None

        return {
            "valence_avg": round(float(row.valence_avg), 3),
            "arousal_avg": round(float(row.arousal_avg), 3),
            "sample_count": row.sample_count,
            "period": "last_14_days",
        }

    try:
        facts, traits, mood = await asyncio.gather(
            _fetch_facts(),
            _fetch_traits(),
            _fetch_recent_mood(),
            return_exceptions=True,
        )
        if isinstance(facts, Exception):
            logger.warning("profile_view facts query failed: %s", facts)
            facts = {}
        if isinstance(traits, Exception):
            logger.warning("profile_view traits query failed: %s", traits)
            traits = []
        if isinstance(mood, Exception):
            logger.warning("profile_view mood query failed: %s", mood)
            mood = None

        return {
            "facts": facts,
            "traits": traits,
            "recent_mood": mood,
        }
    except Exception as e:
        logger.warning("profile_view failed: %s", e)
        return {"facts": {}, "traits": [], "recent_mood": None}
```

**IMPORTS**：`asyncio` 和 `sql_text` 已在文件顶部导入
**GOTCHA**：三个子查询使用独立 session（`self._db.session()`），不要共享 session 以避免并发问题
**VALIDATE**：`cd D:/CODE/NeuroMem && uv run python -c "from neuromem._core import NeuroMemory; print('profile_view' in dir(NeuroMemory))"`

---

### 任务 3: UPDATE `neuromem/_core.py` — 替换 recall() 中的 `_fetch_user_profile`

**IMPLEMENT**：

1. **修改 recall() 中的并行调用**（第 1078 行）：
   将 `self._fetch_user_profile(user_id)` 替换为 `self.profile_view(user_id)`

2. **修改 recall() 中的结果接收**（第 1092 行）：
   将 `user_profile: dict = results[1] if not isinstance(results[1], Exception) else {}`
   改为 `user_profile: dict = results[1] if not isinstance(results[1], Exception) else {"facts": {}, "traits": [], "recent_mood": None}`

3. **删除 `_fetch_user_profile()` 方法**（第 1370-1388 行）：完整删除该方法

**GOTCHA**：`recall()` 返回值中的 `"user_profile": user_profile` 不需要改动（第 1219 行），结构已由 `profile_view()` 决定
**VALIDATE**：`cd D:/CODE/NeuroMem && uv run python -c "import ast, inspect; from neuromem._core import NeuroMemory; src = inspect.getsource(NeuroMemory.recall); assert '_fetch_user_profile' not in src; print('OK')"`

---

### 任务 4: UPDATE `neuromem/services/reflection.py` — 删除 emotion profile 逻辑

**IMPLEMENT**：

1. **修改 `digest()` backward-compat 方法**（第 553-579 行）：
   - 删除 `_update_emotion_profile` 调用（第 574 行）
   - 修改返回值，不再包含 `emotion_profile`
   - 修改后的 `digest()`:
     ```python
     async def digest(
         self,
         user_id: str,
         recent_memories: list[dict],
         existing_insights: Optional[list[dict]] = None,
     ) -> dict:
         if not recent_memories:
             return {"insights": []}
         insights = await self._generate_insights(user_id, recent_memories, existing_insights)
         return {"insights": insights}
     ```

2. **删除以下方法**（第 738-925 行之间）：
   - `_update_emotion_profile()` 方法（第 738-835 行）
   - `_build_emotion_summary_prompt()` 方法（第 837-881 行）
   - `_parse_emotion_summary()` 方法（第 883-925 行）
   - `_get_current_period()` 方法（第 927-931 行）

3. **删除 EmotionProfile 导入**（第 13 行）：
   ```python
   # 删除
   from neuromem.models.emotion_profile import EmotionProfile
   ```

4. **删除 `select` 导入（如果仅被 emotion profile 使用）**：
   检查第 10 行 `from sqlalchemy import select, text as sql_text`，如果 `select` 仅用于 `_update_emotion_profile` 中的 `select(EmotionProfile)`，则删除 `select` 导入。**检查结果**：`select` 未在其他地方使用 → 删除 `select`

**IMPORTS**：删除 `from neuromem.models.emotion_profile import EmotionProfile` 和 `select`
**GOTCHA**：保留 `_generate_insights()` 及其辅助方法（`_build_insight_prompt`, `_parse_insight_result`），它们仍被 `digest()` 使用
**VALIDATE**：`cd D:/CODE/NeuroMem && uv run python -c "from neuromem.services.reflection import ReflectionService; print('OK')"`

---

### 任务 5: UPDATE `neuromem/services/reflection.py` — watermark 迁移到 reflection_cycles

**IMPLEMENT**：

1. **修改 `should_reflect()` 中的 watermark 查询**（第 133-137 行）：
   将：
   ```python
   result = await self.db.execute(
       sql_text(
           "SELECT last_reflected_at FROM conversation_sessions "
           "WHERE user_id = :uid ORDER BY last_reflected_at DESC NULLS LAST LIMIT 1"
       ),
       {"uid": user_id},
   )
   row = result.first()
   ```
   替换为：
   ```python
   result = await self.db.execute(
       sql_text(
           "SELECT completed_at FROM reflection_cycles "
           "WHERE user_id = :uid AND status = 'completed' "
           "ORDER BY completed_at DESC LIMIT 1"
       ),
       {"uid": user_id},
   )
   row = result.first()
   ```
   并将后续 `row.last_reflected_at` 引用改为 `row.completed_at`（第 143 和 157 行）

2. **修改 `_scan_new_memories()` 中的 watermark 查询**（第 398-409 行）：
   同样将 `conversation_sessions.last_reflected_at` 改为 `reflection_cycles.completed_at`：
   ```python
   result = await self.db.execute(
       sql_text(
           "SELECT completed_at FROM reflection_cycles "
           "WHERE user_id = :uid AND status = 'completed' "
           "ORDER BY completed_at DESC LIMIT 1"
       ),
       {"uid": user_id},
   )
   row = result.first()
   watermark = row.completed_at if row else None
   ```

3. **修改 `_update_watermark()` 方法**（第 528-549 行）：
   watermark 不再需要显式更新，因为 `reflect()` 方法在步骤 2 中已经通过 `ReflectionCycle.completed_at` 记录了 watermark。删除整个 `_update_watermark()` 方法。

4. **删除 `_run_reflection_steps()` 中对 `_update_watermark` 的调用**（第 313 和 394 行）：
   ```python
   # 删除第 313 行
   await self._update_watermark(user_id)
   # 删除第 394 行
   await self._update_watermark(user_id)
   ```

5. **删除 ConversationSession 导入**（第 13 行）：
   ```python
   # 删除（如果仅用于 watermark）
   from neuromem.models.conversation import ConversationSession
   ```
   **检查结果**：`ConversationSession` 仅在 watermark 相关代码中使用 → 删除

**IMPORTS**：删除 `ConversationSession` 导入，删除 `EmotionProfile` 导入（已在任务 4 删除）
**GOTCHA**：
- `ReflectionCycle` 模型不需要导入，因为查询使用的是 raw SQL `sql_text()`
- `reflect()` 方法中 cycle 的 `completed_at` 在 `_run_reflection_steps()` 成功后由第 257 行 `cycle.completed_at = datetime.now(timezone.utc)` 设置，这就是新的 watermark
- `_run_reflection_steps()` 中第 313 行的 `await self._update_watermark(user_id)` 是在"无新记忆"分支中调用的，删除后该分支不再更新 watermark（正确：无新记忆不需要推进 watermark）
**VALIDATE**：`cd D:/CODE/NeuroMem && uv run python -c "from neuromem.services.reflection import ReflectionService; print('OK')"`

---

### 任务 6: UPDATE `neuromem/_core.py` — 修改 `_digest_impl()` watermark 逻辑

**IMPLEMENT**：

1. **修改 watermark 读取**（第 1530-1537 行）：
   将从 `emotion_profiles.last_reflected_at` 读取改为从 `reflection_cycles.completed_at` 读取：
   ```python
   # 替换整个 watermark 读取块
   watermark = None
   async with self._db.session() as session:
       row = (await session.execute(
           sql_text(
               "SELECT completed_at FROM reflection_cycles "
               "WHERE user_id = :uid AND status = 'completed' "
               "ORDER BY completed_at DESC LIMIT 1"
           ),
           {"uid": user_id},
       )).first()
       if row and row.completed_at:
           watermark = row.completed_at
   ```

2. **修改 watermark 推进**（第 1640-1652 行）：
   将写入 `emotion_profiles.last_reflected_at` 改为插入 `reflection_cycles` 记录：
   ```python
   if max_created_at is not None:
       async with self._db.session() as session:
           await session.execute(
               sql_text(
                   "INSERT INTO reflection_cycles "
                   "(user_id, trigger_type, status, completed_at, memories_scanned) "
                   "VALUES (:uid, 'digest', 'completed', :ts, :count)"
               ),
               {"uid": user_id, "ts": max_created_at, "count": total_analyzed},
           )
           await session.commit()
   ```

3. **修改返回值**（第 1654-1659 行）：
   删除 `"emotion_profile": emotion_profile`：
   ```python
   return {
       "memories_analyzed": total_analyzed,
       "insights_generated": len(all_insights),
       "insights": all_insights,
   }
   ```

4. **删除 `_digest_impl()` 中的 `emotion_profile` 变量**（第 1578 行）及相关使用（第 1628-1629 行）：
   ```python
   # 删除第 1578 行
   emotion_profile = None
   # 删除第 1628-1629 行
   if emotion_profile is None:
       emotion_profile = batch_result.get("emotion_profile")
   ```

5. **修改 `digest()` 返回值的 None 分支**（第 1551-1556 行）：
   删除 `"emotion_profile": None`：
   ```python
   return {
       "memories_analyzed": 0,
       "insights_generated": 0,
       "insights": [],
   }
   ```

**GOTCHA**：`_digest_impl()` 中的 `existing_insights` 查询（第 1561-1572 行）使用 `memory_type = 'trait' AND trait_stage = 'trend'`，不需要修改
**VALIDATE**：`cd D:/CODE/NeuroMem && uv run python -c "from neuromem._core import NeuroMemory; print('OK')"`

---

### 任务 7: UPDATE Cloud — `extraction_prompt.py`

**IMPLEMENT**：

1. **修改 `_build_en_extraction_prompt()`**（第 48-95 行）：
   - 删除 `4. **Profile Updates**` 块（第 77-79 行区域）
   - 在 fact category 中增加 `identity` 和 `values`
   - 返回格式从 `{facts, episodes, triples, profile_updates}` 改为 `{facts, episodes, triples}`

2. **修改 `_build_zh_extraction_prompt()`**（第 98-145 行）：
   - 删除 `4. **Profile Updates（用户画像更新）**` 块（第 127-129 行区域）
   - 在 fact category 中增加 `identity` 和 `values`
   - 返回格式从 `{facts, episodes, triples, profile_updates}` 改为 `{facts, episodes, triples}`

**GOTCHA**：`build_extraction_response()` 中的文本说明也引用了 `profile_updates`（第 30 行 `"then pass the result as the data parameter"`），需检查但实际不需要修改（描述足够通用）
**VALIDATE**：`cd D:/CODE/neuromem-cloud/server && uv run python -c "from neuromem_cloud.extraction_prompt import build_extraction_prompt_for_rest; print('OK')"`

---

### 任务 8: UPDATE Cloud — `core.py`

**IMPLEMENT**：

1. **修改 `do_ingest_extracted()`**（第 143-268 行）：
   - 删除第 177 行：`profile_updates = data.get("profile_updates", {})`
   - 删除第 182 行：`profile_updates_count = 0`
   - 删除第 237-242 行的 profile_updates 处理块：
     ```python
     # 删除整个 if block
     if profile_updates and isinstance(profile_updates, dict):
         try:
             await svc._store_profile_updates(user_id, profile_updates)
             profile_updates_count = len(profile_updates)
         except Exception as e:
             logger.error("Failed to store extracted profile updates: %s", e, exc_info=True)
     ```
   - 修改第 246 行的 commit 条件：`if total > 0 or profile_updates_count > 0:` 改为 `if total > 0:`
   - 修改第 251 行的 log 格式：删除 `profile=%d` 和 `, profile_updates_count`
   - 修改第 259 行：删除 `profile_updates_count = 0`（从赋值链中移除）
   - 修改返回值（第 261-268 行），删除 `"profile_updates_stored": profile_updates_count`

2. **修改 `do_digest()`** 返回值（第 359-363 行）：
   删除 `"profile_updated": result.get("profile_updated", False)`

**GOTCHA**：旧客户端可能仍在 `data` 中发送 `profile_updates`，由于我们已经删除了对其的读取，它会被自然忽略，无需特殊处理
**VALIDATE**：`cd D:/CODE/neuromem-cloud/server && uv run python -c "from neuromem_cloud.core import do_ingest_extracted, do_digest; print('OK')"`

---

### 任务 9: UPDATE Cloud — `schemas.py`

**IMPLEMENT**：

1. **修改 `IngestExtractedRequest`**（第 22 行）：
   将注释 `# JSON object with facts/episodes/triples/profile_updates` 改为 `# JSON object with facts/episodes/triples`

2. **修改 `IngestExtractedResponse`**（第 24-30 行）：
   删除 `profile_updates_stored: int` 字段

3. **修改 `DigestResponse`**（第 53-56 行）：
   删除 `profile_updated: bool` 字段

**VALIDATE**：`cd D:/CODE/neuromem-cloud/server && uv run python -c "from neuromem_cloud.schemas import IngestExtractedResponse, DigestResponse; print('OK')"`

---

### 任务 10: UPDATE Cloud — `mcp/tools.py`

**IMPLEMENT**：

1. **修改错误消息**（第 134 行）：
   将 `"Expected a JSON object with facts/episodes/triples/profile_updates."` 改为 `"Expected a JSON object with facts/episodes/triples."`

2. **修改统计字符串**（第 136-141 行）：
   删除 `f"{result['profile_updates_stored']} profile updates"` 行：
   ```python
   stats = (
       f"{result['facts_stored']} facts, "
       f"{result['episodes_stored']} episodes, "
       f"{result['triples_stored']} triples"
   )
   ```

**VALIDATE**：`cd D:/CODE/neuromem-cloud/server && uv run python -c "from neuromem_cloud.mcp.tools import *; print('OK')"`

---

### 任务 11: UPDATE `neuromem/services/reflection.py` — 反思 prompt 增加情绪模式识别

**IMPLEMENT**：

在 `REFLECTION_PROMPT_TEMPLATE`（第 23-106 行）的 `## 分析任务` 部分，在 `### 1. 短期趋势检测` 之前添加情绪模式识别引导：

```
注意：新增记忆中的 metadata 可能包含 emotion 字段（含 valence、arousal、label）。在检测趋势和行为模式时，请关注：
- 特定话题/情境下反复出现的情绪模式（如"讨论工作时总是焦虑"）
- 情绪变化趋势（如"最近整体情绪变积极了"）
- 情绪触发关联（如"提到某人时情绪波动大"）
将这些情绪模式作为情境化 trait 产生，context 从话题推断。
```

**GOTCHA**：这是一个 prompt 增强，不改变代码逻辑。反思引擎已有能力创建带 context 的 behavior/trend trait，只需引导 LLM 关注 emotion metadata
**VALIDATE**：`cd D:/CODE/NeuroMem && uv run python -c "from neuromem.services.reflection import REFLECTION_PROMPT_TEMPLATE; assert 'emotion' in REFLECTION_PROMPT_TEMPLATE.lower(); print('OK')"`

---

### 任务 12: CREATE `D:/CODE/NeuroMem/scripts/migrate_profile_unification.py` — 数据迁移脚本

**IMPLEMENT**：

创建独立可执行的迁移脚本，支持 `--dry-run` 和 `--database-url` 参数：

```python
"""数据迁移脚本：Profile 统一架构

将 KV Profile 和 Emotion Profile 数据迁移到 fact + trait 统一存储。

用法:
    uv run python scripts/migrate_profile_unification.py --database-url "postgresql+asyncpg://..." --dry-run
    uv run python scripts/migrate_profile_unification.py --database-url "postgresql+asyncpg://..."
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)


async def migrate(database_url: str, dry_run: bool = False, embedding_provider=None):
    """执行迁移。"""
    engine = create_async_engine(database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    stats = {
        "facts_created": 0,
        "traits_created": 0,
        "watermarks_migrated": 0,
        "users_processed": 0,
        "errors": [],
    }

    async with async_session() as session:
        async with session.begin():
            # 1. 获取所有有 profile 数据的用户
            kv_users = await session.execute(
                sql_text("SELECT DISTINCT scope_id FROM key_values WHERE namespace = 'profile'")
            )
            ep_users = await session.execute(
                sql_text("SELECT DISTINCT user_id FROM emotion_profiles")
            )
            all_users = set(r.scope_id for r in kv_users.fetchall()) | set(r.user_id for r in ep_users.fetchall())

            logger.info("找到 %d 个需要迁移的用户", len(all_users))

            for user_id in all_users:
                try:
                    user_stats = await _migrate_user(session, user_id, embedding_provider)
                    stats["facts_created"] += user_stats["facts"]
                    stats["traits_created"] += user_stats["traits"]
                    stats["watermarks_migrated"] += user_stats["watermarks"]
                    stats["users_processed"] += 1
                except Exception as e:
                    logger.error("迁移用户 %s 失败: %s", user_id, e, exc_info=True)
                    stats["errors"].append({"user_id": user_id, "error": str(e)})

            if dry_run:
                logger.info("Dry-run 模式，回滚所有变更")
                await session.rollback()
            # else: session.begin() context manager 自动 commit

    await engine.dispose()

    logger.info("迁移完成: %s", stats)
    return stats


async def _migrate_user(session: AsyncSession, user_id: str, embedding_provider=None) -> dict:
    """迁移单个用户的数据。"""
    stats = {"facts": 0, "traits": 0, "watermarks": 0}
    now = datetime.now(timezone.utc)

    # --- KV Profile → fact/trait ---
    kv_result = await session.execute(
        sql_text("SELECT key, value FROM key_values WHERE namespace = 'profile' AND scope_id = :uid"),
        {"uid": user_id},
    )
    kv_items = {r.key: r.value for r in kv_result.fetchall()}

    # identity, occupation → fact
    for key, category in [("identity", "identity"), ("occupation", "work")]:
        value = kv_items.get(key)
        if value and isinstance(value, str) and value.strip():
            content = f"用户{key}: {value}" if key == "identity" else value
            await _create_memory(session, user_id, content, "fact", {"category": category, "source": "migration"}, now, embedding_provider)
            stats["facts"] += 1

    # relationships → fact
    relationships = kv_items.get("relationships")
    if relationships and isinstance(relationships, list):
        for rel in relationships:
            if rel and isinstance(rel, str) and rel.strip():
                await _create_memory(session, user_id, rel, "fact", {"category": "relationship", "source": "migration"}, now, embedding_provider)
                stats["facts"] += 1

    # interests, preferences, values, personality → behavior trait (trend)
    for key in ["interests", "preferences", "values", "personality"]:
        items = kv_items.get(key)
        if items and isinstance(items, list):
            for item in items:
                if item and isinstance(item, str) and item.strip():
                    context = "general"
                    if key == "values":
                        context = "personal"
                    await _create_trait(session, user_id, f"用户{item}", "behavior", "trend", 0.2, context, now, embedding_provider)
                    stats["traits"] += 1

    # --- Emotion Profile → trait ---
    ep_result = await session.execute(
        sql_text(
            "SELECT dominant_emotions, emotion_triggers, last_reflected_at "
            "FROM emotion_profiles WHERE user_id = :uid"
        ),
        {"uid": user_id},
    )
    ep_row = ep_result.first()

    if ep_row:
        # dominant_emotions → trait
        if ep_row.dominant_emotions and isinstance(ep_row.dominant_emotions, dict):
            for emotion, weight in ep_row.dominant_emotions.items():
                if emotion and weight and float(weight) > 0.2:
                    content = f"用户经常表现出{emotion}情绪"
                    await _create_trait(session, user_id, content, "behavior", "trend", 0.25, "general", now, embedding_provider)
                    stats["traits"] += 1

        # emotion_triggers → trait
        if ep_row.emotion_triggers and isinstance(ep_row.emotion_triggers, dict):
            for topic, trigger_data in ep_row.emotion_triggers.items():
                if topic and isinstance(trigger_data, dict):
                    valence = trigger_data.get("valence", 0)
                    label = "积极" if valence > 0.3 else "消极" if valence < -0.3 else "中性"
                    content = f"讨论{topic}话题时情绪偏{label}"
                    ctx = "work" if topic in ("工作", "work", "项目", "project") else "general"
                    await _create_trait(session, user_id, content, "behavior", "trend", 0.2, ctx, now, embedding_provider)
                    stats["traits"] += 1

        # watermark → reflection_cycles
        if ep_row.last_reflected_at:
            await session.execute(
                sql_text(
                    "INSERT INTO reflection_cycles "
                    "(id, user_id, trigger_type, status, started_at, completed_at) "
                    "VALUES (:id, :uid, 'migration', 'completed', :ts, :ts)"
                ),
                {"id": str(uuid.uuid4()), "uid": user_id, "ts": ep_row.last_reflected_at},
            )
            stats["watermarks"] += 1

    # --- conversation_sessions watermark → reflection_cycles ---
    cs_result = await session.execute(
        sql_text(
            "SELECT last_reflected_at FROM conversation_sessions "
            "WHERE user_id = :uid AND last_reflected_at IS NOT NULL "
            "ORDER BY last_reflected_at DESC LIMIT 1"
        ),
        {"uid": user_id},
    )
    cs_row = cs_result.first()
    if cs_row and cs_row.last_reflected_at:
        # 检查是否已有更新的 watermark（来自 emotion_profiles 迁移）
        existing = await session.execute(
            sql_text(
                "SELECT completed_at FROM reflection_cycles "
                "WHERE user_id = :uid AND status = 'completed' "
                "ORDER BY completed_at DESC LIMIT 1"
            ),
            {"uid": user_id},
        )
        existing_row = existing.first()
        if not existing_row or cs_row.last_reflected_at > existing_row.completed_at:
            await session.execute(
                sql_text(
                    "INSERT INTO reflection_cycles "
                    "(id, user_id, trigger_type, status, started_at, completed_at) "
                    "VALUES (:id, :uid, 'migration', 'completed', :ts, :ts)"
                ),
                {"id": str(uuid.uuid4()), "uid": user_id, "ts": cs_row.last_reflected_at},
            )
            stats["watermarks"] += 1

    logger.info("用户 %s 迁移完成: facts=%d traits=%d watermarks=%d", user_id, stats["facts"], stats["traits"], stats["watermarks"])
    return stats


async def _create_memory(session, user_id, content, memory_type, metadata, now, embedding_provider=None):
    """创建 Memory 行。"""
    content_hash = hashlib.md5(content.encode()).hexdigest()

    # 生成 embedding
    embedding = None
    if embedding_provider:
        try:
            embedding = await embedding_provider.embed(content)
        except Exception as e:
            logger.warning("Embedding 生成失败，使用零向量: %s", e)

    if embedding is None:
        # 零向量占位
        from neuromem.models import _embedding_dims
        embedding = [0.0] * _embedding_dims

    vector_str = f"[{','.join(str(float(v)) for v in embedding)}]"

    await session.execute(
        sql_text(
            "INSERT INTO memories "
            "(id, user_id, content, embedding, memory_type, metadata, "
            " valid_from, content_hash, valid_at, created_at, updated_at) "
            "VALUES (:id, :uid, :content, :vec, :mtype, :meta::jsonb, "
            " :now, :hash, :now, :now, :now)"
        ),
        {
            "id": str(uuid.uuid4()),
            "uid": user_id,
            "content": content,
            "vec": vector_str,
            "mtype": memory_type,
            "meta": __import__("json").dumps(metadata, ensure_ascii=False),
            "now": now,
            "hash": content_hash,
        },
    )


async def _create_trait(session, user_id, content, subtype, stage, confidence, context, now, embedding_provider=None):
    """创建 Trait Memory 行。"""
    content_hash = hashlib.md5(content.encode()).hexdigest()

    embedding = None
    if embedding_provider:
        try:
            embedding = await embedding_provider.embed(content)
        except Exception as e:
            logger.warning("Embedding 生成失败，使用零向量: %s", e)

    if embedding is None:
        from neuromem.models import _embedding_dims
        embedding = [0.0] * _embedding_dims

    vector_str = f"[{','.join(str(float(v)) for v in embedding)}]"

    await session.execute(
        sql_text(
            "INSERT INTO memories "
            "(id, user_id, content, embedding, memory_type, metadata, "
            " trait_subtype, trait_stage, trait_confidence, trait_context, "
            " trait_first_observed, trait_window_start, trait_window_end, "
            " valid_from, content_hash, valid_at, created_at, updated_at) "
            "VALUES (:id, :uid, :content, :vec, 'trait', :meta::jsonb, "
            " :subtype, :stage, :confidence, :context, "
            " :now, :now, :window_end, "
            " :now, :hash, :now, :now, :now)"
        ),
        {
            "id": str(uuid.uuid4()),
            "uid": user_id,
            "content": content,
            "vec": vector_str,
            "meta": __import__("json").dumps({"source": "migration", "evidence_ids": []}, ensure_ascii=False),
            "subtype": subtype,
            "stage": stage,
            "confidence": confidence,
            "context": context,
            "now": now,
            "hash": content_hash,
            "window_end": now + timedelta(days=30),
        },
    )


def main():
    parser = argparse.ArgumentParser(description="Profile 统一架构数据迁移")
    parser.add_argument("--database-url", required=True, help="PostgreSQL 连接字符串")
    parser.add_argument("--dry-run", action="store_true", help="预览变更，不提交")
    parser.add_argument("--embedding-api-key", help="Embedding API Key（可选，无则使用零向量）")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    # 可选：初始化 embedding provider
    embedding = None
    if args.embedding_api_key:
        try:
            from neuromem.providers.siliconflow import SiliconFlowEmbedding
            embedding = SiliconFlowEmbedding(api_key=args.embedding_api_key)
        except Exception as e:
            logger.warning("无法初始化 Embedding Provider: %s，将使用零向量", e)

    result = asyncio.run(migrate(args.database_url, dry_run=args.dry_run, embedding_provider=embedding))
    print(f"\n迁移结果: {result}")


if __name__ == "__main__":
    main()
```

**GOTCHA**：
- 脚本使用 raw SQL 而非 ORM 以避免依赖 Memory 模型的 HALFVEC 类型（需要 pgvector 扩展加载）
- embedding 向量格式使用 PostgreSQL pgvector 的字符串格式 `[0.1, 0.2, ...]`
- 事务保护通过 `session.begin()` context manager 提供
**VALIDATE**：`cd D:/CODE/NeuroMem && uv run python scripts/migrate_profile_unification.py --help`

---

### 任务 13: UPDATE `neuromem/models/emotion_profile.py` — 标记废弃

**IMPLEMENT**：

在文件顶部添加废弃警告，但**不立即删除**（保留以便迁移脚本读取数据）：

```python
"""Emotion profile model for aggregated user emotional state.

DEPRECATED: This model is deprecated as part of the Profile Unification refactoring.
The emotion_profiles table will be dropped after data migration is complete.
Use profile_view() for emotion data (aggregated from episodic memories).
"""
```

同时确保 `neuromem/models/__init__.py` 中不再主动导入 `EmotionProfile`（检查后决定是否删除）。

**VALIDATE**：`cd D:/CODE/NeuroMem && uv run python -c "from neuromem.models.emotion_profile import EmotionProfile; print('DEPRECATED but importable')"`

---

### 任务 14: 全面测试验证

**IMPLEMENT**：

1. 运行 SDK 全套测试（不含 slow）：
   ```bash
   cd D:/CODE/NeuroMem && uv run pytest tests/ -m "not slow" -v
   ```

2. 检查是否有测试直接测试 `_store_profile_updates` 或 `_update_emotion_profile`，如有需要更新：
   ```bash
   cd D:/CODE/NeuroMem && grep -r "_store_profile_updates\|_update_emotion_profile\|profile_updates\|emotion_profile" tests/
   ```

3. 运行 Cloud 全套测试：
   ```bash
   cd D:/CODE/neuromem-cloud/server && uv run pytest tests/ -v
   ```

4. 检查 Cloud 测试中的 profile_updates 引用：
   ```bash
   cd D:/CODE/neuromem-cloud/server && grep -r "profile_updates\|profile_updated" tests/
   ```

**GOTCHA**：如果现有测试引用了 `profile_updates_stored` 或 `profile_updated`，需要同步修改测试断言

---

## 测试策略

### 单元测试

**profile_view() 测试**（新增）：
- 测试无数据时返回空结构
- 测试有 fact 数据时 facts 部分正确分组
- 测试有 trait 数据时 traits 部分正确过滤（只返回 emerging+）
- 测试有 episodic emotion 数据时 recent_mood 正确聚合
- 测试数据库异常时优雅降级

**extraction prompt 测试**：
- 验证中文 prompt 不再包含 `profile_updates`
- 验证英文 prompt 不再包含 `Profile Updates`
- 验证 fact category 包含 `identity` 和 `values`

**watermark 测试**：
- 验证 `should_reflect()` 从 reflection_cycles 读取 watermark
- 验证 digest() 写入 reflection_cycles 作为 watermark

### 集成测试

**端到端流程**：
- ingest → extraction 不再产生 profile_updates
- recall → profile_view 返回新结构
- digest → 不再更新 emotion_profiles

### 边缘情况

- 新用户（无任何数据）调用 profile_view
- 旧客户端发送含 profile_updates 的 ingest_extracted 请求
- watermark 迁移后首次 digest 不重复处理已分析记忆
- 迁移脚本 dry-run 模式不提交任何变更

---

## 验证命令

### 级别 1：语法检查

```bash
cd D:/CODE/NeuroMem && uv run python -c "
from neuromem._core import NeuroMemory
from neuromem.services.memory_extraction import MemoryExtractionService
from neuromem.services.reflection import ReflectionService
print('SDK imports OK')
"

cd D:/CODE/neuromem-cloud/server && uv run python -c "
from neuromem_cloud.core import do_ingest, do_ingest_extracted, do_recall, do_digest
from neuromem_cloud.extraction_prompt import build_extraction_prompt_for_rest
from neuromem_cloud.schemas import IngestExtractedResponse, DigestResponse
print('Cloud imports OK')
"
```

### 级别 2：单元测试

```bash
cd D:/CODE/NeuroMem && uv run pytest tests/ -m "not slow" -v
cd D:/CODE/neuromem-cloud/server && uv run pytest tests/ -v
```

### 级别 3：验证删除完整性

```bash
# 确认 profile_updates 不再出现在活跃代码路径中
cd D:/CODE/NeuroMem && grep -rn "_store_profile_updates\|_PROFILE_OVERWRITE_KEYS\|_PROFILE_APPEND_KEYS" neuromem/ --include="*.py" | grep -v "\.pyc" | grep -v "migration"

# 确认 _fetch_user_profile 已被删除
cd D:/CODE/NeuroMem && grep -rn "_fetch_user_profile" neuromem/ --include="*.py"

# 确认 _update_emotion_profile 已被删除
cd D:/CODE/NeuroMem && grep -rn "_update_emotion_profile" neuromem/ --include="*.py"
```

### 级别 4：迁移脚本验证

```bash
cd D:/CODE/NeuroMem && uv run python scripts/migrate_profile_unification.py --help
# 注：实际 dry-run 需要可用的 PostgreSQL 实例
```

---

## 验收标准

- [ ] `profile_view()` 方法已实现并可独立调用
- [ ] `recall()` 返回的 `user_profile` 使用新结构（facts + traits + recent_mood）
- [ ] extraction prompt（中英文）不再包含 profile_updates 块
- [ ] `_store_profile_updates()` 方法和常量已删除
- [ ] `_update_emotion_profile()` 及辅助方法已删除
- [ ] `_fetch_user_profile()` 方法已删除并被 `profile_view()` 替换
- [ ] watermark 从 conversation_sessions/emotion_profiles 迁入 reflection_cycles
- [ ] `digest()` 返回值不再包含 `emotion_profile` 字段
- [ ] Cloud `ingest_extracted` 不再处理 `profile_updates`（静默忽略）
- [ ] Cloud `DigestResponse` 不再包含 `profile_updated` 字段
- [ ] MCP tools 统计信息不再包含 profile_updates 计数
- [ ] 反思引擎 prompt 增加了情绪模式识别引导
- [ ] 迁移脚本支持 --dry-run 和事务保护
- [ ] 所有现有 SDK 测试通过
- [ ] 所有现有 Cloud 测试通过
- [ ] 无代码检查或类型检查错误

---

## 完成检查清单

- [ ] 任务 1-14 按顺序完成
- [ ] 每个任务验证命令通过
- [ ] 全套 SDK 测试通过
- [ ] 全套 Cloud 测试通过
- [ ] grep 验证：活跃代码中无 `_store_profile_updates`、`_fetch_user_profile`、`_update_emotion_profile` 引用
- [ ] 迁移脚本 --help 正常输出
- [ ] 所有验收标准满足

---

## 备注

**改造顺序的理由**：
- 先改 ingest（任务 1）是因为它最独立，不影响其他流程
- 再改 recall（任务 2-3）依赖 profile_view，而 profile_view 不依赖其他改动
- 然后改 reflect/digest（任务 4-6）较复杂但内部封闭
- Cloud 改动（任务 7-10）与 SDK 改动对称，但顺序在后以便先验证 SDK
- 迁移脚本（任务 12）放在最后是因为它是独立可执行的，不影响代码改动

**风险控制**：
- emotion_profile.py 标记废弃但不立即删除，迁移脚本需要读取旧表数据
- watermark 迁移确保不丢失不重复：先迁移旧 watermark 到 reflection_cycles，再修改代码读取新位置
- Cloud 端静默忽略旧版客户端的 profile_updates（自然实现：不再读取该字段）

**personality 冷启动说明**：
去掉 profile_updates 后，新用户的 personality 信息不再从单次对话直接提取。这是有意为之——符合 V2 设计原则"trait 必须由反思引擎归纳产生"。用户需要积累足够多的对话记忆后，通过 digest()/reflect() 归纳出 personality trait。现有用户的 personality 通过迁移脚本转化为低置信度的 behavior trait（trend 阶段），等待后续反思引擎验证升级。
