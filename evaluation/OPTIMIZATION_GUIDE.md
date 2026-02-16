# NeuroMemory LoCoMo 优化指南

基于 2025-02-16 测试结果的详细优化建议，用于指导下一轮性能提升。

## 📊 当前性能总览

| 类别 | 当前得分 | 问题数 | 难度 | 提升空间 |
|------|---------|--------|------|---------|
| **Temporal** | 0.087 | 321 | ⭐⭐⭐⭐⭐ | 最大 (~3-4x) |
| **Multi-hop** | 0.305 | 282 | ⭐⭐⭐⭐ | 大 (~1.5-2x) |
| **Single-hop** | 0.327 | 841 | ⭐⭐⭐ | 中 (~1.3-1.5x) |
| **Open-domain** | 0.344 | 96 | ⭐⭐ | 小 (~1.1-1.2x) |
| **Overall** | 0.274 | 1540 | - | 目标: 0.35-0.40 |

---

## 🎯 优先级路线图

### Phase 1: Temporal 时序记忆优化 (预期提升: 0.087 → 0.15-0.20)
**ROI**: 最高 - 得分最低，提升空间最大

#### P0: 专门的时间信息提取 [预期: +50-80%]
- **目标**: 识别并标准化时间表达式
- **实施步骤**:
  ```python
  # 在 neuromemory/services/memory_extraction.py

  # 1. 添加时间解析依赖
  from dateutil import parser
  from dateparser import parse as parse_time

  # 2. 在 _store_episodes 中提取时间
  def _extract_temporal_info(content: str, session_timestamp: datetime) -> dict:
      """提取时间信息"""
      # 使用正则或 NER 识别时间表达式
      # 标准化为 ISO 8601 格式
      # 保留原始表达
      return {
          "timestamp": "2023-05-07T00:00:00",
          "original_expression": "yesterday",
          "type": "relative"  # absolute/relative/fuzzy
      }

  # 3. 存储到 metadata
  meta["temporal"] = temporal_info
  ```

- **修改文件**:
  - `neuromemory/services/memory_extraction.py` - 添加时间提取逻辑
  - `neuromemory/models/memory.py` - 可选：添加时间索引

#### P0: 时间推理和计算 [预期: +40-60%]
- **目标**: 将相对时间转换为绝对时间
- **实施步骤**:
  ```python
  # 在 neuromemory/services/conversation.py

  def calculate_absolute_time(relative_expr: str, reference_time: datetime) -> datetime:
      """计算绝对时间"""
      # "yesterday" + reference_time = reference_time - 1 day
      # "last week" + reference_time = reference_time - 7 days
      # "4 years ago" + reference_time = reference_time - 4 years
      pass

  # 在 memory_extraction.py 的 prompt 中提供上下文
  prompt = f"""
  Current conversation session time: {session_timestamp}

  When extracting temporal information:
  - Convert relative time expressions to absolute dates
  - Example: "yesterday" at session {session_timestamp} = {session_timestamp - 1 day}
  """
  ```

- **修改文件**:
  - `neuromemory/services/memory_extraction.py` - 时间计算逻辑
  - `neuromemory/services/conversation.py` - 辅助函数

#### P1: 时间索引和查询优化 [预期: +20-30%]
- **实施步骤**:
  ```python
  # 在 neuromemory/services/search.py

  def search_by_time_range(
      user_id: str,
      start_time: datetime,
      end_time: datetime,
      limit: int = 10
  ):
      """按时间范围查询"""
      query = select(Embedding).where(
          Embedding.user_id == user_id,
          Embedding.metadata_['temporal']['timestamp'].astext.cast(DateTime) >= start_time,
          Embedding.metadata_['temporal']['timestamp'].astext.cast(DateTime) <= end_time
      )
      return await session.execute(query)
  ```

---

### Phase 2: Single-hop 事实查询优化 (预期提升: 0.327 → 0.40-0.45)
**ROI**: 高 - 占比最大（54.6%），优化影响面广

#### P0: 优化 Fact 提取的准确性 [预期: +15-25%]
- **目标**: 提取原子化、完整的事实
- **实施步骤**:
  ```python
  # 改进 fact 提取 prompt
  FACT_EXTRACTION_PROMPT = """
  Extract atomic facts from the conversation.

  Requirements:
  1. Each fact must be independent and complete
  2. Include subject, predicate, object
  3. Extract entity attributes, states, and behaviors
  4. Avoid redundancy

  Examples:
  - Good: "Caroline is a transgender woman"
  - Good: "Caroline works at a counseling center"
  - Bad: "She is trans" (incomplete, missing subject)
  - Bad: "Caroline is trans and works at a center" (not atomic)
  """
  ```

- **修改文件**: `neuromemory/services/memory_extraction.py`

#### P1: 增加关键词匹配 (Hybrid Search) [预期: +10-15%]
- **目标**: 结合 BM25 和向量检索
- **实施步骤**:
  ```python
  # 在 neuromemory/services/search.py

  # 1. 添加全文索引（数据库迁移）
  # CREATE INDEX idx_embeddings_content_fts ON embeddings USING gin(to_tsvector('english', content));

  # 2. 实现 BM25 检索
  def bm25_search(query: str, limit: int = 10):
      """BM25 关键词检索"""
      ts_query = func.plainto_tsquery('english', query)
      return select(Embedding).where(
          func.to_tsvector('english', Embedding.content).op('@@')(ts_query)
      ).order_by(
          func.ts_rank(func.to_tsvector('english', Embedding.content), ts_query).desc()
      ).limit(limit)

  # 3. 混合检索
  def hybrid_search(query: str, alpha: float = 0.5):
      """混合向量和关键词检索
      alpha: 向量检索权重 (0-1)
      """
      vector_results = await vector_search(query, limit=20)
      keyword_results = await bm25_search(query, limit=20)

      # 合并和重排序
      return merge_and_rerank(vector_results, keyword_results, alpha)
  ```

- **修改文件**:
  - `neuromemory/services/search.py` - 混合检索逻辑
  - `migrations/` - 添加全文索引

#### P1: Metadata 精确过滤 [预期: +10-15%]
- **实施步骤**:
  ```python
  # 提取更多结构化信息
  meta["entities"] = {
      "people": ["Caroline", "Melanie"],
      "locations": ["LGBTQ support group", "school"],
      "topics": ["transgender", "education", "family"]
  }

  # 支持过滤查询
  def search_with_filters(query: str, filters: dict):
      """带过滤条件的搜索"""
      base_query = vector_search(query, limit=50)

      # 应用 metadata 过滤
      if 'person' in filters:
          base_query = base_query.where(
              Embedding.metadata_['entities']['people'].contains([filters['person']])
          )

      return base_query
  ```

---

### Phase 3: Multi-hop 多跳推理优化 (预期提升: 0.305 → 0.40-0.45)
**ROI**: 中高 - 需要图数据库支持，实现复杂度高

#### P0: 增强知识图谱构建 [预期: +20-30%]
- **目标**: 改进实体识别和关系提取
- **实施步骤**:
  ```python
  # 改进 triple 提取 prompt
  TRIPLE_EXTRACTION_PROMPT = """
  Extract entity relationships as triples (subject, relation, object).

  Entity types to extract:
  - PERSON: people, their roles, identities
  - LOCATION: places, addresses, venues
  - EVENT: activities, meetings, conferences
  - CONCEPT: abstract ideas, topics, fields

  Relation types:
  - ATTRIBUTE: is_a, has_property, works_at
  - ACTION: researched, attended, planned
  - TEMPORAL: happened_at, lasted_for
  - SOCIAL: knows, friends_with, mentored_by
  - CAUSAL: causes, leads_to, because_of

  Also extract:
  - Entity aliases (e.g., "Caroline" = "she" in context)
  - Co-reference chains
  """
  ```

- **修改文件**:
  - `neuromemory/services/memory_extraction.py` - 改进 triple 提取
  - `neuromemory/services/graph_memory.py` - 支持更多关系类型

#### P1: 实现多跳推理路径搜索 [预期: +15-25%]
- **目标**: 使用 AGE (Apache AGE) Cypher 查询
- **实施步骤**:
  ```python
  # 在 neuromemory/services/graph_memory.py

  async def find_path(
      start_entity: str,
      end_entity: str,
      max_hops: int = 3
  ):
      """查找实体间的路径"""
      cypher_query = """
      MATCH path = (start:Entity {name: $start})-[*1..%d]-(end:Entity {name: $end})
      RETURN path
      ORDER BY length(path)
      LIMIT 10
      """ % max_hops

      # 执行 AGE 查询
      result = await execute_cypher(cypher_query, start=start_entity, end=end_entity)
      return parse_paths(result)

  async def find_related_memories(entity: str, hop: int = 2):
      """找到与实体相关的所有记忆"""
      cypher_query = """
      MATCH (e:Entity {name: $entity})-[*1..%d]-(related)
      RETURN related
      """ % hop

      return await execute_cypher(cypher_query, entity=entity)
  ```

- **修改文件**: `neuromemory/services/graph_memory.py`

#### P1: 混合检索策略 [预期: +10-15%]
- **实施步骤**:
  ```python
  # 在 neuromemory/services/search.py

  async def hybrid_vector_graph_search(query: str, user_id: str):
      """结合向量检索和图查询"""
      # 1. 向量召回相关记忆
      vector_results = await vector_search(query, limit=10)

      # 2. 提取记忆中的实体
      entities = extract_entities(vector_results)

      # 3. 在图中查找实体的关联记忆
      graph_results = []
      for entity in entities:
          related = await find_related_memories(entity, hop=2)
          graph_results.extend(related)

      # 4. 合并去重
      all_results = merge_results(vector_results, graph_results)

      # 5. 重排序
      return rerank(all_results, query)
  ```

- **修改文件**: `neuromemory/services/search.py`, `neuromemory/_core.py`

---

### Phase 4: Open-domain 开放域优化 (预期提升: 0.344 → 0.38-0.42)
**ROI**: 中 - 已经最高分，优化空间相对较小

#### P1: 增强概念性知识提取 [预期: +10-20%]
- **实施步骤**:
  ```python
  # 改进 fact 提取，关注抽象信息
  CONCEPT_EXTRACTION_PROMPT = """
  Extract conceptual and inferential facts:

  Focus on:
  1. User's intentions, plans, goals
  2. Interests, hobbies, passions
  3. Skills, abilities, competencies
  4. Values, beliefs, principles
  5. Preferences, dislikes
  6. Personality traits
  7. Causal relationships
  8. Reasoning chains

  Example:
  - "She is interested in psychology" (interest)
  - "She plans to get a counseling certification" (intention)
  - "She values family support" (value)
  """
  ```

- **修改文件**: `neuromemory/services/memory_extraction.py`

#### P2: 改进语义召回精度 [预期: +5-10%]
- **实施步骤**:
  ```python
  # 增加 top_k
  recall_limit = 20  # 从 10 增加到 20

  # 实现 reranking
  def rerank_results(query: str, results: List[Memory]):
      """使用 cross-encoder 重排序"""
      from sentence_transformers import CrossEncoder
      model = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')

      pairs = [(query, r.content) for r in results]
      scores = model.predict(pairs)

      # 按分数重新排序
      ranked = sorted(zip(results, scores), key=lambda x: x[1], reverse=True)
      return [r for r, s in ranked]
  ```

- **修改文件**: `neuromemory/services/search.py`

---

## 🛠️ 实施建议

### 推荐实施顺序

1. **Week 1-2: Temporal 优化 (P0 任务)**
   - 专门的时间信息提取
   - 时间推理和计算
   - **预期**: 0.087 → 0.15+ (Judge 分数)

2. **Week 3-4: Single-hop 优化 (P0-P1 任务)**
   - 优化 Fact 提取
   - 增加关键词匹配 (Hybrid Search)
   - Metadata 精确过滤
   - **预期**: 0.327 → 0.42+ (Judge 分数)

3. **Week 5-6: Multi-hop 优化 (P0-P1 任务)**
   - 增强知识图谱构建
   - 实现多跳推理路径搜索
   - 混合检索策略
   - **预期**: 0.305 → 0.42+ (Judge 分数)

4. **Week 7-8: Open-domain 优化 + 集成测试**
   - 增强概念性知识提取
   - 改进语义召回精度
   - 全面集成测试和调优
   - **预期**: 0.344 → 0.40+ (Judge 分数)

### 预期最终结果

| 类别 | 当前 | 目标 | 提升 |
|------|-----|------|------|
| Temporal | 0.087 | 0.15-0.20 | +72-130% |
| Single-hop | 0.327 | 0.42-0.45 | +28-38% |
| Multi-hop | 0.305 | 0.40-0.45 | +31-48% |
| Open-domain | 0.344 | 0.38-0.42 | +10-22% |
| **Overall** | **0.274** | **0.35-0.40** | **+28-46%** |

---

## 📋 测试清单

每次优化后都应该运行完整的 LoCoMo 评测：

```bash
# 1. 确保使用独立数据库容器
docker compose -f docker-compose-eval.yml up -d

# 2. 运行测试
python -m evaluation.cli locomo

# 3. 记录结果
python evaluation/scripts/add_test_record.py \
  2025-XX-XX_<optimization_name> \
  "<Description>" \
  evaluation/results/locomo_results.json \
  "优化措施1" "优化措施2"

# 4. 对比结果
python evaluation/scripts/compare_history.py \
  2025-02-16_perf_opt \
  2025-XX-XX_<optimization_name>
```

---

## 💡 额外建议

1. **渐进式优化**: 不要一次性实施所有优化，逐步测试验证
2. **A/B 测试**: 保留原有代码分支，对比优化效果
3. **监控关键指标**: 除了 Judge 分数，也关注 F1 和 BLEU-1
4. **代码审查**: 优化可能引入 bug，需要仔细测试
5. **性能监控**: 确保优化不会显著降低速度

---

## 📚 参考资料

- **测试记录**: `evaluation/history/2025-02-16_perf_opt.json`
- **详细分析**: 文件中的 `category_optimization_analysis` 字段
- **对比脚本**: `evaluation/scripts/compare_history.py`
- **LoCoMo 数据**: `evaluation/data/locomo10.json`

---

**最后更新**: 2025-02-16
**基于测试**: 2025-02-16_perf_opt (commit e7c0f3d5)
**目标**: 将 Overall Judge 分数从 0.274 提升到 0.35-0.40
