# NeuroMemory API 参考文档

> **版本**: 0.1.0
> **Python**: 3.12+
> **最后更新**: 2026-02-13

---

## 目录

- [初始化](#初始化)
- [核心 API](#核心-api)
  - [recall() - 混合检索](#recall---混合检索)
  - [add_memory() - 添加记忆](#add_memory---添加记忆)
  - [search() - 向量检索](#search---向量检索)
  - [extract_memories() - 提取记忆](#extract_memories---提取记忆)
  - [reflect() - 记忆整理](#reflect---记忆整理)
- [KV 存储](#kv-存储)
- [对话管理](#对话管理)
- [文件管理](#文件管理)
- [图数据库](#图数据库)
- [Provider 接口](#provider-接口)

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
    pool_size: int = 10,
    extraction_strategy: ExtractionStrategy | None = None,
)
```

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `database_url` | `str` | ✅ | PostgreSQL 连接字符串，格式：`postgresql+asyncpg://user:pass@host:port/db` |
| `embedding` | `EmbeddingProvider` | ✅ | Embedding 提供者（SiliconFlowEmbedding / OpenAIEmbedding） |
| `llm` | `LLMProvider` | ❌ | LLM 提供者，用于 `extract_memories()` 和 `reflect()` |
| `storage` | `ObjectStorage` | ❌ | 对象存储，用于文件管理（S3Storage） |
| `pool_size` | `int` | ❌ | 数据库连接池大小，默认 10 |
| `extraction_strategy` | `ExtractionStrategy` | ❌ | 自动记忆提取策略 |

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

## 核心 API

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

### add_memory() - 添加记忆

直接添加结构化记忆，无需 LLM 提取。

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

### search() - 向量检索

纯向量相似度检索（不考虑时间和重要性）。

```python
results = await nm.search(
    user_id: str,
    query: str,
    limit: int = 5,
    memory_type: str | None = None,
) -> list[dict]
```

**参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `user_id` | `str` | - | 用户 ID |
| `query` | `str` | - | 查询文本 |
| `limit` | `int` | `5` | 返回结果数量 |
| `memory_type` | `str` | `None` | 过滤记忆类型 |

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

### extract_memories() - 提取记忆

从对话消息中自动提取结构化记忆（需要 LLM）。

```python
stats = await nm.extract_memories(
    user_id: str,
    session_id: str | None = None,
    limit: int = 50,
) -> dict
```

**参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `user_id` | `str` | - | 用户 ID |
| `session_id` | `str` | `None` | 会话 ID，为 None 时处理所有未提取的消息 |
| `limit` | `int` | `50` | 一次处理的消息数量 |

**返回格式**：

```python
{
    "messages_processed": 10,
    "facts_extracted": 3,
    "preferences_extracted": 2,
    "relations_extracted": 1,
}
```

**提取内容**：

- **事实** (`fact`)：客观信息（"在 Google 工作"）
- **偏好** (`preference`)：存入 KV Store（`preferences` namespace）
- **情景** (`episodic`)：带时间的事件（"昨天面试"）
- **关系** (`relation`)：存入图数据库（(alice)-[works_at]->(Google)）
- **情感标注**：自动标注 valence, arousal, label
- **重要性评分**：1-10 分

**示例**：

```python
# 添加对话消息
await nm.conversations.add_message(
    user_id="alice",
    role="user",
    content="我在 Google 工作，做后端开发"
)

# 提取记忆
stats = await nm.extract_memories(user_id="alice")
print(f"提取了 {stats['facts_extracted']} 条事实")
# 自动生成：
# - fact: "在 Google 工作"
# - fact: "做后端开发"
# - relation: (alice)-[works_at]->(Google)
```

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
    "extraction_stats": {
        "messages_processed": 10,
        "facts_extracted": 3,
        ...
    },
    "insights_generated": 2,
    "emotion_profile_updated": True,
}
```

**工作流程**：

1. **查漏补缺**：重新提取未处理的对话
2. **提炼洞察**：分析近期记忆，生成高层理解
   - 行为模式："用户倾向于晚上工作"
   - 阶段总结："用户近期在准备跳槽"
3. **更新画像**：整合情感数据，更新用户情感画像

**示例**：

```python
# 定期整理记忆
result = await nm.reflect(user_id="alice")

print(f"处理了 {result['extraction_stats']['messages_processed']} 条消息")
print(f"生成了 {result['insights_generated']} 条洞察")

# 查看生成的洞察
insights = await nm.search(user_id="alice", query="", memory_type="insight")
for insight in insights:
    print(insight['content'])
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

### nm.conversations.get_history()

```python
messages = await nm.conversations.get_history(
    user_id: str,
    session_id: str,
    limit: int = 50,
) -> list[ConversationMessage]
```

**返回**：消息列表，按时间倒序。

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
    auto_extract: bool = True,
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
| `auto_extract` | `bool` | `True` | 是否自动提取文本并生成 embedding |
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
    filename: str,
    text: str,
    category: str = "general",
    metadata: dict | None = None,
) -> Document
```

**直接从文本创建文档**（不上传到 S3）。

### nm.files.list_documents()

```python
docs = await nm.files.list_documents(
    user_id: str,
    category: str | None = None,
    limit: int = 10,
) -> list[Document]
```

### nm.files.get_document()

```python
doc = await nm.files.get_document(
    user_id: str,
    document_id: str,
) -> Document | None
```

### nm.files.delete_document()

```python
success = await nm.files.delete_document(
    user_id: str,
    document_id: str,
) -> bool
```

### nm.files.search_files()

```python
results = await nm.files.search_files(
    user_id: str,
    query: str,
    limit: int = 5,
    file_type: str | None = None,
    category: str | None = None,
) -> list[dict]
```

**向量检索文件内容**。

**示例**：

```python
# 检索所有文件
results = await nm.files.search_files(user_id="alice", query="项目报告")

# 只检索 PDF
pdfs = await nm.files.search_files(
    user_id="alice",
    query="技术文档",
    file_type="pdf"
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
    start_type: NodeType,
    start_id: str,
    edge_type: EdgeType,
    end_type: NodeType,
    end_id: str,
    properties: dict | None = None,
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

### nm.graph.get_neighbors()

```python
neighbors = await nm.graph.get_neighbors(
    node_type: NodeType,
    node_id: str,
    edge_type: EdgeType | None = None,
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
        stats = await nm.extract_memories(user_id=user_id)
        print(f"提取了 {stats['facts_extracted']} 条事实")

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

**更多示例**: [docs/v2/GETTING_STARTED.md](v2/GETTING_STARTED.md)
**架构文档**: [docs/v2/ARCHITECTURE.md](v2/ARCHITECTURE.md)
