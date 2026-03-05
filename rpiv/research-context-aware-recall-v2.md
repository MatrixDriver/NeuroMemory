---
description: "技术可行性调研: context-aware-recall-v2"
status: completed
created_at: 2026-03-05T17:00:00
updated_at: 2026-03-05T17:00:00
archived_at: null
---

# 技术可行性调研: context-aware-recall-v2

## 调研目标

针对需求摘要 `brainstorm-summary-context-aware-recall-v2.md` 中的四个场景，逐一验证技术可行性，确认 SDK 内置能力和改动点。

---

## A. ContextService 参数机制

**源码**: `neuromem/services/context.py:173-184`

### 现有参数

| 参数 | 当前值 | 含义 |
|------|--------|------|
| `MARGIN_THRESHOLD` | 0.05 | 最高分与次高分的 margin 低于此值则判为 general |
| `MAX_CONTEXT_BOOST` | 0.10 | context 匹配时的最大加分（当前未直接使用，实际 boost 在 search.py 中硬编码） |
| `GENERAL_CONTEXT_BOOST` | 0.07 | general context 的 boost 力度 |
| `CONFIDENCE_NORMALIZER` | 0.15 | 将 margin 归一化为 0~1 的置信度 |

### 参数修改副作用分析

- **MARGIN_THRESHOLD**: 降低阈值（如 0.05 -> 0.02）会让更多查询被判为特定 context 而非 general。无副作用，因为该值仅影响 `infer_context()` 的返回值，不影响任何持久化数据。
- **MAX_CONTEXT_BOOST**: 当前实际 boost 值在 `search.py:355-358` 中硬编码为 `0.10 * context_confidence`（匹配 trait）和 `0.07 * context_confidence`（general trait），**并未引用** `MAX_CONTEXT_BOOST` 类属性。需要将硬编码值改为引用 ContextService 的参数。
- 参数修改是纯计算层，**不影响数据库**，可随时调整。

### 关键发现

1. `infer_context()` 有 keyword fallback（`_infer_context_keywords`），当 embedding margin 不足时用关键词匹配，这是一道安全网。
2. `ensure_prototypes()` 是惰性初始化，首次调用需要一次 `embed_batch()`（约 120 句），后续缓存在内存中。
3. A/B 实验只需修改类属性值即可，无需改数据结构。

### 结论: **完全可行，零风险**

---

## B. Extraction Prompt 现有结构

**源码**: `neuromem/services/memory_extraction.py:291-527`

### Prompt 结构分析

- 中文 prompt: `_build_zh_prompt()` (L298-411)
- 英文 prompt: `_build_en_prompt()` (L413-526)
- 两个 prompt 结构完全对称，都输出 `{"facts": [...], "episodes": [...]}`

### Fact JSON Schema 当前字段

```json
{
  "content": "事实描述",
  "category": "分类",
  "temporality": "current|prospective|historical",
  "confidence": 0.0-1.0,
  "importance": 1-10,
  "entities": {"people": [], "locations": [], "topics": []},
  "emotion": {"valence": -1.0~1.0, "arousal": 0.0~1.0, "label": "..."}
}
```

### 如何添加 context 字段

**方案**: 在 fact 和 episode 的 JSON schema 中添加 `"context"` 字段，白名单: work/personal/social/learning/general。

**改动点**:
1. `_build_zh_prompt()` 和 `_build_en_prompt()` 各加一行 context 字段说明 + 示例
2. `_store_facts()` (L663-801): 解析 `fact.get("context")` 并写入 `trait_context` 列
3. `_store_episodes()` (L803-912): 同理

**不增加 LLM 调用**: context 标注复用已有的 extraction LLM 调用，只是在同一次 prompt 中多要求一个字段。对 token 消耗的影响约 +5%（每条记忆多一个 context 标签值）。

### JSON 解析逻辑

`_parse_classification_result()` (L558-601) 使用 `json.loads()` + JSON 修复。新增字段不影响解析，因为它直接从 dict 取值（`fact.get("context")`），缺失时返回 None。

### 降级策略

在 `_store_facts()` 和 `_store_episodes()` 中：
```python
context = fact.get("context", "general")
if context not in {"work", "personal", "social", "learning", "general"}:
    context = "general"
```

### 结论: **完全可行，改动量小（约 40 行）**

---

## C. trait_context 列的可用性

**源码**: `neuromem/models/memory.py:70`, `neuromem/db.py:113`

### 现状

- `trait_context` 列**已存在于 memories 表**（所有 memory_type 共享同一张表）
- 类型: `VARCHAR(20)`，nullable
- ORM 映射: `Memory.trait_context: Mapped[str | None]`
- 已有索引: `idx_trait_context ON memories (user_id, trait_context) WHERE trait_context IS NOT NULL` (`db.py:222-223`)
- DDL 迁移: `ALTER TABLE memories ADD COLUMN IF NOT EXISTS trait_context VARCHAR(20)` (`db.py:113`) — 幂等

### fact/episodic 是否可用

`trait_context` 列名虽然以 `trait_` 为前缀，但它定义在 `memories` 表上，**fact 和 episodic 记忆同样可以使用此列**。当前只有 trait 类型在写入时赋值（`trait_engine.py:116,193`），fact/episodic 写入时未赋值（默认 NULL）。

### 需要的改动

1. **无 DDL 变更**: 列已存在，索引已存在
2. 在 `_store_facts()` 和 `_store_episodes()` 中写入 `trait_context` 值:
   ```python
   embedding_obj = Memory(
       ...,
       trait_context=context,  # 新增
   )
   ```
3. 在 `search.py` 的 context_bonus_sql 中，去掉 `memory_type = 'trait'` 的限制，让 fact/episodic 也参与 context boost

### 结论: **完全可行，零 DDL 变更，复用现有列和索引**

---

## D. Recall Boost 现有逻辑

**源码**: `neuromem/services/search.py:248-464`

### 当前 context boost 实现

`scored_search()` 方法中的 context_bonus_sql（L348-363）:

```sql
CASE
  WHEN memory_type = 'trait' AND trait_context = '{query_context}'
  THEN {0.10 * context_confidence}
  WHEN memory_type = 'trait' AND trait_context = 'general'
  THEN {0.07 * context_confidence}
  ELSE 0
END
```

**当前限制**: 只对 `memory_type = 'trait'` 生效，fact/episodic 的 context_match 始终为 0。

### 最终评分公式

```
score = prospective_penalty
      * LEAST(vector_score + bm25_hit*0.05, 1.0)
      * (1.0 + recency + importance + trait_boost + emotion_match + context_match)
```

各 bonus 范围:
- recency: 0~0.15
- importance: 0~0.15
- trait_boost: 0~0.25（core trait）
- emotion_match: 0~0.10
- context_match: 0~0.10

### 改造方案

将 context_bonus_sql 改为:

```sql
CASE
  WHEN trait_context = '{query_context}'
  THEN {MAX_CONTEXT_BOOST * context_confidence}
  WHEN trait_context = 'general'
  THEN {GENERAL_CONTEXT_BOOST * context_confidence}
  ELSE 0
END
```

- 去掉 `memory_type = 'trait'` 限制
- 引用 ContextService 的参数而非硬编码
- NULL trait_context 不参与 boost（CASE 的 ELSE 0 已覆盖）

### boost 力度分析

以 aggressive 参数组（MAX_CONTEXT_BOOST=0.20）为例:
- query context=work, memory context=work, confidence=0.8 -> boost = 0.16
- 占最终 score 的比例: 约 10-12%（因 base relevance 通常 0.7~0.9, multiplier 通常 1.3~1.7）
- 这足以将同一 vector_score 的记忆重排 1-2 个位置

### 结论: **完全可行，改动约 10 行**

---

## E. Embedding 回填方案

### Context Prototype 向量获取

`ContextService.ensure_prototypes()` (L190-226) 将 120 条原型句子 embedding 后取平均，得到 4 个 prototype 向量（work/personal/social/learning）。

**回填脚本可直接复用**:
```python
ctx_service = ContextService(embedding_provider)
await ctx_service.ensure_prototypes()
# ctx_service._prototypes 即为 4 个 prototype 向量
```

### 回填逻辑

```python
# 1. 查询所有 fact/episodic 且 trait_context IS NULL 的记忆
# 2. 逐条取 embedding，与 4 个 prototype 计算余弦相似度
# 3. 取最高分，若 margin > threshold 则标注，否则标 general
# 4. UPDATE memories SET trait_context = :ctx WHERE id = :id
```

### 数据库访问方式

- 读取: `SELECT id, embedding FROM memories WHERE memory_type IN ('fact', 'episodic') AND trait_context IS NULL`
- 写入: `UPDATE memories SET trait_context = :ctx WHERE id = :id`
- 可通过 `nm._db.session()` 获取 AsyncSession

### 性能估算

- **embedding 计算**: 回填**不需要**调用 embedding API。记忆的 embedding 已存储在数据库中，只需读取。
- **prototype 初始化**: 首次调用需 1 次 `embed_batch(120)`，约 0.5-1 秒
- **余弦相似度计算**: 纯 Python，每条记忆 4 次余弦（对 4 个 prototype），1536 维向量约 0.1ms/次
- **数据库 I/O**: 每条 1 次 SELECT + 1 次 UPDATE
- **总估算**:
  - 110 条记忆: < 5 秒（含数据库 I/O）
  - 10,000 条记忆: < 60 秒
  - 100,000 条记忆: 约 10 分钟（瓶颈在数据库 round-trip，可批量 UPDATE 优化）

### 批量优化建议

```sql
-- 批量读取 embedding（避免逐条查询）
SELECT id, embedding FROM memories
WHERE memory_type IN ('fact', 'episodic') AND trait_context IS NULL
ORDER BY id;

-- 批量更新（每 100 条一批）
UPDATE memories SET trait_context = CASE id
  WHEN :id1 THEN :ctx1
  WHEN :id2 THEN :ctx2
  ...
END
WHERE id IN (:id1, :id2, ...);
```

### 幂等性

脚本可重复运行：`WHERE trait_context IS NULL` 确保已标注的记忆不会被重新处理。

### 结论: **完全可行，零 LLM 消耗，110 条记忆 < 5 秒**

---

## 总结

| 调研点 | 可行性 | 风险 | 改动量 | DDL 变更 |
|--------|--------|------|--------|----------|
| A. 参数调优 | 可行 | 零 | ~5 行 | 无 |
| B. Extraction Prompt | 可行 | 低 | ~40 行 | 无 |
| C. trait_context 列 | 可行 | 零 | ~5 行 | 无 |
| D. Recall Boost | 可行 | 低 | ~10 行 | 无 |
| E. Embedding 回填 | 可行 | 低 | ~80 行脚本 | 无 |

**关键发现**:
1. **零 DDL 变更**: trait_context 列已存在于 memories 表，fact/episodic 可直接复用
2. **零额外 LLM 调用**: extraction 标注复用已有调用，回填用 embedding 相似度
3. **search.py 的 context boost 当前仅对 trait 生效**，需去掉 `memory_type = 'trait'` 限制
4. **MAX_CONTEXT_BOOST 参数未被实际引用**，search.py 中硬编码了 0.10/0.07，需改为引用 ContextService 属性
5. **所有改动集中在 3 个文件**: `context.py`（参数）、`memory_extraction.py`（prompt + 存储）、`search.py`（boost 逻辑）+ 1 个独立回填脚本
