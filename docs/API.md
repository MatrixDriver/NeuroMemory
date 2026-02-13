# NeuroMemory API 参考文档

> **版本**: 0.1.0
> **Python**: 3.12+
> **最后更新**: 2026-02-13

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
    extraction: ExtractionStrategy | None = None,
    graph_enabled: bool = False,
    pool_size: int = 10,
    echo: bool = False,
)
```

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `database_url` | `str` | ✅ | PostgreSQL 连接字符串，格式：`postgresql+asyncpg://user:pass@host:port/db` |
| `embedding` | `EmbeddingProvider` | ✅ | Embedding 提供者（SiliconFlowEmbedding / OpenAIEmbedding） |
| `llm` | `LLMProvider` | ❌ | LLM 提供者，用于 `extract_memories()` 和 `reflect()` |
| `storage` | `ObjectStorage` | ❌ | 对象存储，用于文件管理（S3Storage） |
| `extraction` | `ExtractionStrategy` | ❌ | 自动记忆提取策略 |
| `graph_enabled` | `bool` | ❌ | 是否启用图数据库（Apache AGE），默认 `False` |
| `pool_size` | `int` | ❌ | 数据库连接池大小，默认 10 |
| `echo` | `bool` | ❌ | 是否输出 SQL 日志，默认 `False`（调试用） |

**示例**：

```python
async with NeuroMemory(
    database_url="postgresql+asyncpg://neuromemory:neuromemory@localhost:5432/neuromemory",
    embedding=SiliconFlowEmbedding(api_key="sk-xxx"),
    llm=OpenAILLM(api_key="sk-xxx", model="deepseek-chat"),
) as nm:
    # 使用 nm...
    pass
```

---

## 易混淆 API 说明

NeuroMemory 有三组容易混淆的 API，请先理解它们的区别：

### ✏️ 写入 API：add_message() vs add_memory()

| API | 用途 | 写入目标 | 何时使用 |
|-----|------|---------|---------|
| **add_message()** ⭐ | 存储对话消息 | 对话历史表 → 后续通过 `extract_memories()` 提取记忆 | **日常使用（推荐）**：对话驱动，记忆自动提取 |
| **add_memory()** | 直接写入记忆 | 记忆表（embedding） | **特定场景**：手动导入、批量初始化、已知结构化信息 |

**示例对比**：
```python
# add_message(): 对话驱动（推荐）
# 先存对话，再获取未提取消息，然后 LLM 提取记忆
await nm.conversations.add_message(user_id="alice", role="user",
    content="我在 Google 工作，做后端开发")
messages = await nm.conversations.get_unextracted_messages(user_id="alice")
await nm.extract_memories(user_id="alice", messages=messages)
# → 自动提取: fact: "在 Google 工作", fact: "做后端开发"
# → 自动标注: importance=8, emotion={valence: 0.3, arousal: 0.2}

# add_memory(): 直接写入（手动指定一切）
await nm.add_memory(user_id="alice", content="在 Google 工作",
    memory_type="fact", metadata={"importance": 8})
# → 直接存入记忆库，不经过对话和 LLM 提取
```

**核心区别**：
- `add_message()`: **对话驱动** - 存对话 → LLM 自动提取记忆（含情感、重要性）
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

### 🧠 记忆管理 API：extract_memories() vs reflect()

| API | 用途 | 处理内容 | 何时使用 |
|-----|------|---------|---------|
| **extract_memories()** | 提取新记忆 | 从对话中提取事实/偏好/关系，添加到记忆库 | **每次对话后**：提取用户刚说的新信息 |
| **reflect()** | 整理已有记忆 | 重新提取未处理对话 + 生成洞察 + 更新情感画像 | **定期整理**（每天/每周）：生成高层次理解 |

**示例对比**：
```python
# extract_memories(): 获取未提取消息，然后提取记忆
await nm.conversations.add_message(user_id="alice", role="user", content="我在 Google 工作")
messages = await nm.conversations.get_unextracted_messages(user_id="alice")
await nm.extract_memories(user_id="alice", messages=messages)
# → 提取: fact: "在 Google 工作", relation: (alice)-[works_at]->(Google)

# reflect(): 整理所有记忆，生成洞察
await nm.reflect(user_id="alice")
# → 重新提取遗漏的对话 + 生成洞察: "用户近期求职，面试了 Google 和微软"
```

**核心区别**：
- `extract_memories()`: **增量提取** - 处理新对话，添加新记忆
- `reflect()`: **全面整理** - 查漏补缺 + 提炼洞察 + 更新画像

---

## 核心 API

## 写入 API 对比

这两个 API 都用于"写入"数据，但写入目标不同。**日常使用推荐 add_message()**。

### add_message() - 添加对话消息

**最常用的 API**，用于存储用户和 assistant 的对话消息。这是构建对话 agent 的核心操作。

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
| `metadata` | `dict` | `None` | 元数据（可选） |

**返回**：`ConversationMessage` 对象，包含 `id`, `session_id`, `role`, `content`, `created_at`

**典型使用流程**：

```python
# 1. 用户发送消息
await nm.conversations.add_message(
    user_id="alice",
    role="user",
    content="我在 Google 工作，做后端开发"
)

# 2. 召回相关记忆
result = await nm.recall(user_id="alice", query="工作", limit=5)

# 3. 基于记忆生成回复（使用你的 LLM）
reply = your_llm.generate(
    context=result["merged"],
    user_input="我在 Google 工作，做后端开发"
)

# 4. 存储 assistant 回复
await nm.conversations.add_message(
    user_id="alice",
    role="assistant",
    content=reply
)

# 5. 自动提取记忆（如果配置了 ExtractionStrategy，会在满足条件时自动触发）
# 手动触发：
# messages = await nm.conversations.get_unextracted_messages(user_id="alice")
# await nm.extract_memories(user_id="alice", messages=messages)
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
- 自动记忆提取需要配置 `llm` 和 `extraction` 参数
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
| `memory_type` | `str` | `"general"` | 记忆类型：`fact`, `episodic`, `preference`, `insight`, `general` |
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

| 特性 | add_message() | add_memory() |
|------|--------------|-------------|
| **写入目标** | 对话历史表 | 记忆表（embedding） |
| **记忆生成** | 后续通过 extract_memories() 自动提取 | 直接写入，立即可检索 |
| **情感标注** | ✅ LLM 自动标注 | ❌ 需手动指定 |
| **重要性评分** | ✅ LLM 自动评估 | ❌ 需手动指定 |
| **记忆分类** | ✅ LLM 自动分类（fact/preference/relation） | ❌ 需手动指定 memory_type |
| **图关系** | ✅ 自动提取关系到知识图谱 | ❌ 不涉及图数据库 |
| **LLM 依赖** | 提取时需要 LLM | 不需要 LLM |
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

**三因子向量检索 + 图实体检索**，综合召回相关记忆（推荐使用）。

```python
result = await nm.recall(
    user_id: str,
    query: str,
    limit: int = 10,
    decay_rate: float | None = None,
) -> dict
```

**参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `user_id` | `str` | - | 用户 ID |
| `query` | `str` | - | 查询文本 |
| `limit` | `int` | `10` | 返回结果数量 |
| `decay_rate` | `float` | `86400*30` | 时间衰减率（秒），30 天 |

**返回格式**：

```python
{
    "vector_results": [
        {
            "id": "uuid",
            "content": "我在 Google 工作",
            "memory_type": "fact",
            "metadata": {"importance": 8, "emotion": {...}},
            "created_at": "2024-01-01T00:00:00",
            "relevance": 0.95,      # 语义相似度
            "recency": 0.85,        # 时间衰减
            "importance": 0.8,      # 重要性
            "score": 0.646,         # 综合评分
        },
        ...
    ],
    "graph_results": [
        {
            "id": "uuid",
            "content": "(alice)-[works_at]->(Google)",
            ...
        },
        ...
    ],
    "merged": [
        # 去重后的综合结果，推荐使用
        {"content": "...", "source": "vector", ...},
        {"content": "...", "source": "graph", ...},
    ]
}
```

**评分公式**：

```python
score = relevance × recency × importance

# 相关性 (0-1)：余弦相似度
relevance = 1 - cosine_distance(query_vec, memory_vec)

# 时效性 (0-1)：指数衰减，情感唤醒减缓遗忘
recency = e^(-t / (decay_rate × (1 + arousal × 0.5)))

# 重要性 (0.1-1.0)：metadata.importance / 10，默认 0.5
importance = metadata.get("importance", 5) / 10
```

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

### search() - 向量检索

纯向量相似度检索（不考虑时间和重要性）。

```python
results = await nm.search(
    user_id: str,
    query: str,
    limit: int = 5,
    memory_type: str | None = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
) -> list[dict]
```

**参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `user_id` | `str` | - | 用户 ID |
| `query` | `str` | - | 查询文本 |
| `limit` | `int` | `5` | 返回结果数量 |
| `memory_type` | `str` | `None` | 过滤记忆类型 |
| `created_after` | `datetime` | `None` | 只返回该时间之后的记忆 |
| `created_before` | `datetime` | `None` | 只返回该时间之前的记忆 |

**返回格式**：

```python
[
    {
        "id": "uuid",
        "content": "...",
        "memory_type": "fact",
        "metadata": {...},
        "created_at": "2024-01-01T00:00:00",
        "distance": 0.12,  # 余弦距离，越小越相似
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
| **检索方式** | 三因子向量 + 图检索 | 纯向量检索 |
| **评分因素** | 相关性 × 时效性 × 重要性 | 仅相关性（余弦相似度） |
| **结果来源** | vector_results + graph_results + merged | 单一列表 |
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

这两个 API 都用于管理记忆，但处理逻辑不同。**日常使用 extract_memories()，定期使用 reflect()**。

### extract_memories() - 提取记忆

从对话消息中自动提取结构化记忆（需要 LLM）。

```python
stats = await nm.extract_memories(
    user_id: str,
    messages: list,
) -> dict
```

**参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `user_id` | `str` | 用户 ID |
| `messages` | `list` | 待提取的对话消息列表（通过 `get_unextracted_messages()` 获取） |

**返回格式**：

```python
{
    "messages_processed": 10,
    "facts_stored": 3,
    "preferences_stored": 2,
    "episodes_stored": 1,
    "triples_stored": 1,      # 图关系数量（需要 graph_enabled=True）
}
```

**提取内容**：

- **事实** (`fact`)：客观信息（"在 Google 工作"）
- **偏好** (`preference`)：存入 KV Store（`preferences` namespace）
- **情景** (`episodic`)：带时间的事件（"昨天面试"）
- **关系** (`relation`)：存入图数据库（需要 `graph_enabled=True`）
- **情感标注**：自动标注 valence, arousal, label
- **重要性评分**：1-10 分

**示例**：

```python
# 1. 添加对话消息
await nm.conversations.add_message(
    user_id="alice", role="user",
    content="我在 Google 工作，做后端开发"
)

# 2. 获取未提取的消息
messages = await nm.conversations.get_unextracted_messages(user_id="alice")

# 3. 提取记忆
stats = await nm.extract_memories(user_id="alice", messages=messages)
print(f"提取了 {stats['facts_stored']} 条事实")
# 自动生成：
# - fact: "在 Google 工作"
# - fact: "做后端开发"
# - relation: (alice)-[works_at]->(Google)  (需要 graph_enabled=True)
```

**注意**：配置了 `ExtractionStrategy` 后，`add_message()` 会在满足条件时（如每 10 条消息）自动调用提取，无需手动调用。

---

### reflect() - 记忆整理

全面记忆整理：重新提取 + 生成洞察 + 更新情感画像。

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
    "conversations_processed": 10,    # 补充提取的对话数
    "facts_added": 3,                # 新增事实数
    "preferences_updated": 2,         # 更新偏好数
    "relations_added": 1,             # 新增关系数
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

**工作流程**：

1. **查漏补缺**：重新提取未处理的对话（自动调用 `extract_memories()`）
2. **提炼洞察**：分析近期记忆，生成高层理解
   - 行为模式（pattern）："用户倾向于晚上工作"
   - 阶段总结（summary）："用户近期在准备跳槽"
3. **更新画像**：整合情感数据，更新用户情感画像

**示例**：

```python
# 定期整理记忆
result = await nm.reflect(user_id="alice")

print(f"处理了 {result['conversations_processed']} 条对话")
print(f"生成了 {result['insights_generated']} 条洞察")

# 查看生成的洞察
for insight in result["insights"]:
    print(f"[{insight['category']}] {insight['content']}")

# 也可以通过 search 查找洞察
insights = await nm.search(user_id="alice", query="行为模式", memory_type="insight")
```

---

### 🧠 extract_memories() vs reflect() 对比

| 特性 | extract_memories() | reflect() |
|------|-------------------|-----------|
| **主要功能** | 提取新记忆 | 全面整理记忆 |
| **处理对象** | 对话消息（未提取的） | 对话 + 已有记忆 |
| **输出内容** | 事实/偏好/关系/情景 | 提取 + 洞察 + 情感画像 |
| **调用时机** | 每次对话后 | 定期（每天/每周） |
| **是否生成洞察** | ❌ 不生成 | ✅ 生成高层次理解 |
| **是否更新画像** | ❌ 不更新 | ✅ 更新情感画像 |
| **执行速度** | 快（只处理新消息） | 慢（分析所有记忆） |
| **LLM 调用** | 1 次（提取） | 2-3 次（提取+洞察+画像） |

**何时使用 extract_memories()**：
- ✅ 每次对话后提取新信息（推荐）
- ✅ 需要快速更新记忆库
- ✅ 增量式记忆积累

**何时使用 reflect()**：
- 定期整理（每天/每周执行一次）
- 生成用户行为模式洞察
- 更新情感画像和长期理解
- 查漏补缺，重新处理遗漏的对话

**典型使用模式**：
```python
# 每次对话后（手动模式）
await nm.conversations.add_message(user_id, "user", input)
messages = await nm.conversations.get_unextracted_messages(user_id)
await nm.extract_memories(user_id, messages=messages)  # 增量提取

# 或配置 ExtractionStrategy 自动提取（推荐）
# nm = NeuroMemory(..., extraction=ExtractionStrategy(message_interval=10))

# 每天 0 点执行
await nm.reflect(user_id)  # 全面整理
```

---

## KV 存储

键值存储，用于用户偏好、配置等结构化数据。

### nm.kv.set()

```python
await nm.kv.set(
    namespace: str,
    scope: str,
    key: str,
    value: Any,
) -> None
```

**参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `namespace` | `str` | 命名空间（如 `"preferences"`, `"config"`） |
| `scope` | `str` | 作用域，通常是 `user_id` |
| `key` | `str` | 键名 |
| `value` | `Any` | 值（支持 str, int, float, bool, dict, list, None） |

**示例**：

```python
# 存储用户偏好
await nm.kv.set("preferences", "alice", "language", "zh-CN")
await nm.kv.set("preferences", "alice", "theme", {"mode": "dark", "color": "blue"})

# 存储配置
await nm.kv.set("config", "alice", "model", "gpt-4")
```

### nm.kv.get()

```python
value = await nm.kv.get(
    namespace: str,
    scope: str,
    key: str,
) -> Any | None
```

**返回**：值，不存在时返回 `None`。

**示例**：

```python
lang = await nm.kv.get("preferences", "alice", "language")
print(lang)  # "zh-CN"

theme = await nm.kv.get("preferences", "alice", "theme")
print(theme)  # {"mode": "dark", "color": "blue"}
```

### nm.kv.list()

```python
items = await nm.kv.list(
    namespace: str,
    scope: str,
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
    namespace: str,
    scope: str,
    key: str,
) -> bool
```

**返回**：删除成功返回 `True`，键不存在返回 `False`。

### nm.kv.batch_set()

```python
await nm.kv.batch_set(
    namespace: str,
    scope: str,
    items: dict[str, Any],
) -> None
```

**示例**：

```python
await nm.kv.batch_set("preferences", "alice", {
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

**关闭会话**，如果配置了 `ExtractionStrategy.on_session_close=True`，会自动触发记忆提取。

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
    file_id: str,
) -> Document | None
```

### nm.files.delete()

```python
success = await nm.files.delete(
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

基于 Apache AGE 的知识图谱。

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

NodeType.USER       # 用户
NodeType.ENTITY     # 实体（公司、地点等）
NodeType.TOPIC      # 主题
NodeType.EVENT      # 事件
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
EdgeType.WORKS_AT        # 工作于
EdgeType.INTERESTED_IN   # 感兴趣
EdgeType.KNOWS           # 认识
EdgeType.RELATED_TO      # 相关
EdgeType.CUSTOM          # 自定义
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
    node_type: NodeType,
    node_id: str,
) -> dict | None
```

### nm.graph.get_neighbors()

```python
neighbors = await nm.graph.get_neighbors(
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

### nm.graph.query()

```python
results = await nm.graph.query(
    cypher: str,
    params: dict | None = None,
) -> list
```

**执行原始 Cypher 查询**（高级用法）。

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
    async def generate(self, prompt: str, **kwargs) -> str:
        """生成文本"""
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

        # 1. 存储对话
        await nm.conversations.add_message(
            user_id=user_id,
            role="user",
            content="我在 Google 工作，做后端开发，最近压力有点大"
        )

        # 2. 提取记忆
        messages = await nm.conversations.get_unextracted_messages(user_id=user_id)
        stats = await nm.extract_memories(user_id=user_id, messages=messages)
        print(f"提取了 {stats['facts_stored']} 条事实")

        # 3. 召回记忆
        result = await nm.recall(user_id=user_id, query="工作情况", limit=5)
        for mem in result["merged"]:
            print(f"[{mem['source']}] {mem['content']}")

        # 4. 查询偏好
        lang = await nm.kv.get("preferences", user_id, "language")

        # 5. 定期整理
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
await nm.kv.batch_set(namespace, scope, items)

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

## 学术基础

- **Generative Agents** (Stanford, 2023)：三因子检索、反思机制
- **ACT-R 认知架构**：访问追踪、基础激活
- **LeDoux 情感记忆理论** (1996)：情感标注
- **Russell Circumplex Model**：valence-arousal 模型
- **Ebbinghaus 遗忘曲线**：时间衰减

---

**更多示例**: [GETTING_STARTED.md](GETTING_STARTED.md)
**架构文档**: [ARCHITECTURE.md](ARCHITECTURE.md)
