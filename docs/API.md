# NeuroMemory API 参考文档

> **版本**: 0.4.x
> **Python**: 3.12+
> **最后更新**: 2026-02-24

---

## 目录

- [初始化](#初始化)
- [易混淆 API 说明](#易混淆-api-说明) ⚠️ **必读**
- [核心 API](#核心-api)
  - [写入 API 对比](#写入-api-对比)
    - [add_message() - 添加对话消息](#add_message---添加对话消息) ⭐ **最常用**
    - [add_memory() - 直接添加记忆](#add_memory---直接添加记忆)
  - [检索 API 对比](#检索-api-对比)
    - [recall() - 混合检索](#recall---混合检索) ⭐ **推荐**
    - [search() - 向量检索](#search---向量检索)
  - [记忆管理 API 对比](#记忆管理-api-对比)
    - [extract_memories() - 提取记忆](#extract_memories---提取记忆)
    - [reflect() - 记忆整理](#reflect---记忆整理)
- [对话管理（完整 API）](#对话管理完整-api)
- [KV 存储](#kv-存储)
- [文件管理](#文件管理)
- [图数据库](#图数据库)
- [Provider 接口](#provider-接口)
- [常见使用模式](#常见使用模式)

---

## 初始化

### NeuroMemory(...)

```python
from neuromemory import NeuroMemory, SiliconFlowEmbedding, OpenAILLM, S3Storage

nm = NeuroMemory(
    database_url: str,
    embedding: EmbeddingProvider,
    llm: LLMProvider | None = None,
    storage: ObjectStorage | None = None,
    auto_extract: bool = True,
    graph_enabled: bool = False,
    pool_size: int = 10,
    echo: bool = False,
    reflection_interval: int = 20,
)
```

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `database_url` | `str` | ✅ | PostgreSQL 连接字符串，格式：`postgresql+asyncpg://user:pass@host:port/db` |
| `embedding` | `EmbeddingProvider` | ✅ | Embedding 提供者（SiliconFlowEmbedding / OpenAIEmbedding） |
| `llm` | `LLMProvider` | ❌ | LLM 提供者，用于自动提取和 `reflect()` |
| `storage` | `ObjectStorage` | ❌ | 对象存储，用于文件管理（S3Storage） |
| `auto_extract` | `bool` | ❌ | 是否自动提取记忆（每次 `add_message()` 时），默认 `True` |
| `reflection_interval` | `int` | ❌ | 每 N 次提取后自动在后台运行 `reflect()`（0 = 禁用，默认 `20`）。需要配置 `llm`。 |
| `graph_enabled` | `bool` | ❌ | 是否启用图数据库（关系表实现），默认 False |
| `pool_size` | `int` | ❌ | 数据库连接池大小，默认 10 |
| `echo` | `bool` | ❌ | 是否输出 SQL 日志，默认 `False`（调试用） |

**示例**：

```python
# 默认模式：自动提取（推荐）
async with NeuroMemory(
    database_url="postgresql+asyncpg://neuromemory:neuromemory@localhost:5432/neuromemory",
    embedding=SiliconFlowEmbedding(api_key="sk-xxx"),
    llm=OpenAILLM(api_key="sk-xxx", model="deepseek-chat"),
    auto_extract=True,  # 默认，每次 add_message 自动提取
) as nm:
    # 每次 add_message 都会自动提取记忆
    await nm.conversations.add_message(user_id="alice", role="user", content="I work at Google")
    # → 自动提取: fact: "在 Google 工作"

# 手动模式：关闭自动提取
async with NeuroMemory(
    database_url="...",
    embedding=SiliconFlowEmbedding(api_key="sk-xxx"),
    llm=OpenAILLM(api_key="sk-xxx", model="deepseek-chat"),
    auto_extract=False,  # 关闭自动提取
) as nm:
    await nm.conversations.add_message(user_id="alice", role="user", content="I work at Google")
    await nm.reflect(user_id="alice")  # 手动触发：提取记忆 + 生成洞察
```

---

## 易混淆 API 说明

NeuroMemory 有三组容易混淆的 API，请先理解它们的区别：

### ✏️ 写入 API：add_message() vs add_memory()

| API | 用途 | 写入目标 | 何时使用 |
|-----|------|---------|---------|
| **add_message()** ⭐ | 存储对话消息 + 自动提取记忆 | 对话历史表 + 记忆表（默认 `auto_extract=True`） | **日常使用（推荐）**：对话驱动，记忆自动提取 |
| **add_memory()** | 直接写入记忆 | 记忆表（embedding） | **特定场景**：手动导入、批量初始化、已知结构化信息 |

**示例对比**：
```python
# add_message(): 对话驱动（推荐），默认自动提取
# v0.2.0: 一次调用即可，自动提取记忆
await nm.conversations.add_message(user_id="alice", role="user",
    content="我在 Google 工作，做后端开发")
# → 自动提取: fact: "在 Google 工作", fact: "做后端开发"
# → 自动标注: importance=8, emotion={valence: 0.3, arousal: 0.2}
# → 立即可检索

# add_memory(): 直接写入（手动指定一切）
await nm.add_memory(user_id="alice", content="在 Google 工作",
    memory_type="fact", metadata={"importance": 8})
# → 直接存入记忆库，不经过对话和 LLM 提取
```

**核心区别**：
- `add_message()`: **对话驱动 + 自动提取** - 存对话 → LLM 自动提取记忆（含情感、重要性）→ 立即可用
- `add_memory()`: **手动写入** - 跳过对话，直接存记忆（需自行指定类型和元数据）

---

### 📚 检索 API：recall() vs search()

| API | 用途 | 检索方式 | 何时使用 |
|-----|------|---------|---------|
| **recall()** ⭐ | 智能混合检索 | 三因子向量（相关性×时效×重要性）+ 图实体检索 + 去重 | **日常使用（推荐）**：需要考虑时间、重要性的综合召回 |
| **search()** | 纯语义检索 | 仅 embedding 余弦相似度 | **特定场景**：只需语义相似度，不考虑时间和重要性 |

**示例对比**：
```python
# recall(): 综合考虑，最近的重要记忆优先
result = await nm.recall(user_id="alice", query="工作")
# → "昨天面试 Google"（最近 + 重要）优先于 "去年在微软实习"（久远）

# search(): 只看语义，可能返回很久以前的记忆
results = await nm.search(user_id="alice", query="工作")
# → "去年在微软实习" 和 "昨天面试 Google" 都可能返回，只按相似度排序
```

---

### 🧠 记忆管理 API：reflect() vs extract_memories()

| API | 用途 | 处理内容 | 何时使用 |
|-----|------|---------|---------|
| **reflect()** ⭐ | 生成洞察 + 更新画像 | 生成行为模式、阶段总结 + 更新情感画像 | **定期调用**：分析记忆、提炼洞察 |
| **extract_memories()** | 提取基础记忆 | 从对话中提取事实/偏好/关系（不生成洞察） | **内部使用**：由 `auto_extract` 自动调用 |

**示例（v0.2.0）**：
```python
# 默认模式：add_message() 自动提取基础记忆
await nm.conversations.add_message(user_id="alice", role="user", content="我在 Google 工作")
# → 自动提取: fact: "在 Google 工作", relation: (alice)-[works_at]->(Google)
# → 立即可通过 recall() 检索

# reflect(): 定期调用，生成洞察
result = await nm.reflect(user_id="alice")
# → 洞察: "用户近期求职，面试了 Google 和微软"
# → 画像: 更新情感状态
# → 不再重复提取基础事实（已由 add_message 完成）

# extract_memories(): 内部方法，由 auto_extract 自动调用
# 通常不需要直接调用
```

**核心区别（v0.2.0）**：
- `reflect()`: **洞察生成** - 分析已有记忆，生成行为模式和阶段总结
- `extract_memories()`: **基础提取** - 从对话提取事实，由 `add_message()` 自动调用（内部）

---

## 核心 API

## 写入 API 对比

这两个 API 都用于"写入"数据，但写入目标不同。**日常使用推荐 add_message()**。

### add_message() - 添加对话消息

**最常用的 API**，用于存储用户和 assistant 的对话消息。**v0.2.0 起默认自动提取记忆**，这是构建对话 agent 的核心操作。

```python
message = await nm.conversations.add_message(
    user_id: str,
    role: str,
    content: str,
    session_id: str | None = None,
    metadata: dict | None = None,
) -> ConversationMessage
```

**行为变化（v0.2.0）**：
- 当 `auto_extract=True`（默认）时，每次调用会自动提取记忆到记忆库
- 提取的记忆立即可通过 `recall()` 或 `search()` 检索
- 如需关闭自动提取，初始化时设置 `auto_extract=False`

**参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `user_id` | `str` | - | 用户 ID |
| `role` | `str` | - | 角色：`"user"` 或 `"assistant"` |
| `content` | `str` | - | 消息内容 |
| `session_id` | `str` | `None` | 会话 ID，为 None 时自动创建新会话 |
| `metadata` | `dict` | `None` | 元数据（可选） |

**返回**：`ConversationMessage` 对象，包含 `id`, `session_id`, `role`, `content`, `created_at`

**典型使用流程（v0.2.0）**：

```python
# 1. 用户发送消息（自动提取记忆）
await nm.conversations.add_message(
    user_id="alice",
    role="user",
    content="我在 Google 工作，做后端开发"
)
# → 自动提取: fact: "在 Google 工作", fact: "做后端开发"

# 2. 召回相关记忆（立即可用）
result = await nm.recall(user_id="alice", query="工作", limit=5)

# 3. 基于记忆生成回复（使用你的 LLM）
reply = your_llm.generate(
    context=result["merged"],
    user_input="我在 Google 工作，做后端开发"
)

# 4. 存储 assistant 回复（自动提取记忆）
await nm.conversations.add_message(
    user_id="alice",
    role="assistant",
    content=reply
)

# 5. 定期生成洞察（可选）
# await nm.reflect(user_id="alice")  # 生成行为模式和阶段总结
```

**使用场景**：

| 场景 | 说明 | 代码示例 |
|------|------|---------|
| **聊天机器人** | 存储用户和 bot 的每轮对话 | `await nm.conversations.add_message(user_id, "user", input)` |
| **客服系统** | 记录客服与用户的完整对话历史 | 每次对话都调用 `add_message()` |
| **AI 导师** | 追踪学生的学习对话，分析进度 | 存储所有问答，定期 `reflect()` |
| **个人助手** | 构建长期对话记忆，理解用户习惯 | 结合 `recall()` 提供个性化回复 |

**进阶：批量添加消息**

```python
# 导入历史对话
session_id, msg_ids = await nm.conversations.add_messages_batch(
    user_id="alice",
    messages=[
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！有什么可以帮你？"},
        {"role": "user", "content": "介绍一下 Python"},
    ]
)
```

**注意事项**：
- 每次对话都应该存储（user 和 assistant 消息）
- **v0.2.0**: 自动记忆提取需要配置 `llm` 参数（`auto_extract=True` 默认开启）
- 可以通过 `session_id` 组织多轮对话
- 更多对话管理 API 见 [对话管理（完整 API）](#对话管理完整-api)

---

### add_memory() - 直接添加记忆

直接添加结构化记忆，无需 LLM 提取。适用于手动导入、批量初始化等场景。

```python
memory_id = await nm.add_memory(
    user_id: str,
    content: str,
    memory_type: str = "general",
    metadata: dict | None = None,
) -> str
```

**参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `user_id` | `str` | - | 用户 ID |
| `content` | `str` | - | 记忆内容 |
| `memory_type` | `str` | `"general"` | 记忆类型：`fact`, `episodic`, `insight`, `general` |
| `metadata` | `dict` | `None` | 元数据，支持 `importance`, `emotion`, `tags` 等 |

**示例**：

```python
# 添加事实记忆
await nm.add_memory(
    user_id="alice",
    content="在 Google 工作",
    memory_type="fact",
    metadata={"importance": 8, "source": "user_profile"}
)

# 添加情景记忆（带情感标注）
await nm.add_memory(
    user_id="alice",
    content="昨天面试很紧张",
    memory_type="episodic",
    metadata={
        "importance": 7,
        "emotion": {
            "valence": -0.6,   # 情感效价 (-1~1)
            "arousal": 0.8,    # 情感唤醒 (0~1)
            "label": "焦虑"
        }
    }
)
```

---

### ✏️ add_message() vs add_memory() 对比

| 特性 | add_message() (v0.2.0) | add_memory() |
|------|--------------|-------------|
| **写入目标** | 对话历史表 + 记忆表 | 记忆表（embedding） |
| **记忆生成** | **自动提取**（默认 `auto_extract=True`） | 直接写入，立即可检索 |
| **情感标注** | ✅ LLM 自动标注 | ❌ 需手动指定 |
| **重要性评分** | ✅ LLM 自动评估 | ❌ 需手动指定 |
| **记忆分类** | ✅ LLM 自动分类（fact/episode/relation） | ❌ 需手动指定 memory_type |
| **图关系** | ✅ 自动提取关系到知识图谱 | ❌ 不涉及图数据库 |
| **LLM 依赖** | ✅ 需要 LLM（自动提取） | 不需要 LLM |
| **推荐场景** | 日常对话（推荐） | 手动导入、批量初始化、已知结构化数据 |

**何时使用 add_message()**：
- ✅ 构建对话 Agent（推荐）
- ✅ 希望自动提取记忆、情感、关系
- ✅ 日常对话场景

**何时使用 add_memory()**：
- 批量导入已有数据（如从其他系统迁移）
- 手动添加已知信息（如用户资料）
- 不想依赖 LLM 提取

---

## 检索 API 对比

这两个 API 都用于检索记忆，但检索策略不同。**日常使用推荐 recall()**。

### recall() - 混合检索

**RRF 混合检索（向量 + BM25）+ 图融合排序**，综合召回相关记忆（推荐使用）。评分公式为 `rrf_score × recency × importance × graph_boost`，其中 rrf_score 通过 Reciprocal Rank Fusion 融合向量相似度和 BM25 关键词匹配，graph_boost 通过图三元组覆盖度提升命中记忆的排名。图三元组本身也参与 `merged` 统一排序。

```python
result = await nm.recall(
    user_id: str,
    query: str,
    limit: int = 20,
    decay_rate: float | None = None,
    include_conversations: bool = False,
) -> dict
```

**参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `user_id` | `str` | - | 用户 ID |
| `query` | `str` | - | 查询文本 |
| `limit` | `int` | `20` | 返回结果数量 |
| `decay_rate` | `float` | `86400*30` | 时间衰减率（秒），30 天 |
| `include_conversations` | `bool` | `False` | 是否将原始对话片段合并进 `merged[]`（默认关闭，节省 token） |

**返回格式**：

```python
{
    # 提取的记忆（fact / episodic / insight），按三因子评分排序
    "vector_results": [
        {
            "id": "uuid",
            "content": "在 Google 工作"  # fact: 无日期前缀；episodic: "2025-03-01: 去了北京. sentiment: excited",
            "memory_type": "fact",              # fact / episodic / insight / general
            "metadata": {
                "importance": 8,               # 重要性评分 (1-10)
                "emotion": {
                    "valence": 0.6,            # 情感效价 (-1~1)
                    "arousal": 0.4,            # 情感唤醒 (0~1)
                    "label": "满足"
                }
            },
            "extracted_timestamp": "2025-03-01T10:00:00",  # 事件发生时间
            "score": 0.646,                    # 综合评分（relevance × recency × importance）
        },
        ...
    ],
    # 原始对话片段，保留了日期、细节，补充 vector_results 遗失的信息
    "conversation_results": [
        {
            "id": "uuid",
            "content": "我在 Google 工作，做后端开发",
            "role": "user",
            "session_id": "...",
            "created_at": "2025-03-01T10:00:00",
            "similarity": 0.91,
        },
        ...
    ],
    # 图谱三元组，结构化事实
    "graph_results": [
        {
            "subject": "alice",
            "relation": "WORKS_AT",
            "object": "google",
            "content": "在 Google 工作",
        },
        ...
    ],
    # 图谱三元组的文本化列表，可直接注入 prompt
    "graph_context": [
        "alice → WORKS_AT → google",
        "alice → HAS_SKILL → python",
    ],
    # 用户画像（从 KV profile 读取）
    "user_profile": {
        "occupation": "后端工程师",
        "interests": ["Python", "分布式系统"],
        "identity": "Alice, 28岁",
    },
    # vector_results + graph_results + conversation_results 去重合并，按 score 降序排列
    "merged": [
        {"content": "...", "source": "vector", "score": 0.646, "graph_boost": 1.5, ...},
        {"content": "张三 → WORKS_AT → google", "source": "graph", "score": 0.98, "memory_type": "graph_fact"},
        {"content": "...", "source": "conversation", "similarity": 0.91, ...},
    ]
}
```

**评分公式**：

```python
score = rrf_score × recency × importance × graph_boost

# RRF 评分 (0-1)：融合向量相似度和 BM25 关键词匹配
# rrf_score = 1/(k+rank_vector) + 1/(k+rank_bm25)，k=60
rrf_score = reciprocal_rank_fusion(vector_similarity, bm25_score)

# 时效性 (0-1)：指数衰减，情感唤醒减缓遗忘
recency = e^(-t / (decay_rate × (1 + arousal × 0.5)))

# 重要性 (0.1-1.0)：metadata.importance / 10，默认 0.5
importance = metadata.get("importance", 5) / 10

# 图 Boost (1.0-2.0)：基于图三元组覆盖度
# 双端命中（subject+object 都在记忆中）: +0.5
# 单端命中（subject 或 object 在记忆中）: +0.2
# 上限 2.0，无图匹配时为 1.0（不影响原始分数）
graph_boost = min(1.0 + coverage_boost, 2.0)
```

### 三因子检索 vs 纯向量检索

| 对比维度 | 纯向量检索 | 三因子检索 |
|---------|-----------|-----------|
| **时间感知** | ❌ 1 年前和昨天的权重相同 | ✅ 指数衰减（Ebbinghaus 遗忘曲线） |
| **情感影响** | ❌ 不考虑情感强度 | ✅ 高 arousal 记忆衰减慢 50% |
| **重要性** | ❌ 琐事和大事同等对待 | ✅ 重要事件优先级更高 |

**实际案例** — 用户问"我在哪工作？"：

| 记忆内容 | 时间 | 纯向量 | 三因子 | 应该返回 |
|---------|------|--------|--------|---------|
| "我在 Google 工作" | 1 年前 | 0.95 | 0.008 | ❌ 已过时 |
| "上周从 Google 离职了" | 7 天前 | 0.85 | 0.67 | ✅ 最新且重要 |

**示例**：

```python
# 召回相关记忆
result = await nm.recall(user_id="alice", query="我在哪工作？", limit=5)

# 使用综合结果（推荐）
for mem in result["merged"]:
    print(f"[{mem['source']}] {mem['content']}")

# 或分别查看
print(f"向量检索: {len(result['vector_results'])} 条")
print(f"图检索: {len(result['graph_results'])} 条")
```

---

### search() - 混合检索（向量 + BM25）

混合检索，通过 Reciprocal Rank Fusion 融合向量相似度和 BM25 关键词匹配（不考虑时间和重要性）。

```python
results = await nm.search(
    user_id: str,
    query: str,
    limit: int = 5,
    memory_type: str | None = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    event_after: datetime | None = None,
    event_before: datetime | None = None,
) -> list[dict]
```

**参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `user_id` | `str` | - | 用户 ID |
| `query` | `str` | - | 查询文本 |
| `limit` | `int` | `5` | 返回结果数量 |
| `memory_type` | `str` | `None` | 过滤记忆类型 |
| `created_after` | `datetime` | `None` | 只返回该时间之后创建的记忆 |
| `created_before` | `datetime` | `None` | 只返回该时间之前创建的记忆 |
| `event_after` | `datetime` | `None` | 只返回事件时间在该时间之后的记忆 |
| `event_before` | `datetime` | `None` | 只返回事件时间在该时间之前的记忆 |

**返回格式**：

```python
[
    {
        "id": "uuid",
        "content": "...",
        "memory_type": "fact",
        "metadata": {...},
        "created_at": "2024-01-01T00:00:00",
        "vector_score": 0.88,  # 向量相似度分数
        "bm25_score": 12.5,    # BM25 关键词匹配分数
        "rrf_score": 0.032,    # RRF 融合分数
    },
    ...
]
```

**示例**：

```python
# 检索所有类型
results = await nm.search(user_id="alice", query="工作", limit=10)

# 只检索洞察
insights = await nm.search(
    user_id="alice",
    query="行为模式",
    memory_type="insight",
    limit=5
)
```

---

### 🔍 recall() vs search() 对比

| 特性 | recall() | search() |
|------|----------|----------|
| **检索方式** | RRF 混合检索 + 图检索 | RRF 混合检索（向量 + BM25） |
| **评分因素** | rrf_score × 时效性 × 重要性 × 图boost | 仅 rrf_score |
| **结果来源** | vector_results + graph_results + merged（统一排序） | 单一列表 |
| **时间衰减** | ✅ 支持（近期记忆优先） | ❌ 不考虑时间 |
| **重要性** | ✅ 支持（重要记忆优先） | ❌ 不考虑重要性 |
| **图实体** | ✅ 包含知识图谱关系 | ❌ 无图检索 |
| **推荐场景** | 日常使用，构建对话 Agent | 纯语义搜索，特定类型筛选 |

**何时使用 recall()**：
- ✅ 构建对话 Agent（推荐）
- ✅ 需要最相关的**最近**记忆
- ✅ 考虑记忆重要性
- ✅ 需要知识图谱关系

**何时使用 search()**：
- 只需要语义相似度，不考虑时间
- 特定类型筛选（`memory_type="insight"`）
- 调试或分析记忆分布

---

## 记忆管理 API 对比

推荐使用 `reflect()` 进行记忆处理。`extract_memories()` 是底层方法，由 `add_message()` 的 `auto_extract` 机制自动调用。

### reflect() - 记忆整理 ⭐ 推荐

**v0.2.0 更新**：专注于洞察生成和情感画像，基础记忆提取已由 `add_message()` 自动完成。

```python
result = await nm.reflect(
    user_id: str,
    limit: int = 50,
) -> dict
```

**参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `user_id` | `str` | - | 用户 ID |
| `limit` | `int` | `50` | 分析的近期记忆数量 |

**返回格式**：

```python
{
    "conversations_processed": 0,     # v0.2.0: 基础提取已由 add_message 完成
    "facts_added": 0,                # v0.2.0: 不再重复提取
    "preferences_updated": 0,         # v0.2.0: 偏好存入 profile
    "relations_added": 0,             # v0.2.0: 不再重复提取
    "insights_generated": 2,          # 生成洞察数
    "insights": [                     # 洞察内容
        {"content": "用户是技术从业者，关注后端开发", "category": "pattern"},
        {"content": "用户近期工作压力大，寻求减压方式", "category": "summary"},
    ],
    "emotion_profile": {              # 情感画像
        "latest_state": "近期偏焦虑",
        "valence_avg": -0.3,
        ...
    },
}
```

**工作流程（v0.2.0）**：

1. **提炼洞察**：分析近期记忆（已由 `add_message()` 提取），生成高层理解
   - 行为模式（pattern）："用户倾向于晚上工作"
   - 阶段总结（summary）："用户近期在准备跳槽"
2. **更新画像**：整合情感数据，更新用户情感画像

**示例（v0.2.0）**：

```python
# 日常使用：add_message 自动提取 + 定期 reflect 生成洞察
await nm.conversations.add_message(user_id="alice", role="user", content="我在 Google 工作")
# → 自动提取: fact: "在 Google 工作"

# 定期调用 reflect（如每天、每周）
result = await nm.reflect(user_id="alice")

print(f"生成了 {result['insights_generated']} 条洞察")

for insight in result["insights"]:
    print(f"[{insight['category']}] {insight['content']}")

# 也可以通过 search 查找洞察
insights = await nm.search(user_id="alice", query="行为模式", memory_type="insight")
```

---

### extract_memories() - 提取记忆（内部方法）

**v0.2.0 更新**：此方法主要由 `add_message()` 内部调用（当 `auto_extract=True` 时），通常不需要直接使用。

```python
stats = await nm.extract_memories(
    user_id: str,
    messages: list,
) -> dict
```

**提取内容**：事实 / 情景 / 关系 / 情感标注 / 重要性评分 / 用户画像（含偏好）

**何时直接使用**：
- 批量处理历史对话（关闭 `auto_extract`，手动批量提取）
- 自定义提取逻辑

---

### reflect() vs extract_memories() 对比（v0.2.0）

| 特性 | reflect() ⭐ | extract_memories() |
|------|-------------|-------------------|
| **主要功能** | 洞察生成 + 画像更新 | 提取基础记忆 |
| **处理对象** | 已有记忆 | 对话消息 |
| **生成洞察** | ✅ 行为模式、阶段总结 | ❌ |
| **更新画像** | ✅ 情感画像 | ❌ |
| **提取事实** | ❌ 不再重复提取 | ✅ 提取事实/情景/关系 |
| **LLM 调用** | 1-2 次（洞察生成） | 1 次 |
| **推荐场景** | 定期调用（每天/周） | 内部自动调用（`add_message`） |

**典型使用模式（v0.2.0）**：
```python
# 推荐：使用 auto_extract（默认）
nm = NeuroMemory(
    database_url="...",
    embedding=SiliconFlowEmbedding(api_key="..."),
    llm=OpenAILLM(api_key="..."),
    auto_extract=True,  # 默认，每次 add_message 自动提取
)

# 对话时自动提取
await nm.conversations.add_message(user_id, "user", content)
# → 自动调用 extract_memories()

# 定期生成洞察
await nm.reflect(user_id)  # 分析记忆，生成洞察
```

---

## KV 存储

键值存储，用于用户偏好、配置等结构化数据。

### nm.kv.set()

```python
await nm.kv.set(
    user_id: str,
    namespace: str,
    key: str,
    value: Any,
) -> None
```

**参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `user_id` | `str` | 用户 ID |
| `namespace` | `str` | 命名空间（如 `"profile"`, `"config"`） |
| `key` | `str` | 键名 |
| `value` | `Any` | 值（支持 str, int, float, bool, dict, list, None） |

**示例**：

```python
# 存储用户配置
await nm.kv.set("alice", "config", "language", "zh-CN")
await nm.kv.set("alice", "config", "theme", {"mode": "dark", "color": "blue"})
await nm.kv.set("alice", "config", "model", "gpt-4")

# 注：用户偏好由 LLM 自动提取，存入 profile namespace
# await nm.kv.get("alice", "profile", "preferences")  # → ["喜欢喝咖啡", ...]
```

### nm.kv.get()

```python
value = await nm.kv.get(
    user_id: str,
    namespace: str,
    key: str,
) -> Any | None
```

**返回**：值，不存在时返回 `None`。

**示例**：

```python
lang = await nm.kv.get("alice", "config", "language")
print(lang)  # "zh-CN"

theme = await nm.kv.get("alice", "config", "theme")
print(theme)  # {"mode": "dark", "color": "blue"}
```

### nm.kv.list()

```python
items = await nm.kv.list(
    user_id: str,
    namespace: str,
    prefix: str = "",
) -> list[dict]
```

**返回**：

```python
[
    {"key": "language", "value": "zh-CN"},
    {"key": "theme", "value": {...}},
]
```

### nm.kv.delete()

```python
await nm.kv.delete(
    user_id: str,
    namespace: str,
    key: str,
) -> bool
```

**返回**：删除成功返回 `True`，键不存在返回 `False`。

### nm.kv.batch_set()

```python
await nm.kv.batch_set(
    user_id: str,
    namespace: str,
    items: dict[str, Any],
) -> None
```

**示例**：

```python
await nm.kv.batch_set("alice", "config", {
    "language": "zh-CN",
    "timezone": "Asia/Shanghai",
    "theme": {"mode": "dark"},
})
```

---

## 对话管理

### nm.conversations.add_message()

```python
message = await nm.conversations.add_message(
    user_id: str,
    role: str,
    content: str,
    session_id: str | None = None,
    metadata: dict | None = None,
) -> ConversationMessage
```

**参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `user_id` | `str` | - | 用户 ID |
| `role` | `str` | - | 角色：`"user"` 或 `"assistant"` |
| `content` | `str` | - | 消息内容 |
| `session_id` | `str` | `None` | 会话 ID，为 None 时自动创建新会话 |
| `metadata` | `dict` | `None` | 元数据 |

**示例**：

```python
# 添加用户消息
await nm.conversations.add_message(
    user_id="alice",
    role="user",
    content="我在 Google 工作"
)

# 添加 assistant 回复
await nm.conversations.add_message(
    user_id="alice",
    role="assistant",
    content="了解！"
)
```

### nm.conversations.add_messages_batch()

```python
session_id, message_ids = await nm.conversations.add_messages_batch(
    user_id: str,
    messages: list[dict],
    session_id: str | None = None,
) -> tuple[str, list[str]]
```

**参数**：

```python
messages = [
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hi!"},
]
```

**返回**：`(session_id, [msg_id1, msg_id2, ...])`

### nm.conversations.get_session_messages()

```python
messages = await nm.conversations.get_session_messages(
    user_id: str,
    session_id: str,
    limit: int = 100,
    offset: int = 0,
) -> list[ConversationMessage]
```

**返回**：消息列表。

### nm.conversations.get_unextracted_messages()

```python
messages = await nm.conversations.get_unextracted_messages(
    user_id: str,
    session_id: str | None = None,
    limit: int = 100,
) -> list[ConversationMessage]
```

**获取尚未提取记忆的消息**，用于传入 `extract_memories()`。

### nm.conversations.close_session()

```python
await nm.conversations.close_session(
    user_id: str,
    session_id: str,
) -> None
```

**关闭会话**。

### nm.conversations.list_sessions()

```python
sessions = await nm.conversations.list_sessions(
    user_id: str,
    limit: int = 10,
) -> list[ConversationSession]
```

**返回**：会话列表，每个会话包含 `session_id`, `message_count`, `created_at`, `updated_at`。

---

## 文件管理

需要配置 `storage` 参数（S3Storage）。

### nm.files.upload()

```python
document = await nm.files.upload(
    user_id: str,
    filename: str,
    file_data: bytes,
    category: str = "general",
    tags: list[str] | None = None,
    metadata: dict | None = None,
) -> Document
```

**参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `user_id` | `str` | - | 用户 ID |
| `filename` | `str` | - | 文件名 |
| `file_data` | `bytes` | - | 文件二进制数据 |
| `category` | `str` | `"general"` | 分类标签 |
| `tags` | `list[str]` | `None` | 标签列表 |
| `metadata` | `dict` | `None` | 元数据 |

**支持格式**：

- 文本：`.txt`, `.md`, `.json`, `.csv`
- PDF：`.pdf`（需要 `pip install neuromemory[pdf]`）
- Word：`.docx`（需要 `pip install neuromemory[docx]`）
- 图片：`.jpg`, `.png`, `.gif`（仅存储，不提取文本）

**示例**：

```python
# 上传 PDF
with open("report.pdf", "rb") as f:
    doc = await nm.files.upload(
        user_id="alice",
        filename="report.pdf",
        file_data=f.read(),
        category="work",
        auto_extract=True,
    )

print(f"文档 ID: {doc.id}")
print(f"提取文本: {doc.extracted_text[:100]}...")
```

### nm.files.create_from_text()

```python
document = await nm.files.create_from_text(
    user_id: str,
    title: str,
    content: str,
    category: str = "general",
    tags: list[str] | None = None,
    metadata: dict | None = None,
) -> Document
```

**直接从文本创建文档**（不上传到 S3）。

### nm.files.list()

```python
docs = await nm.files.list(
    user_id: str,
    category: str | None = None,
    tags: list[str] | None = None,
    file_types: list[str] | None = None,
    limit: int = 50,
) -> list[Document]
```

### nm.files.get()

```python
doc = await nm.files.get(
    user_id: str,
    file_id: str,
) -> Document | None
```

### nm.files.delete()

```python
success = await nm.files.delete(
    user_id: str,
    file_id: str,
) -> bool
```

### nm.files.search()

```python
results = await nm.files.search(
    user_id: str,
    query: str,
    limit: int = 5,
    file_types: list[str] | None = None,
    category: str | None = None,
    tags: list[str] | None = None,
) -> list[dict]
```

**向量检索文件内容**。

**示例**：

```python
# 检索所有文件
results = await nm.files.search(user_id="alice", query="项目报告")

# 只检索 PDF
pdfs = await nm.files.search(
    user_id="alice",
    query="技术文档",
    file_types=["pdf"]
)
```

---

## 图数据库

图数据库（基于 PostgreSQL 关系表）。

### nm.graph.create_node()

```python
node_id = await nm.graph.create_node(
    node_type: NodeType,
    node_id: str,
    properties: dict | None = None,
    user_id: str | None = None,
) -> str
```

**NodeType 枚举**：

```python
from neuromemory.models.graph import NodeType

NodeType.USER         # 用户
NodeType.ENTITY       # 通用实体
NodeType.ORGANIZATION # 组织/公司
NodeType.LOCATION     # 地点
NodeType.SKILL        # 技能
```

**示例**：

```python
from neuromemory.models.graph import NodeType, EdgeType

# 创建用户节点
await nm.graph.create_node(NodeType.USER, "alice", {"name": "Alice"})

# 创建实体节点
await nm.graph.create_node(NodeType.ENTITY, "google", {"name": "Google"})
```

### nm.graph.create_edge()

```python
await nm.graph.create_edge(
    source_type: NodeType,
    source_id: str,
    edge_type: EdgeType,
    target_type: NodeType,
    target_id: str,
    properties: dict | None = None,
    user_id: str | None = None,
) -> None
```

**EdgeType 枚举**：

```python
# Fact 关系
EdgeType.WORKS_AT     # 工作于
EdgeType.LIVES_IN     # 居住于
EdgeType.HAS_SKILL    # 拥有技能
EdgeType.STUDIED_AT   # 就读于
EdgeType.KNOWS        # 认识
EdgeType.USES         # 使用
EdgeType.HOBBY        # 爱好
EdgeType.OWNS         # 拥有
EdgeType.SPEAKS       # 会说语言
EdgeType.BORN_IN      # 出生于
EdgeType.LOCATED_IN   # 位于
# Episode 关系
EdgeType.MET          # 见面
EdgeType.ATTENDED     # 参加活动
EdgeType.VISITED      # 访问地点
EdgeType.OCCURRED_AT  # 发生地点
# 通用
EdgeType.RELATED_TO   # 相关
EdgeType.MENTIONS     # 提及
EdgeType.CUSTOM       # 自定义关系（properties["relation_name"] 存储原始名称）
```

**示例**：

```python
# 创建关系
await nm.graph.create_edge(
    NodeType.USER, "alice",
    EdgeType.WORKS_AT,
    NodeType.ENTITY, "google",
    properties={"since": "2023-01-01"}
)
```

### nm.graph.get_node()

```python
node = await nm.graph.get_node(
    user_id: str,
    node_type: NodeType,
    node_id: str,
) -> dict | None
```

### nm.graph.get_neighbors()

```python
neighbors = await nm.graph.get_neighbors(
    user_id: str,
    node_type: NodeType,
    node_id: str,
    edge_types: list[EdgeType] | None = None,
    direction: str = "both",
    limit: int = 10,
) -> list[dict]
```

**返回**：

```python
[
    {
        "node_type": "ENTITY",
        "node_id": "google",
        "properties": {"name": "Google"},
        "edge_type": "WORKS_AT",
        "edge_properties": {"since": "2023-01-01"}
    },
    ...
]
```

### nm.graph.find_path()

```python
paths = await nm.graph.find_path(
    start_type: NodeType,
    start_id: str,
    end_type: NodeType,
    end_id: str,
    max_depth: int = 3,
) -> list[list[dict]]
```

**查找两个节点之间的路径**。

### nm.graph.update_node()

```python
await nm.graph.update_node(
    node_type: NodeType,
    node_id: str,
    properties: dict,
) -> None
```

### nm.graph.delete_node()

```python
await nm.graph.delete_node(
    node_type: NodeType,
    node_id: str,
) -> None
```

---

## Provider 接口

### EmbeddingProvider

自定义 Embedding 提供者。

```python
from neuromemory.providers.embedding import EmbeddingProvider

class CustomEmbedding(EmbeddingProvider):
    @property
    def dims(self) -> int:
        """返回向量维度"""
        return 1024

    async def embed(self, text: str) -> list[float]:
        """生成单个文本的 embedding"""
        # 调用你的 embedding API
        return [0.1, 0.2, ...]  # 1024 维向量

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量生成 embedding"""
        return [await self.embed(t) for t in texts]
```

**内置实现**：

- `SiliconFlowEmbedding`：BAAI/bge-m3 (1024 维)
- `OpenAIEmbedding`：text-embedding-3-small (1536 维)

### LLMProvider

自定义 LLM 提供者。

```python
from neuromemory.providers.llm import LLMProvider

class CustomLLM(LLMProvider):
    async def chat(self, messages: list[dict], **kwargs) -> str:
        """对话生成，messages 格式同 OpenAI: [{"role": "user", "content": "..."}]"""
        # 调用你的 LLM API
        return "generated text"
```

**内置实现**：

- `OpenAILLM`：兼容 OpenAI API（支持 DeepSeek、Moonshot 等）

### ObjectStorage

自定义对象存储。

```python
from neuromemory.storage.base import ObjectStorage

class CustomStorage(ObjectStorage):
    async def upload(self, key: str, data: bytes) -> str:
        """上传文件，返回 URL"""
        pass

    async def download(self, key: str) -> bytes:
        """下载文件"""
        pass

    async def delete(self, key: str) -> bool:
        """删除文件"""
        pass

    async def exists(self, key: str) -> bool:
        """检查文件是否存在"""
        pass
```

**内置实现**：

- `S3Storage`：兼容 S3 协议（MinIO / AWS S3 / 华为云 OBS）

---

## 完整示例

```python
import asyncio
from neuromemory import NeuroMemory, SiliconFlowEmbedding, OpenAILLM

async def main():
    async with NeuroMemory(
        database_url="postgresql+asyncpg://neuromemory:neuromemory@localhost:5432/neuromemory",
        embedding=SiliconFlowEmbedding(api_key="sk-xxx"),
        llm=OpenAILLM(api_key="sk-xxx", model="deepseek-chat"),
    ) as nm:
        user_id = "alice"

        # 1. 存储对话（自动提取记忆）
        await nm.conversations.add_message(
            user_id=user_id,
            role="user",
            content="我在 Google 工作，做后端开发，最近压力有点大"
        )
        # → 自动提取: fact "在 Google 工作", episodic "最近压力有点大"

        # 2. 召回记忆
        result = await nm.recall(user_id=user_id, query="工作情况", limit=5)
        for mem in result["merged"]:
            print(f"[{mem['source']}] {mem['content']}")

        # 3. 查询用户画像（自动提取后存入 profile）
        prefs = await nm.kv.get(user_id, "profile", "interests")

        # 4. 定期生成洞察（默认 reflection_interval=20 自动触发，也可手动调用）
        await nm.reflect(user_id=user_id)

asyncio.run(main())
```

---

## 错误处理

```python
from sqlalchemy.exc import IntegrityError

try:
    await nm.add_memory(user_id="alice", content="...")
except IntegrityError:
    print("记忆已存在或违反约束")
except Exception as e:
    print(f"错误: {e}")
```

---

## 性能优化

### 批量操作

```python
# 批量添加对话
await nm.conversations.add_messages_batch(user_id, messages)

# 批量设置 KV
await nm.kv.batch_set(user_id, namespace, items)

# 批量 embedding
texts = ["text1", "text2", ...]
vectors = await embedding.embed_batch(texts)
```

### 连接池配置

```python
nm = NeuroMemory(
    database_url="...",
    embedding=...,
    pool_size=20,  # 增加连接池大小
)
```

---

## 数据生命周期 API

### delete_user_data() - 删除用户数据

**单事务原子删除**用户的所有数据（embeddings, conversations, graph, KV, emotion profiles, documents）。

```python
result = await nm.delete_user_data(user_id: str) -> dict
```

**返回格式**：

```python
{
    "deleted": {
        "embeddings": 15,
        "graph_edges": 3,
        "graph_nodes": 5,
        "conversations": 42,
        "conversation_sessions": 2,
        "key_values": 8,
        "emotion_profiles": 1,
        "documents": 0,
    }
}
```

**示例**：

```python
# 删除用户所有数据（GDPR 合规）
result = await nm.delete_user_data(user_id="alice")
print(f"删除了 {result['deleted']['embeddings']} 条记忆")

# 删除不存在的用户不会报错
result = await nm.delete_user_data(user_id="nonexistent")
# → {"deleted": {"embeddings": 0, ...}}
```

---

### export_user_data() - 导出用户数据

导出用户的**全部数据**为结构化字典。

```python
result = await nm.export_user_data(user_id: str) -> dict
```

**返回格式**：

```python
{
    "memories": [
        {"id": "uuid", "content": "...", "memory_type": "fact", "metadata": {...}, ...},
    ],
    "conversations": [
        {"id": "uuid", "role": "user", "content": "...", "session_id": "...", ...},
    ],
    "graph": {
        "nodes": [{"node_type": "Person", "node_id": "alice", "properties": {...}}],
        "edges": [{"source_id": "alice", "edge_type": "WORKS_AT", "target_id": "google", ...}],
    },
    "kv": [
        {"namespace": "profile", "key": "lang", "value": "en", ...},
    ],
    "profile": {...} or None,
    "documents": [...],
}
```

**示例**：

```python
# 导出用户数据（数据可移植性）
data = await nm.export_user_data(user_id="alice")
print(f"共 {len(data['memories'])} 条记忆, {len(data['conversations'])} 条对话")
```

---

## 记忆分析 API

### stats() - 记忆统计

获取用户的记忆统计信息。

```python
result = await nm.stats(user_id: str) -> dict
```

**返回格式**：

```python
{
    "total": 42,
    "by_type": {"fact": 20, "episodic": 15, "insight": 7},
    "by_week": [{"week": "2025-W01", "count": 5}, ...],
    "active_entities": 12,
    "profile_summary": {
        "dominant_emotions": [...],
        "latest_state": "...",
        "last_reflected_at": "2025-03-01T10:00:00",
    } or None,
}
```

**示例**：

```python
stats = await nm.stats(user_id="alice")
print(f"总记忆: {stats['total']}, 实体: {stats['active_entities']}")
for mtype, count in stats["by_type"].items():
    print(f"  {mtype}: {count}")
```

---

### cold_memories() - 冷记忆查询

查找长期未被访问的记忆，用于记忆归档或清理。

```python
result = await nm.cold_memories(
    user_id: str,
    threshold_days: int = 90,
    limit: int = 50,
) -> list[dict]
```

**参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `user_id` | `str` | - | 用户 ID |
| `threshold_days` | `int` | `90` | 超过此天数未访问视为冷记忆 |
| `limit` | `int` | `50` | 最大返回数量 |

**返回格式**：

```python
[
    {
        "id": "uuid",
        "content": "很久以前的记忆",
        "memory_type": "fact",
        "access_count": 0,
        "last_accessed_at": None,
        "created_at": "2024-01-01T00:00:00",
    },
    ...
]
```

**示例**：

```python
# 查找 90 天未访问的记忆
cold = await nm.cold_memories(user_id="alice", threshold_days=90)
print(f"发现 {len(cold)} 条冷记忆")
for mem in cold:
    print(f"  [{mem['memory_type']}] {mem['content'][:50]}...")
```

---

### entity_profile() - 实体全景

跨类型查询某个实体的全部信息：记忆提及、图谱关系、对话记录、时间线。

```python
result = await nm.entity_profile(
    user_id: str,
    entity: str,
) -> dict
```

**参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `user_id` | `str` | 用户 ID |
| `entity` | `str` | 实体名称（如 "Google", "Alice"） |

**返回格式**：

```python
{
    "entity": "Google",
    "facts": [
        {"id": "uuid", "content": "Alice works at Google", "memory_type": "fact", ...},
    ],
    "graph_relations": [
        {"subject": "alice", "relation": "WORKS_AT", "object": "google", ...},
    ],
    "conversations": [
        {"id": "uuid", "role": "user", "content": "I work at Google", ...},
    ],
    "timeline": [
        {"type": "memory", "content": "...", "time": "2025-01-01T00:00:00"},
        {"type": "conversation", "content": "...", "time": "2025-03-01T10:00:00"},
    ],
}
```

**示例**：

```python
# 查看关于 Google 的所有信息
profile = await nm.entity_profile(user_id="alice", entity="Google")
print(f"事实: {len(profile['facts'])}, 关系: {len(profile['graph_relations'])}")
for rel in profile["graph_relations"]:
    print(f"  {rel['subject']} → {rel['relation']} → {rel['object']}")
```

---

## 学术基础

- **Generative Agents** (Stanford, 2023)：三因子检索、反思机制
- **ACT-R 认知架构**：访问追踪、基础激活
- **LeDoux 情感记忆理论** (1996)：情感标注
- **Russell Circumplex Model**：valence-arousal 模型
- **Ebbinghaus 遗忘曲线**：时间衰减

---

**更多示例**: [GETTING_STARTED.md](GETTING_STARTED.md)
**架构文档**: [ARCHITECTURE.md](ARCHITECTURE.md)
