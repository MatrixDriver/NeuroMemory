---
description: "技术可行性调研: Profile 统一架构"
status: completed
created_at: 2026-03-02T20:30:00
updated_at: 2026-03-02T20:30:00
---

# 技术可行性调研：Profile 统一架构

## 调研目标

评估将三套平行用户画像机制（KV Profile、Emotion Profile、v2 Trait）统一为 fact + trait + 计算视图架构的技术可行性、性能影响和迁移风险。

---

## 3.1 profile_view 查询性能

### 现状分析

**当前实现** (`_core.py:1370-1388`)：`_fetch_user_profile()` 从 KV 存储读取 7 个固定 key（identity, occupation, interests, preferences, values, relationships, personality），走 `ix_kv_ns_scope` 索引，本质是一次 `WHERE namespace='profile' AND scope_id=:uid` 查询，返回最多 7 行。

**改造后**：`profile_view()` 需要从三个数据源组装：

1. **fact 查询**：`WHERE user_id=:uid AND memory_type='fact' AND metadata->>'category' IN ('identity', 'occupation', ...)`
2. **trait 查询**：`WHERE user_id=:uid AND memory_type='trait' AND trait_stage IN ('emerging', 'established', 'core')`
3. **emotion 聚合**：近期 N 条 episodic 的 `metadata->'emotion'` 聚合

### 性能评估

| 维度 | KV 直读（现状） | profile_view（改造后） |
|------|----------------|----------------------|
| 查询次数 | 1 次 KV list | 2-3 次 memories 查询 |
| 扫描范围 | KV 表 ≤7 行 | memories 表按 user_id + type 过滤 |
| 索引利用 | `ix_kv_ns_scope` | `ix_mem_type_user(user_id, memory_type)` 可用 |
| JSONB 过滤 | 无 | `metadata->>'category'` 需额外评估 |
| 预计延迟 | <1ms | 3-10ms（取决于记忆总量） |

### JSONB 索引需求分析

**现有索引**（`memory.py:87-93`）：
- `ix_mem_user(user_id)` — 基础用户索引
- `ix_mem_type_user(user_id, memory_type)` — **可直接用于** `WHERE user_id=:uid AND memory_type='fact'`

**metadata->>'category' 查询**：在已用 `ix_mem_type_user` 缩窄到某用户全部 fact 后，再在内存中过滤 category。典型用户的 fact 数量在 50-500 条量级，内存过滤完全可接受，**暂不需要 JSONB GIN 索引**。

**SQLAlchemy JSONB 索引支持**（框架检查）：SQLAlchemy 支持通过 `Index('ix_name', Model.metadata_['category'].astext)` 创建函数索引，也支持 `postgresql_using='gin'` 创建 GIN 索引。若未来 fact 规模增长到万级别，可后期添加：
```python
Index("ix_mem_fact_category", Memory.metadata_["category"].astext,
      postgresql_where=Memory.memory_type == "fact")
```

### 结论

**可行**。性能从 <1ms 增至 3-10ms，对于 recall() 整体耗时（通常 100-500ms 含向量检索）影响可忽略。三个查询可用 `asyncio.gather()` 并行执行进一步压缩延迟。暂不需要新索引。

---

## 3.2 emotion metadata 实时聚合

### 现状分析

**episodic emotion 格式**（`memory_extraction.py:849-854`）：
```python
meta["emotion"] = {
    "valence": emotion.get("valence", 0),  # -1.0 ~ 1.0
    "arousal": emotion.get("arousal", 0),  # 0.0 ~ 1.0
    "label": emotion.get("label", ""),      # 如 "焦虑"、"兴奋"
}
```
存储在 `memories.metadata->'emotion'` JSONB 字段中。

**当前 meso 情绪**（`emotion_profile.py:34-53`）：由 `_update_emotion_profile()` 在 `digest()` 时批量计算后持久化到 `emotion_profiles` 表。

**改造后**：meso 情绪改为 recall 时实时聚合。

### SQL 实现评估

```sql
SELECT
    AVG((metadata->'emotion'->>'valence')::float) AS valence_avg,
    AVG((metadata->'emotion'->>'arousal')::float) AS arousal_avg,
    COUNT(*) AS sample_count
FROM memories
WHERE user_id = :uid
  AND memory_type = 'episodic'
  AND metadata->'emotion' IS NOT NULL
  AND created_at > NOW() - INTERVAL '14 days'
ORDER BY created_at DESC
LIMIT 50;
```

### 性能评估

- **扫描范围**：`ix_mem_type_user(user_id, memory_type)` 索引可用，缩窄到用户的 episodic 记忆
- **时间过滤**：`ix_mem_user_ts(user_id, extracted_timestamp)` 可用于时间范围过滤
- **JSONB 解析开销**：JSONB `->` 操作在 PostgreSQL 中为 O(1) 键查找，对 50 条记录的聚合耗时可忽略
- **预计延迟**：1-5ms
- **新索引需求**：**不需要**。现有 `ix_mem_type_user` + `ix_mem_user_ts` 组合足够

### 结论

**可行**。SQL 聚合简单高效，无需新索引。可作为 profile_view 的第三个并行查询。相比现有持久化方案，实时聚合能反映最新情绪状态而不必等 digest() 执行。

---

## 3.3 watermark 迁移

### 现状分析

**当前 watermark 位置**：`conversation_sessions.last_reflected_at`（`conversation.py:87-89`）
- 类型：`DateTime(timezone=True), nullable=True`
- 用途：记录最后一次 reflect/digest 处理到哪条记忆的时间戳
- 读取方式（`reflection.py:133-137`）：
  ```sql
  SELECT last_reflected_at FROM conversation_sessions
  WHERE user_id = :uid ORDER BY last_reflected_at DESC NULLS LAST LIMIT 1
  ```
- 更新方式（`reflection.py:528-548`）：UPDATE 或 INSERT（upsert）conversation_sessions

**reflection_cycles 表**（`reflection_cycle.py`）：已存在，记录每次反思运行的元数据：
- `user_id`, `trigger_type`, `trigger_value`
- `memories_scanned`, `traits_created/updated/dissolved`
- `started_at`, `completed_at`, `status`, `error_message`
- 索引：`idx_reflection_user(user_id, started_at)`

**目标**：将 watermark 迁移到 reflection_cycles 表，因为 watermark 是反思引擎的运维字段，不属于会话元数据。

### 迁移方案

**不需要新增列**。reflection_cycles 已有 `completed_at` 字段，可直接作为 watermark 使用：

```sql
-- 新的 watermark 查询
SELECT completed_at FROM reflection_cycles
WHERE user_id = :uid AND status = 'completed'
ORDER BY completed_at DESC LIMIT 1
```

**理由**：每次成功的 reflection cycle 的 `completed_at` 就是自然的 watermark —— 表示"到这个时间点的记忆都已经被反思处理过了"。

### 迁移步骤

1. 修改 `_scan_new_memories()` 和 `should_trigger()` 的 watermark 查询，从 `conversation_sessions` 改为 `reflection_cycles`
2. 修改 `_update_watermark()` 为在 `reflection_cycles` 中插入一条 completed 记录（而非更新 conversation_sessions）
3. 数据迁移：将现有 `conversation_sessions.last_reflected_at` 写入一条历史 `reflection_cycles` 记录
4. 后续可清理 `conversation_sessions.last_reflected_at` 列（非阻塞，可延迟）

### 兼容性风险

- `conversation_sessions` 表本身保留，仅移除 `last_reflected_at` 的使用
- `reflection_cycles` 表已存在，`idx_reflection_user(user_id, started_at)` 索引支持查询
- **需进一步验证**：如果 `completed_at` 为 NULL（status='running' 或 'failed'），watermark 查询需加 `WHERE status = 'completed'` 条件

### 结论

**可行且优雅**。不需要创建新表或新列，利用现有 reflection_cycles 表的 completed_at 作为自然 watermark。改动集中在 reflection.py 的 3 个方法中。

---

## 3.4 数据迁移安全性

### 迁移矩阵

| 源 | 目标 | 转换逻辑 | 复杂度 |
|----|------|----------|--------|
| KV `profile/identity` | fact (category=identity) | 字符串 → Memory 行 | 低 |
| KV `profile/occupation` | fact (category=occupation) | 字符串 → Memory 行 | 低 |
| KV `profile/interests` | trait (behavior/trend) | 数组 → 多条 Memory | 中 |
| KV `profile/preferences` | trait (behavior/trend) | 数组 → 多条 Memory | 中 |
| KV `profile/values` | trait (preference/trend) | 数组 → 多条 Memory | 中 |
| KV `profile/personality` | trait (behavior/trend) | 数组 → 多条 Memory | 中 |
| KV `profile/relationships` | fact (category=relationship) | 数组 → 多条 Memory | 中 |
| emotion_profiles.dominant_emotions | trait (behavior/trend) | JSONB → 多条 Memory | 中 |
| emotion_profiles.emotion_triggers | trait (behavior/trend) | JSONB → 多条 Memory | 中 |
| emotion_profiles.last_reflected_at | reflection_cycles 记录 | DateTime → 新行 | 低 |
| conversation_sessions.last_reflected_at | reflection_cycles 记录 | DateTime → 新行 | 低 |

### 事务保护方案

```python
async with nm._db.session() as session:
    async with session.begin():  # 自动事务
        # 1. 读取所有 KV profile 数据
        # 2. 读取所有 emotion_profiles 数据
        # 3. 批量创建 fact/trait Memory 对象
        # 4. 创建 reflection_cycles watermark 记录
        # 5. 如果一切成功，commit（由 begin() context manager 自动完成）
        # 6. 如果任何步骤失败，rollback（由 begin() context manager 自动完成）
```

SQLAlchemy async session 的 `session.begin()` context manager 天然提供事务保护：成功则 commit，异常则 rollback。

### embedding 生成问题

迁移时创建 Memory 行需要 embedding 向量。方案：
- **方案 A**：迁移脚本调用 Embedding Provider 实时生成向量 — 需要 API 配额，但数据量小（每用户 10-50 条）
- **方案 B**：使用零向量占位，标记 `metadata_.needs_reembed=True`，后续批量补充 — 不依赖外部 API，但临时降低检索质量

**建议**：方案 A，因为数据量极小（全部用户加起来预计不超过几百条），API 调用成本可忽略。

### dry-run 模式

```python
# dry-run: 只读取和计算，不 commit
async with session.begin():
    # ... 所有转换逻辑 ...
    if dry_run:
        await session.rollback()  # 预览完毕，不提交
        return preview_result
```

### 回滚策略

1. **迁移前**：自动备份 KV profile namespace 和 emotion_profiles 数据到临时表
2. **迁移中**：单一事务，失败自动 rollback
3. **迁移后**：保留原始 KV 数据 7 天，验证无误后再清理
4. **紧急回滚**：从临时备份表恢复 KV 数据和 emotion_profiles

### 结论

**可行**。数据量小、事务保护完善、dry-run 可预览。主要风险点是 embedding 生成需要 API 调用，但数据量极小可忽略。

---

## 3.5 extraction prompt 改造影响

### 当前 prompt 结构

**SDK 端**（`memory_extraction.py:332-340`，`456-464`）：
- `profile_updates` 作为第 4/5 个提取类别（中英文 prompt 均有）
- 输出结构：`{"facts": [...], "episodes": [...], "triples": [...], "profile_updates": {...}}`
- 7 个字段：identity, occupation, interests, preferences, values, relationships, personality

**Cloud 端**（`extraction_prompt.py:77-79`，`127-129`）：
- One-LLM 模式的 prompt 同样包含 `profile_updates` 部分
- 输出结构与 SDK 一致

### 改造方案

**删除 profile_updates 块**，identity/occupation 通过 fact 的 category 字段自然提取：

- **identity 信息**：现有 fact prompt 已要求提取"姓名、年龄、性别等核心身份信息"（`memory_extraction.py:381`），只需在 fact 的 category 选项中确保包含 `identity`/`personal` — **已存在**（当前 category 选项含 personal）
- **occupation 信息**：现有 fact prompt 已要求提取"职业/公司/职位信息"（`memory_extraction.py:386`），category 选项含 `work` — **已存在**

**改造点**：
1. 在 fact 的 category 说明中增加 `identity` 选项（明确区分 identity 和 personal）
2. 删除 `profile_updates` 的 prompt 段落和返回格式中的 `"profile_updates": {...}`
3. 删除 `_store_profile_updates()` 方法和 `_PROFILE_OVERWRITE_KEYS`/`_PROFILE_APPEND_KEYS` 常量
4. 删除 `_parse_classification_result()` 中 `profile_updates` 的解析

### 提取质量影响评估

| 信息类型 | 改造前（profile_updates） | 改造后（fact category） | 风险 |
|----------|--------------------------|------------------------|------|
| identity | 专用字段，覆写语义 | fact + category=identity | **低**：已在 fact 提取规则中覆盖 |
| occupation | 专用字段，覆写语义 | fact + category=work | **低**：已在 fact 提取规则中覆盖 |
| interests | 专用数组字段 | fact + category=hobby | **低**：fact 规则已要求提取兴趣 |
| preferences | 专用数组字段 | fact + category=personal | **低**：fact 规则已要求提取偏好 |
| values | 专用数组字段 | fact + category=personal | **中**：需确保 fact 提取不遗漏价值观 |
| personality | 专用数组字段 | 不再直接提取（等待 trait 归纳） | **中**：符合 v2 设计原则，但短期内新用户画像会更稀疏 |
| relationships | 专用数组字段 | fact + category=relationship | **低**：已有 relationship category |

**关键质量风险**：
1. personality 不再从单次对话直接提取，符合 v2 设计原则（trait 必须归纳产生），但新用户的冷启动期 personality 信息将为空，需等 digest() 后才有
2. values 信息可能在 fact 提取中被泛化或遗漏 — 建议在 fact prompt 的 category 说明中增加 `values` 明确选项

### Cloud 端 One-LLM 模式特殊考虑

Cloud 端的 `ingest_extracted` 函数（`core.py:143-268`）直接调用 `svc._store_profile_updates()`。改造后：
1. `extraction_prompt.py` 中删除 profile_updates 部分
2. `core.py` 中 `do_ingest_extracted()` 删除 profile_updates 处理逻辑
3. `schemas.py` 中 `IngestExtractedResponse` 删除 `profile_updates_stored` 字段
4. **兼容性**：旧版 SDK 客户端可能仍发送 `profile_updates`，`do_ingest_extracted()` 应静默忽略（不报错）

### 结论

**可行**。fact 的 extraction prompt 已具备提取 identity/occupation/interests/relationships 的能力，删除 profile_updates 不会导致信息丢失。主要需注意：
1. fact category 新增 `identity` 和 `values` 明确选项
2. personality 改为 trait 归纳（冷启动期为空，符合设计）
3. Cloud 端需兼容旧客户端（静默忽略 profile_updates）

---

## 4. 框架内置方案检查

### SQLAlchemy JSONB 索引支持

SQLAlchemy 2.0 完整支持 JSONB 操作和索引：

```python
# 函数索引
Index("ix_name", Model.metadata_["category"].astext)

# GIN 索引
Index("ix_name", Model.metadata_, postgresql_using="gin")

# 部分索引（仅 fact 类型）
Index("ix_name", Model.metadata_["category"].astext,
      postgresql_where=(Model.memory_type == "fact"))
```

**结论**：如需 JSONB 索引，SQLAlchemy 原生支持，无需 raw SQL。

### 批量迁移工具

- SQLAlchemy 的 `session.add_all()` 支持批量添加对象
- `session.begin()` context manager 提供自动事务管理
- 无需引入额外的迁移框架（如 Alembic），neuromem 项目使用内联 DDL
- **现有模式**：`db.py` 中的 `create_all()` 处理 schema 创建，可参考此模式添加迁移脚本

---

## 5. 总体评估

### 可行性矩阵

| 调研项 | 可行性 | 风险等级 | 需新索引 | 关键依赖 |
|--------|--------|----------|----------|----------|
| profile_view 查询 | 可行 | 低 | 否 | 现有 ix_mem_type_user |
| emotion 实时聚合 | 可行 | 低 | 否 | 现有 ix_mem_user_ts |
| watermark 迁移 | 可行 | 低 | 否 | 现有 reflection_cycles 表 |
| 数据迁移 | 可行 | 中 | 否 | Embedding API（数据量小） |
| prompt 改造 | 可行 | 中 | N/A | 需增加 fact category 选项 |

### 需进一步验证的点

1. **profile_view 缓存策略**：需求摘要中标注"延迟决策"，但如果 profile_view 在单次 recall 中被多次调用，建议至少做 request-level 缓存
2. **personality 冷启动**：去掉 profile_updates 后新用户需等待首次 digest() 才有 personality trait，需评估对下游（如 Me2 的 prompt 组装）的影响
3. **Cloud 旧客户端兼容窗口**：需确定支持多久的旧版本客户端（建议至少 2 个 minor version）

### 建议改造顺序

1. **extraction prompt 改造**（风险最低，可独立验证）
2. **profile_view 实现**（替换 `_fetch_user_profile()`）
3. **watermark 迁移**（reflection.py 内部改动，影响面小）
4. **emotion profile 删除**（依赖 profile_view 中的实时聚合替代）
5. **数据迁移脚本**（最后执行，依赖前 4 步完成）
6. **Cloud 端适配**（与 SDK 改造并行或紧随其后）

---

## 源码引用

| 文件 | 关键位置 | 说明 |
|------|----------|------|
| `neuromem/models/memory.py:87-93` | 现有 memories 表索引 | profile_view 查询可利用 |
| `neuromem/models/memory.py:31` | metadata_ JSONB 列 | category 字段存储位置 |
| `neuromem/models/memory.py:67-78` | trait 专用列 | trait_stage 等过滤条件 |
| `neuromem/models/emotion_profile.py:14-88` | EmotionProfile 表结构 | 待删除的表 |
| `neuromem/models/reflection_cycle.py:15-41` | ReflectionCycle 表结构 | watermark 迁移目标 |
| `neuromem/models/conversation.py:65-93` | ConversationSession | 现有 watermark 位置 |
| `neuromem/models/kv.py:12-33` | KeyValue 表结构 | 现有 profile 存储 |
| `neuromem/_core.py:1370-1388` | _fetch_user_profile() | 待替换为 profile_view() |
| `neuromem/services/memory_extraction.py:294-423` | extraction prompt | 含 profile_updates 段落 |
| `neuromem/services/memory_extraction.py:893-947` | _store_profile_updates() | 待删除 |
| `neuromem/services/reflection.py:528-548` | _update_watermark() | 待迁移到 reflection_cycles |
| `neuromem/services/reflection.py:738-835` | _update_emotion_profile() | 待删除 |
| `neuromem-cloud/server/src/neuromem_cloud/extraction_prompt.py` | Cloud extraction prompt | 含 profile_updates |
| `neuromem-cloud/server/src/neuromem_cloud/core.py:143-268` | do_ingest_extracted() | 含 profile_updates 处理 |
| `neuromem-cloud/server/src/neuromem_cloud/schemas.py:30` | IngestExtractedResponse | 含 profile_updates_stored |
