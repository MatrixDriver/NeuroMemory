# neuromem 使用指南

> **Python 版本**: 3.12+
> **最后更新**: 2026-02-24

---

## 目录

1. [安装](#1-安装)
2. [初始化](#2-初始化)
3. [语义记忆](#3-语义记忆)
4. [KV 存储](#4-kv-存储)
5. [对话管理](#5-对话管理)
6. [文件管理](#6-文件管理)
7. [图数据库](#7-图数据库)
8. [记忆提取](#8-记忆提取)
9. [时间查询](#9-时间查询)
10. [错误处理](#10-错误处理)
11. [自定义 Provider](#11-自定义-provider)
12. [数据生命周期与分析](#12-数据生命周期与分析)
13. [如何用 recall() 组装 Prompt](#13-如何用-recall-组装-prompt)

---

## 1. 安装

```bash
# 核心依赖
pip install -e .

# 全部可选依赖
pip install -e ".[all]"
```

依赖 PostgreSQL（含 pgvector）：
```bash
docker compose -f docker-compose.yml up -d db
```

---

## 2. 初始化

### 2.1 基础初始化

```python
from neuromem import NeuroMemory, SiliconFlowEmbedding, OpenAILLM

nm = NeuroMemory(
    database_url="postgresql+asyncpg://neuromem:neuromem@localhost:5432/neuromem",
    embedding=SiliconFlowEmbedding(api_key="your-key"),
    llm=OpenAILLM(api_key="your-llm-key", model="deepseek-chat"),
)
await nm.init()   # 创建表、初始化扩展

# 使用...

await nm.close()  # 关闭连接池
```

### 2.2 上下文管理器（推荐）

```python
async with NeuroMemory(
    database_url="postgresql+asyncpg://...",
    embedding=SiliconFlowEmbedding(api_key="..."),
    llm=OpenAILLM(api_key="...", model="deepseek-chat"),
) as nm:
    await nm.ingest(user_id="alice", role="user", content="Hello")
    # 自动调用 init() 和 close()
```

### 2.3 完整配置

```python
from neuromem import (
    neuromem,
    SiliconFlowEmbedding,
    OpenAILLM,
    S3Storage,
)

nm = NeuroMemory(
    database_url="postgresql+asyncpg://user:pass@host:5432/db",
    embedding=SiliconFlowEmbedding(api_key="..."),
    llm=OpenAILLM(                          # 必需：记忆提取和反思
        api_key="...",
        model="deepseek-chat",
        base_url="https://api.deepseek.com/v1",
    ),
    storage=S3Storage(                       # 可选：文件存储
        endpoint="http://localhost:9000",
        access_key="neuromem",
        secret_key="neuromem123",
        bucket="neuromem",
    ),
    pool_size=20,                            # 数据库连接池大小
)
```

### 2.4 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| database_url | str | 是 | PostgreSQL 连接字符串 |
| embedding | EmbeddingProvider | 是 | Embedding 服务 |
| llm | LLMProvider | 是 | LLM 服务（记忆提取和反思） |
| storage | ObjectStorage | 否 | 文件存储（文件功能需要） |
| pool_size | int | 否 | 连接池大小（默认 10） |
| auto_extract | bool | 否 | 自动提取记忆（默认 True） |
| graph_enabled | bool | 否 | 启用图数据库（默认 False） |
| reflection_interval | int | 否 | 每 N 次提取后自动 digest（默认 20，0 = 禁用） |
| on_extraction | Callable | 否 | 提取完成回调 |

---

## 3. 记忆写入与检索

### 3.1 通过对话写入记忆

记忆通过 `ingest()` 自动提取，无需手动添加：

```python
# 存储对话消息，自动提取记忆（facts/episodes/relations）
await nm.ingest(
    user_id="alice",
    role="user",
    content="I work at ABC Company as a software engineer",
)
# → 自动提取: fact: "在 ABC Company 工作", fact: "软件工程师"
```

记忆类型（由 LLM 自动分类）：

| 类型 | 说明 | 示例 |
|------|------|------|
| `fact` | 事实性知识 | "Python 是一种编程语言" |
| `episodic` | 事件记录 | "昨天参加了项目会议" |
| `insight` | 洞察（digest 生成） | "用户倾向于晚上工作" |
| `general` | 通用 | 其他 |

> **注**：用户偏好（如"喜欢喝咖啡"）由 LLM 自动提取后存入 profile（KV 存储），不作为独立记忆类型。

### 3.2 混合检索（recall）

```python
# 基础检索（三因子评分：相关性 x 时效性 x 重要性）
result = await nm.recall(
    user_id="alice",
    query="Where does Alice work?",
)

# 带过滤
result = await nm.recall(
    user_id="alice",
    query="meetings",
    memory_type="episodic",
    limit=20,
)

# 结果格式
for r in result["merged"]:
    print(f"[{r['score']:.2f}] {r['content']}")
```

---

## 4. KV 存储

通用键值存储，按 `namespace + scope_id + key` 隔离。

### 4.1 基础 CRUD

```python
# 设置（支持任意 JSON 值）
await nm.kv.set("alice", "config", "language", "zh-CN")
await nm.kv.set("alice", "config", "theme", {"mode": "dark"})
await nm.kv.set("global", "settings", "max_tokens", 4096)

# 获取
value = await nm.kv.get("alice", "config", "language")
# 返回 "zh-CN"，不存在返回 None

# 删除
deleted = await nm.kv.delete("alice", "config", "language")
# 返回 True/False
```

### 4.2 列出和批量操作

```python
# 列出 namespace + scope 下所有键值
items = await nm.kv.list("alice", "config")
for item in items:
    print(f"{item.key}: {item.value}")

# 按前缀过滤
items = await nm.kv.list("alice", "config", prefix="theme")

# 批量设置
await nm.kv.batch_set("alice", "config", {
    "language": "zh-CN",
    "theme": {"mode": "dark"},
    "font_size": 14,
})
```

---

## 5. 对话管理

### 5.1 添加消息

```python
# 单条消息（自动生成 session_id）
msg = await nm.ingest(
    user_id="alice",
    role="user",
    content="Hello!",
)
print(msg.session_id)  # session_xxxx

# 指定 session
msg = await nm.ingest(
    user_id="alice",
    role="assistant",
    content="Hi! How can I help?",
    session_id="my_session_001",
)
```

### 5.2 批量添加

```python
session_id, message_ids = await nm.conversations.add_messages_batch(
    user_id="alice",
    messages=[
        {"role": "user", "content": "What's the weather?"},
        {"role": "assistant", "content": "It's sunny today!"},
        {"role": "user", "content": "Great, thanks!"},
    ],
    session_id="weather_chat",
)
```

### 5.3 查询

```python
# 获取会话历史
messages = await nm.conversations.get_session_messages(
    user_id="alice",
    session_id="my_session_001",
    limit=50,
)

# 列出所有会话
sessions = await nm.conversations.list_sessions(
    user_id="alice",
    limit=20,
)
for s in sessions:
    print(f"Session {s.session_id}: {s.message_count} messages")
```

---

## 6. 文件管理

需要配置 `S3Storage`。

### 6.1 上传文件

```python
# 上传文件（自动提取文本 + 生成 embedding）
doc = await nm.files.upload(
    user_id="alice",
    filename="report.pdf",
    file_data=open("report.pdf", "rb").read(),
    category="work",
    tags=["quarterly", "finance"],
    auto_extract=True,  # 默认 True
)

print(f"ID: {doc.id}")
print(f"Extracted: {len(doc.extracted_text or '')} chars")
```

### 6.2 从文本创建文档

```python
doc = await nm.files.create_from_text(
    user_id="alice",
    title="Meeting Notes",
    content="Today we discussed the Q1 roadmap...",
    category="notes",
)
```

### 6.3 查询和删除

```python
# 列出文件
docs = await nm.files.list(
    user_id="alice",
    category="work",
    file_types=["pdf", "docx"],
)

# 获取单个文件
doc = await nm.files.get(file_id=some_uuid)

# 删除文件（同时删除存储和数据库记录）
await nm.files.delete(file_id=some_uuid)
```

### 6.4 支持的文件类型

| 类型 | 扩展名 | 文本提取 |
|------|--------|---------|
| 文本 | .txt, .md, .json, .yaml, .csv, .html, .xml | 直接读取 |
| 代码 | .py, .js, .ts, .java, .go, .sql, .sh | 直接读取 |
| PDF | .pdf | pypdf |
| Word | .docx | python-docx |
| 图片 | .png, .jpg, .gif, .webp | 仅存储，不提取 |

---

## 7. 图数据库

图数据库（基于 PostgreSQL 关系表，无 Cypher 依赖）。

### 7.1 节点和关系类型

```python
from neuromem.models.graph import NodeType, EdgeType

# 内置节点类型
NodeType.USER         # 用户
NodeType.ENTITY       # 通用实体
NodeType.ORGANIZATION # 组织/公司
NodeType.LOCATION     # 地点
NodeType.SKILL        # 技能

# 内置关系类型（Fact）
EdgeType.WORKS_AT     # 工作于
EdgeType.LIVES_IN     # 居住于
EdgeType.HAS_SKILL    # 拥有技能
EdgeType.STUDIED_AT   # 就读于
EdgeType.KNOWS        # 认识
EdgeType.HOBBY        # 爱好
EdgeType.SPEAKS       # 会说语言
# 内置关系类型（Episode）
EdgeType.MET          # 见面
EdgeType.ATTENDED     # 参加活动
EdgeType.VISITED      # 访问地点
# 通用
EdgeType.RELATED_TO   # 相关
EdgeType.CUSTOM       # 自定义
```

### 7.2 节点 CRUD

```python
# 创建节点
node = await nm.graph.create_node(
    NodeType.USER, "alice",
    properties={"name": "Alice", "age": 30},
    user_id="alice",
)

# 获取节点
node = await nm.graph.get_node("alice", NodeType.USER, "alice")

# 更新节点
await nm.graph.update_node("alice", NodeType.USER, "alice", {"age": 31})

# 删除节点（同时删除相关边）
await nm.graph.delete_node("alice", NodeType.USER, "alice")
```

### 7.3 关系 CRUD

```python
# 创建关系
edge = await nm.graph.create_edge(
    NodeType.USER, "alice",
    EdgeType.WORKS_AT,
    NodeType.ENTITY, "google",
    properties={"since": "2020"},
)

# 更新关系
await nm.graph.update_edge(
    NodeType.USER, "alice",
    EdgeType.WORKS_AT,
    NodeType.ENTITY, "google",
    {"role": "ML engineer"},
)

# 删除关系
await nm.graph.delete_edge(
    NodeType.USER, "alice",
    EdgeType.WORKS_AT,
    NodeType.ENTITY, "google",
)
```

### 7.4 查询

```python
# 获取邻居
neighbors = await nm.graph.get_neighbors(
    "alice", NodeType.USER, "alice",
    edge_types=[EdgeType.WORKS_AT],
    direction="out",
    limit=20,
)

# 查找路径
path = await nm.graph.find_path(
    "alice", NodeType.USER, "alice",
    NodeType.ENTITY, "google",
    max_depth=3,
)
```

---

## 8. 记忆提取

需要配置 `LLMProvider`。`ingest()` 默认 `auto_extract=True`，每条消息自动提取记忆。

### 8.1 基础用法

```python
from neuromem import OpenAILLM

nm = NeuroMemory(
    database_url="...",
    embedding=SiliconFlowEmbedding(api_key="..."),
    llm=OpenAILLM(api_key="...", model="deepseek-chat"),
    reflection_interval=20,  # 每 20 条消息后台自动 digest（默认）
)

# ingest 自动提取记忆
await nm.ingest(
    user_id="alice", role="user",
    content="I just started working at Google as a ML engineer"
)
# → 自动提取: fact "在 Google 担任 ML 工程师", profile.interests 更新

# digest 生成洞察（默认自动触发，也可手动调用）
result = await nm.digest(user_id="alice")
```

### 8.2 提取结果（ingest 返回后记忆立即可用）

```python
# recall 可立即检索到刚提取的记忆
result = await nm.recall(user_id="alice", query="Where does Alice work?")
# result["merged"] 包含: fact "在 Google 担任 ML 工程师"

# digest 返回
{
    "insights_generated": 1,      # 生成洞察数
    "insights": [{"content": "...", "category": "pattern"}],
    "emotion_profile": {...},
}
```

---

## 9. 时间查询

### 9.1 时间范围查询

```python
from datetime import datetime, timezone

result = await nm.get_memories_by_time_range(
    user_id="alice",
    start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
    end_time=datetime(2026, 1, 31, 23, 59, 59, tzinfo=timezone.utc),
    memory_type="fact",
    limit=50,
)
```

### 9.2 最近记忆

```python
memories = await nm.get_recent_memories(
    user_id="alice",
    days=7,
    memory_types=["fact", "episodic"],
    limit=50,
)
```

### 9.3 时间线统计

```python
from datetime import date

stats = await nm.get_memory_timeline(
    user_id="alice",
    start_date=date(2026, 1, 1),
    end_date=date(2026, 1, 31),
    granularity="day",  # day, week, month
)
```

---

## 10. 错误处理

```python
try:
    result = await nm.recall(user_id="alice", query="test")
except Exception as e:
    # 数据库连接错误、Embedding API 错误等
    print(f"Error: {e}")
```

常见错误：

| 错误 | 原因 | 解决 |
|------|------|------|
| `ConnectionRefusedError` | PostgreSQL 未启动 | 启动 Docker 容器 |
| `ValueError: Storage not configured` | 未配置 S3Storage | 传入 storage 参数 |
| `ValueError: LLM not configured` | 未配置 LLMProvider | 传入 llm 参数 |
| `httpx.HTTPStatusError` | Embedding API 错误 | 检查 API Key |

---

## 11. 自定义 Provider

### 11.1 自定义 Embedding

```python
from neuromem.providers.embedding import EmbeddingProvider

class MyEmbedding(EmbeddingProvider):
    @property
    def dims(self) -> int:
        return 768

    async def embed(self, text: str) -> list[float]:
        # 你的实现
        return await my_service.embed(text)

nm = NeuroMemory(database_url="...", embedding=MyEmbedding())
```

### 11.2 自定义 LLM

```python
from neuromem.providers.llm import LLMProvider

class MyLLM(LLMProvider):
    async def chat(self, messages, temperature=0.7, max_tokens=1024):
        # 你的实现
        return await my_llm.complete(messages)

nm = NeuroMemory(database_url="...", embedding=..., llm=MyLLM())
```

### 11.3 自定义 Storage

```python
from neuromem.storage.base import ObjectStorage

class MyStorage(ObjectStorage):
    async def upload(self, prefix, filename, data, content_type):
        # 你的实现
        return f"{prefix}/{filename}"

    async def download(self, object_key):
        ...

    async def delete(self, object_key):
        ...

nm = NeuroMemory(database_url="...", embedding=..., storage=MyStorage())
```

---

## 12. 数据生命周期与分析

### 12.1 删除用户数据

单事务原子删除用户的全部数据，适用于 GDPR 合规或账号注销：

```python
result = await nm.delete_user_data(user_id="alice")
# → {"deleted": {"embeddings": 15, "conversations": 42, ...}}
```

### 12.2 导出用户数据

导出用户的完整数据（记忆、对话、图谱、KV、画像、文档）：

```python
data = await nm.export_user_data(user_id="alice")
# data["memories"], data["conversations"], data["graph"], data["kv"], ...
```

### 12.3 记忆统计

```python
stats = await nm.stats(user_id="alice")
print(f"总记忆: {stats['total']}")
print(f"按类型: {stats['by_type']}")  # {"fact": 20, "episodic": 15, ...}
print(f"活跃实体: {stats['active_entities']}")
```

### 12.4 冷记忆查询

查找长期未访问的记忆，用于归档或清理：

```python
cold = await nm.cold_memories(user_id="alice", threshold_days=90, limit=50)
for mem in cold:
    print(f"[{mem['memory_type']}] {mem['content'][:50]}...")
```

### 12.5 实体全景

跨类型查询某个实体的全部信息（记忆 + 图谱 + 对话 + 时间线）：

```python
profile = await nm.entity_profile(user_id="alice", entity="Google")
# profile["facts"] — 提及该实体的记忆
# profile["graph_relations"] — 图谱中的关系
# profile["conversations"] — 提及该实体的对话
# profile["timeline"] — 按时间排序的事件线
```

---

## 13. 如何用 recall() 组装 Prompt

> 可运行的完整示例见 **[example/](../example/)**，支持终端交互、命令查询、自动记忆提取。

这是使用 neuromem 最关键的一步——**如何把 recall() 的结果变成高质量的 LLM 上下文**。正确组装 prompt 能充分利用 neuromem 的全部能力：三因子检索、图谱关系、用户画像、情感洞察。

### 13.1 recall() 返回的完整结构

```python
result = await nm.recall(user_id="alice", query=user_input, limit=10)

# result 包含以下字段：
result["merged"]               # ⭐ 主要使用：vector + graph + conversation 去重合并，已按评分排序
result["user_profile"]         # ⭐ 用户画像：occupation, interests, identity 等
result["graph_context"]        # ⭐ 图谱三元组文本：["alice → WORKS_AT → google", ...]
result["vector_results"]       # 提取的记忆（fact/episodic/insight），含评分
result["conversation_results"] # 原始对话片段，保留了日期细节
result["graph_results"]        # 图谱原始三元组
```

**merged 中每条记忆的关键字段**：
```python
# 事实记忆（fact）：持久属性，无日期前缀
{"content": "在 Google 工作",                                       "memory_type": "fact",     "score": 0.82}
# 情节记忆（episodic）：时间戳 = 事件发生的时间
{"content": "2025-03-01: 压力很大，担心项目延期. sentiment: anxious", "memory_type": "episodic", "score": 0.75}
# 洞察记忆（insight）：digest() 自动生成，无时间前缀
{"content": "工作压力大时倾向于回避社交，独自消化",                   "memory_type": "insight",  "score": 0.68}

# 完整字段
{
    "content": "...",                              # 格式化后的内容（含时间前缀）
    "source": "vector",                            # "vector" / "graph" / "conversation"
    "memory_type": "fact",                         # fact / episodic / insight / graph_fact
    "score": 0.646,                                # 综合评分（相关性 × 时效 × 重要性 × 图boost）
    "graph_boost": 1.5,                            # 图三元组覆盖度 boost（仅 source="vector" 时存在）
    "extracted_timestamp": "2025-03-01T00:00:00+00:00",  # 可用于时间排序
    "metadata": {
        "importance": 8,                           # 重要性 (1-10)
        "emotion": {"label": "满足", "valence": 0.6}
    }
}
```

> **时间戳含义**：
> - `fact` 的时间 = 用户**提到**该信息的时间，不代表事情开始的时间
> - `episodic` 的时间 = 事件**发生**的时间
> - 组装 prompt 时应向 LLM 说明这一区别，避免误判时间线

### 13.2 推荐的 Prompt 组装模板

```python
from datetime import datetime, timezone

def build_system_prompt(recall_result: dict, user_input: str) -> str:
    """将 recall() 结果组装为 LLM system prompt。"""

    # 1. 用户画像 → 稳定背景信息，始终放在 system prompt 中
    profile = recall_result.get("user_profile", {})
    profile_lines = []
    if profile.get("identity"):
        profile_lines.append(f"身份：{profile['identity']}")
    if profile.get("occupation"):
        profile_lines.append(f"职业：{profile['occupation']}")
    if profile.get("interests"):
        profile_lines.append(f"兴趣：{profile['interests']}")
    profile_text = "\n".join(profile_lines) if profile_lines else "暂无"

    # 2. merged 按类型分层：facts/insights 按相关性，episodes 按时间升序
    merged = recall_result.get("merged", [])
    facts    = [m for m in merged if m.get("memory_type") == "fact"][:5]
    insights = [m for m in merged if m.get("memory_type") == "insight"][:3]
    # 情节记忆按时间升序 → 完整时间线
    episodes = sorted(
        [m for m in merged if m.get("memory_type") == "episodic"],
        key=lambda m: m.get("extracted_timestamp") or datetime.min.replace(tzinfo=timezone.utc),
    )[:5]

    def fmt(items):
        return "\n".join(f"- {m['content']}" for m in items) or "暂无"

    # 3. 图谱关系 → 结构化事实，补充向量检索的盲区
    graph_lines = recall_result.get("graph_context", [])[:5]
    graph_text = "\n".join(f"- {g}" for g in graph_lines) or "暂无"

    return f"""你是一个有长期记忆的 AI 助手，能根据对用户的了解提供个性化回复。

## 用户画像
{profile_text}

## 关于当前话题，你记得的事实
（括号内时间 = 用户提及该信息的时间，不代表事情开始的时间）
{fmt(facts)}

## 事件时间线（按时间排序）
{fmt(episodes)}

## 对用户的深层理解（洞察）
{fmt(insights)}

## 结构化关系
{graph_text}

---
请根据以上记忆自然地回应用户，不要逐条引用记忆，而是像一个真正了解他的朋友那样对话。
如果记忆与当前问题不相关，忽略它们即可。"""
```

### 13.3 组装 Prompt 的核心原则

| 原则 | 说明 |
|------|------|
| **一次 recall，完整上下文** | 一次 `recall()` 已包含 merged、profile、graph，无需额外查询 |
| **profile 放 system prompt** | 职业、兴趣等稳定画像每次都要注入，是 agent 个性化的基础 |
| **merged 按类型分层** | facts/insights 按相关性，episodes 按时间升序排列，呈现完整时间线 |
| **时间戳含义要说清** | fact 时间 = 用户提及时间；episodic 时间 = 事件发生时间；需在 prompt 中注明区别 |
| **graph_context 补充结构化知识** | 向量检索可能遗漏"alice 在 Google 工作"这类关系，图谱能补充 |
| **insight 自动包含** | 默认 `reflection_interval=20`，insight 自动进入 merged，无需额外调用 |
| **token 预算控制** | 每类记忆取 3-5 条，总记忆上下文建议 400-600 tokens |
| **自然注入，不逐条引用** | system prompt 结尾提示 LLM"像朋友一样对话"，避免机械引用 |

---

**文档维护**: 本文档随代码同步更新。如有问题，请提交 Issue。
