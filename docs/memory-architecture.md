# 混合记忆架构 (Hybrid Memory Architecture)

## 概述

NeuroMemory 采用混合记忆架构，根据记忆类型选择最适合的存储和检索方式。这一设计参考了认知科学中的记忆分类理论，以及 Zep (arXiv:2501.13956)、Mem0g (arXiv:2504.19413) 等系统的实践经验。

## 记忆类型与存储策略

| 记忆类型 | 认知科学对应 | 存储方式 | 检索方式 | 示例 |
|----------|------------|----------|---------|------|
| **事实 Facts** | 语义记忆 | 图三元组 + 向量（双写） | 图遍历 + 向量搜索 | "在 Google 工作" |
| **情景 Episodes** | 情景记忆 | 向量 embedding | 语义相似搜索 | "昨天面试了一家公司" |
| **关系 Triples** | 语义记忆 | 图边 | 实体遍历 | `(user)-[HAS_SKILL]->(Python)` |
| **偏好 Preferences** | 语义记忆 | KV (Profile) | 精确 key 查找 | `["喜欢喝咖啡", "偏好深色模式"]` |

### 为什么双写事实？

- **向量搜索**擅长模糊语义匹配（"工作相关的信息"），但对精确事实召回不可靠
- **图存储**天然建模实体关系，支持多跳推理和时态跟踪
- 双写确保两种检索路径都能命中事实类记忆

## 数据流

```
对话消息
  │
  ▼
LLM 记忆提取 (MemoryExtractionService)
  │
  ├── Facts → Embedding Store (语义搜索) + Graph Store (关系查询)
  ├── Episodes → Embedding Store (语义搜索)
  ├── Triples → Graph Store (实体关系)
  └── Profile Updates (含偏好) → KV Store (精确查找)
```

## 时态模型

参考 Zep 的双时态设计，图边包含时间属性：

- `valid_from`: 事实生效时间
- `valid_until`: 事实失效时间（`null` 表示当前有效）

当事实发生变化时（如换工作），旧边标记 `valid_until=now`，新边 `valid_from=now`。查询时自动过滤失效边。

```
时间线:
t1: (user)-[WORKS_AT {valid_from=t1}]->(Google)
t2: (user)-[WORKS_AT {valid_from=t1, valid_until=t2}]->(Google)  ← 失效
    (user)-[WORKS_AT {valid_from=t2}]->(Meta)                    ← 新增
```

## 冲突解决

当新三元组到达时，`GraphMemoryService._resolve_conflict` 执行以下判定：

| 条件 | 操作 |
|------|------|
| 无已有活跃边（同主语+同关系） | **ADD** - 直接创建 |
| 已有活跃边，且客体相同 | **NOOP** - 跳过 |
| 已有活跃边，但客体不同 | **UPDATE** - 旧边失效 + 新边创建 |

## 情感标注 (Emotional Tagging)

参考 LeDoux 1996 情感标记增强记忆编码理论和 Russell 1980 Circumplex 模型。

LLM 提取记忆时同时标注情感维度，存入 metadata：

```json
{
  "emotion": {
    "valence": -0.8,
    "arousal": 0.7,
    "label": "焦虑"
  },
  "importance": 9
}
```

- **valence**: 正面(1.0) / 负面(-1.0)
- **arousal**: 高兴奋(1.0) / 低兴奋(0.0)
- **label**: 可选的情感描述词

情感标注仅基于对话文本中明确表达的情感，不推测用户内心感受。

## 重要性评分 (Importance Scoring)

参考 Generative Agents (Park et al. 2023)。每条记忆有 1-10 的重要性评分：
- 1-2: 随口一提（天气、时间等）
- 5: 日常信息
- 8-9: 重要事件（生日、重大人生事件）
- 10: 核心身份信息

## 检索方式

### `search()` - 纯向量搜索

```python
results = await nm.search(user_id="u1", query="workplace", limit=5)
```

保持向后兼容，仅使用 pgvector 语义搜索。搜索后自动更新访问计数。

### `recall()` - 三因子混合检索

```python
result = await nm.recall(user_id="u1", query="workplace", limit=10)
# result = {
#     "vector_results": [...],  # 三因子评分搜索
#     "graph_results": [...],   # 图实体遍历结果
#     "merged": [...],          # 去重合并
# }
```

使用三因子评分（参考 Generative Agents + Ebbinghaus 遗忘曲线）：

```
score = relevance × recency × importance
```

- **relevance**: 余弦相似度 (0-1)
- **recency**: 指数衰减 `e^(-t/S)`，高 arousal 记忆衰减更慢
- **importance**: metadata 中的重要性评分 (1-10 映射到 0.1-1.0)

### 访问追踪

每次检索命中后自动更新 `access_count` 和 `last_accessed_at`，为后续遗忘曲线优化提供数据。

## 反思机制 (Reflection)

参考 Generative Agents 的反思设计 — 从近期记忆中提炼高层次洞察。

```python
result = await nm.reflect(user_id="u1", limit=50)
# result = {
#     "reflections_generated": 3,
#     "reflections": [
#         {"content": "用户是一名工程师，注重效率", "category": "insight"},
#         ...
#     ]
# }
```

反思类别：
- **pattern**: 行为模式或习惯
- **summary**: 阶段性总结
- **insight**: 深层理解

反思结果存为 `memory_type="reflection"` 的 embedding，可在后续检索中被召回。

可配置自动反思：

```python
ExtractionStrategy(
    reflection_interval=3,  # 每 3 次提取后自动反思
)
```

## 配置

```python
nm = NeuroMemory(
    database_url="postgresql+asyncpg://...",
    embedding=SiliconFlowEmbedding(api_key="..."),
    llm=OpenAILLM(api_key="..."),
    graph_enabled=True,  # 启用图记忆
)
```

`graph_enabled=False`（默认）时，行为与之前完全一致。

## 竞品对比

| 特性 | NeuroMemory | Mem0 | Zep | Cognee |
|------|------------|------|-----|--------|
| 向量记忆 | pgvector | Qdrant | pgvector | 多种 |
| 图记忆 | Apache AGE | Neo4j | Neo4j | NetworkX/Neo4j |
| KV 画像/偏好 | PostgreSQL (Profile) | - | - | - |
| 时态模型 | valid_from/until | - | 双时态 | - |
| 冲突解决 | 启发式规则 | LLM | LLM | - |
| 部署方式 | Python 框架 | 托管 API | 托管 API | Python 框架 |
| 数据库 | 仅 PostgreSQL | 多种 | PostgreSQL + Neo4j | 多种 |

NeuroMemory 的优势在于：
- **单一数据库**：PostgreSQL 同时提供关系、向量、图能力，无需部署多个数据库
- **框架模式**：直接嵌入 agent 程序，无需部署和维护独立服务
- **KV 画像**：用户画像（含偏好）存入 Profile，精确查找无需语义搜索
