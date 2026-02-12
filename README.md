# NeuroMemory

**AI Agent 记忆框架**

为 AI agent 开发者提供记忆管理能力。直接在 Python 程序中使用，无需部署服务器。

---

## 快速开始

```bash
# 1. 启动 PostgreSQL
docker compose -f docker-compose.v2.yml up -d db

# 2. 安装
pip install -e ".[all]"
```

```python
import asyncio
from neuromemory import NeuroMemory, SiliconFlowEmbedding

async def main():
    async with NeuroMemory(
        database_url="postgresql+asyncpg://neuromemory:neuromemory@localhost:5432/neuromemory",
        embedding=SiliconFlowEmbedding(api_key="your-key"),
    ) as nm:
        # 添加记忆
        await nm.add_memory(
            user_id="alice",
            content="I work at ABC Company as a software engineer",
            memory_type="fact",
        )

        # 三因子检索（相关性 × 时效性 × 重要性）
        result = await nm.recall(user_id="alice", query="Where does Alice work?")
        for r in result["merged"]:
            print(f"[{r['score']:.2f}] {r['content']}")

asyncio.run(main())
```

**完整指南**: [docs/v2/GETTING_STARTED.md](docs/v2/GETTING_STARTED.md)

---

## 核心特性

### 功能模块

| 模块 | 入口 | 功能 |
|------|------|------|
| **语义记忆** | `nm.add_memory()` / `nm.search()` | 存储文本并自动生成 embedding，向量相似度检索 |
| **三因子检索** | `nm.recall()` | relevance × recency × importance 综合评分检索 |
| **KV 存储** | `nm.kv` | 通用键值存储（偏好、配置），namespace + scope 隔离 |
| **对话管理** | `nm.conversations` | 会话消息存储、批量导入、会话列表 |
| **文件管理** | `nm.files` | 文件上传到 S3/MinIO，自动提取文本并生成 embedding |
| **图数据库** | `nm.graph` | 基于 Apache AGE 的知识图谱，节点/边 CRUD、路径查找 |
| **记忆提取** | `nm.extract_memories()` | 用 LLM 从对话中自动提取偏好、事实、事件，含情感标注和重要性评分 |
| **反思** | `nm.reflect()` | 全面记忆整理：重新提取未处理对话 + 生成洞察 + 更新情感画像 |

### 拟人记忆能力

让 AI agent 像朋友般陪伴用户，而非冷冰冰的数据库。

| 能力 | 理论基础 | 实现方式 |
|------|---------|---------|
| **情感标注** | LeDoux 1996 情感标记 + Russell Circumplex | LLM 提取时标注 valence(-1~1)、arousal(0~1)、label，存入 metadata |
| **重要性评分** | Generative Agents (Park 2023) | 每条记忆 1-10 分，影响检索排序（生日=9, 天气=2） |
| **三因子检索** | Generative Agents + Ebbinghaus | `score = relevance × recency × importance`，高 arousal 记忆衰减更慢 |
| **访问追踪** | ACT-R 记忆模型 | 自动记录 access_count 和 last_accessed_at |
| **反思机制** | Generative Agents Reflection | 定期从近期记忆提炼高层洞察（pattern/summary），更新情感画像 |

#### 记忆类型总结

| 记忆类型 | 存储方式 | 检索方式 | 示例 |
|---------|---------|---------|------|
| **偏好** | KV Store | 精确 key 查找 | `language=zh-CN` |
| **事实** | Embedding + Graph | 向量搜索 + 图遍历 | "在 Google 工作" |
| **情景** | Embedding | 向量搜索 | "昨天面试很紧张" |
| **关系** | Graph Store | 实体遍历 | `(user)-[works_at]->(Google)` |
| **洞察** | Embedding | 向量搜索 | • 行为模式："用户倾向于晚上工作"<br>• 阶段总结："用户近期在准备跳槽" |
| **情感画像** | Table | 结构化查询 | "容易焦虑，对技术兴奋" |
| **通用** | Embedding | 向量搜索 | 手动 `add_memory()` 的内容 |

#### 三层情感架构

NeuroMemory 独创的三层情感设计，让 AI agent 既能记住具体事件的情感，又能理解用户的长期情感特质：

| 层次 | 类型 | 存储位置 | 时间性 | 示例 |
|------|------|---------|--------|------|
| **微观** | 事件情感标注 | fact/episodic.metadata | 瞬时 | "说到面试时很紧张(valence=-0.6)" |
| **中观** | 近期情感状态 | emotion_profiles.latest_state | 1-2周 | "最近工作压力大，情绪低落" |
| **宏观** | 长期情感画像 | emotion_profiles.* | 长期稳定 | "容易焦虑，但对技术话题兴奋" |

**为什么需要三层？**
- 微观：捕捉瞬时情感，丰富记忆细节
- 中观：追踪近期状态，agent 可以关心"你最近还好吗"
- 宏观：理解长期特质，形成真正的用户画像

> **不做的事**：不自动推断用户人格 (Big Five) 或价值观。EU AI Act Article 5 禁止基于人格特征做自动化画像，Replika 因此被罚款 500 万欧元。人格和价值观应由开发者通过 system prompt 设定 agent 角色。

---

### 如何使用

NeuroMemory 的核心使用流程围绕三个关键操作：

**插入记忆（add_memory）**：
- 手动添加记忆：`await nm.add_memory(user_id, content, memory_type)`
- 自动提取记忆：`await nm.extract_memories(user_id)`（需要 LLM）
- 目的：将用户的对话、事件、知识转化为结构化记忆存储

**召回记忆（recall）**：
- 智能检索：`await nm.recall(user_id, query)`
- 目的：根据查询语义，综合考虑相关性、时效性、重要性，找出最匹配的记忆
- 在对话中使用：让 agent 能"想起"相关的历史信息来回应用户

**整理记忆（reflect）**：
- 定期整理：`await nm.reflect(user_id)`
- 目的：从海量碎片记忆中提炼高层洞察（行为模式、阶段总结），更新情感画像
- **持续学习系统**：这不是简单的数据存储，而是让 agent 真正"认识"用户的过程
  - 理解用户的思维模式："他喜欢在晚上工作，遇到难题会先查文档再问人"
  - 捕捉情感变化："最近因为项目延期压力大，但聊到新技术时很兴奋"
  - 形成长期认知："容易焦虑但韧性强，对技术话题敏感，重视效率"
- 让记忆从"流水账"升华为"理解"，agent 不再是工具，而是真正了解你的伙伴

**逻辑关系**：
```
对话进行中 → 插入记忆 (add_memory / extract_memories)
     ↓
agent 需要上下文 → 召回记忆 (recall) ← 根据查询找出相关记忆
     ↓
积累一定量后 → 整理记忆 (reflect) → 生成洞察 + 更新情感画像
```

通过 `ExtractionStrategy` 可以配置自动触发时机（如每 10 条消息提取，每 50 次提取后反思），也可以完全手动控制。

---

#### 1. 获取不同类型的记忆

NeuroMemory 提供 7 种记忆类型，每种有不同的获取方式：

| 记忆类型 | 如何获取 | 代码示例 |
|---------|---------|---------|
| **偏好** | `nm.kv.get()` | `lang = await nm.kv.get("preferences", "alice", "language")` |
| **事实** | `nm.recall()` 或 `nm.search()` | `facts = await nm.recall("alice", "工作信息")` |
| **情景** | `nm.recall()` 或 `nm.search()` | `episodes = await nm.recall("alice", "面试经历")` |
| **关系** | `nm.graph.get_neighbors()` | `relations = await nm.graph.get_neighbors("alice", "User")` |
| **洞察** | `nm.search(memory_type="insight")` | `insights = await nm.search("alice", "行为模式", memory_type="insight")` |
| **情感画像** | 直接查询数据库 | `profile = await get_emotion_profile(user_id)` |
| **通用** | `nm.search()` 或 `nm.recall()` | `all = await nm.search("alice", "相关内容")` |

**查询方式对比**：
- `search()`: 纯向量相似度，简单快速
- `recall()`: 综合评分（相关性 × 时效性 × 重要性），推荐使用
- `kv.get()`: 精确键值查询，用于偏好配置
- `graph.*`: 图遍历查询，用于关系网络

#### 2. 完整使用流程

```python
from neuromemory import NeuroMemory, SiliconFlowEmbedding, OpenAILLM, ExtractionStrategy

async with NeuroMemory(
    database_url="postgresql+asyncpg://...",
    embedding=SiliconFlowEmbedding(api_key="..."),
    llm=OpenAILLM(api_key="..."),  # 可选，用于记忆提取和反思
    extraction_strategy=ExtractionStrategy(
        message_interval=10,       # 每 10 条消息自动提取
        reflection_interval=50,    # 每 50 次提取后自动反思
    )
) as nm:
    # === 步骤 1：对话过程中自动记录 ===
    await nm.conversations.add_message(
        user_id="alice",
        role="user",
        content="我在 Google 工作，主要做后端开发，最近项目压力很大"
    )
    # 自动提取：
    # - fact: "在 Google 工作", "做后端开发"
    # - episodic: "最近项目压力很大" (含 emotion: {valence: -0.6, arousal: 0.7, label: "焦虑"})
    # - preference: {"skill": "后端开发"}
    # - relation: (alice)-[works_at]->(Google)

    # === 步骤 2：对话中智能回忆 ===
    # 回忆工作信息（事实 + 情景）
    work_memories = await nm.recall(user_id="alice", query="工作情况")
    # 返回：["在 Google 工作", "做后端开发", "最近项目压力很大"] (按综合评分排序)

    # 查询偏好设置
    skill = await nm.kv.get("preferences", "alice", "skill")
    # 返回："后端开发"

    # 查询关系网络
    entities = await nm.graph.get_neighbors(node_id="alice", node_type="User")
    # 返回：[(Google, "works_at"), ...]

    # === 步骤 3：定期整理记忆 ===
    result = await nm.reflect(user_id="alice")
    # 执行：
    # 1. 查漏补缺：重新提取未处理的对话
    # 2. 生成洞察：
    #    - pattern: "用户是 Google 的后端工程师"
    #    - summary: "用户近期工作压力大，频繁提到项目延期"
    # 3. 更新情感画像：
    #    - latest_state: "最近工作压力大，情绪偏焦虑"
    #    - emotion_triggers: {"工作": {"valence": -0.5}}

    print(f"提取了 {result['facts_added']} 个事实")
    print(f"生成了 {result['insights_generated']} 条洞察")

    # 查询洞察（高层理解）
    insights = await nm.search(user_id="alice", query="用户特点", memory_type="insight")
    # 返回：["用户是 Google 的后端工程师", "用户近期工作压力大"]
```

#### 3. 策略配置

通过 `ExtractionStrategy` 控制自动记忆管理：

```python
ExtractionStrategy(
    message_interval=10,      # 每 10 条消息自动提取记忆（0 = 禁用）
    idle_timeout=600,         # 闲置 10 分钟后自动提取（0 = 禁用）
    reflection_interval=50,   # 每 50 次提取后触发 reflect() 整理（0 = 禁用）
    on_session_close=True,    # 会话关闭时提取
    on_shutdown=True,         # 程序关闭时提取
)
```

**推荐配置**：
- **实时应用**（聊天机器人）：`message_interval=10, reflection_interval=50`
- **批处理**（每日总结）：`message_interval=0, on_session_close=True`，手动调用 `reflect()`
- **开发调试**：全部设为 0，手动控制提取和反思时机

---

## 差异化亮点

与 Mem0、LangChain Memory、Character.AI 等竞品相比，NeuroMemory 的独特优势：

| 特性 | NeuroMemory | Mem0 | LangChain | Character.AI |
|------|------------|------|-----------|--------------|
| **三层情感架构** | ✅ 微观事件 + 中观状态 + 宏观画像 | ❌ | ❌ | 🔶 隐式推断（有争议） |
| **情感标注** | ✅ valence/arousal/label | ❌ | ❌ | ❌ |
| **重要性评分** | ✅ 1-10 分 + 三因子检索 | ✅ 有评分 | ❌ | ❌ |
| **反思机制** | ✅ 行为模式 + 阶段总结洞察 | ❌ | ❌ | 🔶 Diary 机制 |
| **图数据库** | ✅ Apache AGE (Cypher) | 🔶 简单图 | 🔶 LangGraph (不同层) | ❌ |
| **框架嵌入** | ✅ Python 库，直接嵌入 | ✅ | ✅ | ❌ (SaaS) |
| **多模态文件** | ✅ PDF/DOCX 自动提取 | ✅ | ❌ | ❌ |
| **隐私合规** | ✅ 不推断人格/价值观 | ❓ | ❓ | ❌ (GDPR 罚款) |

**核心差异点**：
1. **情感认知**：NeuroMemory 是唯一实现三层情感架构的开源记忆框架，让 agent 能像人一样理解和回应用户的情感变化
2. **理论基础**：基于认知心理学（LeDoux、Ebbinghaus、ACT-R）和最新 AI 研究（Generative Agents），不是简单的向量数据库封装
3. **隐私优先**：严格遵守 EU AI Act 和 GDPR，不做有争议的人格推断

---

### 可插拔 Provider

```
EmbeddingProvider (ABC)
├── SiliconFlowEmbedding   # BAAI/bge-m3, 1024 维
└── OpenAIEmbedding        # text-embedding-3-small, 1536 维

LLMProvider (ABC)
└── OpenAILLM              # 兼容 OpenAI / DeepSeek

ObjectStorage (ABC)
└── S3Storage              # 兼容 MinIO / AWS S3 / 华为云 OBS
```

### 统一存储

- **PostgreSQL 16 + pgvector**: 结构化数据 + 向量检索
- **Apache AGE**: 图数据库（Cypher 查询）
- **ACID 事务**: 数据一致性保证

### 异步优先

- 全链路 async/await（SQLAlchemy 2.0 + asyncpg）
- 上下文管理器自动管理连接生命周期

---

## 文档

| 文档 | 说明 |
|------|------|
| **[快速开始](docs/v2/GETTING_STARTED.md)** | 10 分钟上手指南 |
| **[架构设计](docs/v2/ARCHITECTURE.md)** | 系统架构、Provider 模式、数据模型 |
| **[使用指南](docs/v2/SDK_GUIDE.md)** | 完整 API 用法和代码示例 |
| **[CLAUDE.md](CLAUDE.md)** | Claude Code 工作指南 |

---

## 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                   NeuroMemory 架构                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         应用层 (Your Agent Code)                      │  │
│  │  from neuromemory import NeuroMemory                  │  │
│  │  nm = NeuroMemory(database_url=..., embedding=...)    │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐  │
│  │         门面层 (Facade Layer)                         │  │
│  │  nm.kv  nm.conversations  nm.files  nm.graph         │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐  │
│  │         服务层 (Service Layer)                        │  │
│  │  SearchService │ KVService │ ConversationService      │  │
│  │  FileService │ GraphService │ MemoryExtractionService │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐  │
│  │    Provider 层 (可插拔)                               │  │
│  │  EmbeddingProvider │ LLMProvider │ ObjectStorage      │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐  │
│  │    存储层                                             │  │
│  │  PostgreSQL + pgvector + AGE │ MinIO/S3 (可选)       │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| **Framework** | Python 3.10+ async | 直接嵌入 agent 程序 |
| **数据库** | PostgreSQL 16 + pgvector | 向量检索 + 结构化存储 |
| **图数据库** | Apache AGE | Cypher 查询语言 |
| **ORM** | SQLAlchemy 2.0 (async) | asyncpg 驱动 |
| **Embedding** | 可插拔 Provider | SiliconFlow / OpenAI |
| **LLM** | 可插拔 Provider | OpenAI / DeepSeek |
| **文件存储** | S3 兼容 | MinIO / AWS S3 / 华为云 OBS |

---

## 安装

### 环境要求

- **Python**: 3.10+
- **Docker**: 20.0+（用于 PostgreSQL）

### 安装步骤

```bash
# 克隆项目
git clone https://github.com/your-repo/NeuroMemory.git
cd NeuroMemory

# 启动 PostgreSQL（含 pgvector + AGE）
docker compose -f docker-compose.v2.yml up -d db

# 安装（含所有可选依赖）
pip install -e ".[all]"

# 或只安装核心依赖
pip install -e .
```

### 可选依赖

```bash
pip install -e ".[s3]"     # S3/MinIO 文件存储
pip install -e ".[pdf]"    # PDF 文本提取
pip install -e ".[docx]"   # Word 文本提取
pip install -e ".[dev]"    # 开发和测试工具
pip install -e ".[all]"    # 全部依赖
```

详见 [快速开始指南](docs/v2/GETTING_STARTED.md)

---

## 使用示例

### KV 存储

```python
# 存储用户偏好
await nm.kv.set("preferences", "alice", "language", "zh-CN")
await nm.kv.set("preferences", "alice", "theme", {"mode": "dark"})

# 读取
value = await nm.kv.get("preferences", "alice", "language")

# 列出
items = await nm.kv.list("preferences", "alice")
```

### 对话管理

```python
# 添加消息
msg = await nm.conversations.add_message(
    user_id="alice", role="user", content="Hello!"
)

# 批量添加
session_id, ids = await nm.conversations.add_messages_batch(
    user_id="alice",
    messages=[
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello!"},
    ],
)

# 获取历史
messages = await nm.conversations.get_history(user_id="alice", session_id=session_id)
```

### 文件管理

```python
from neuromemory import S3Storage

nm = NeuroMemory(
    database_url="...",
    embedding=SiliconFlowEmbedding(api_key="..."),
    storage=S3Storage(
        endpoint="http://localhost:9000",
        access_key="neuromemory",
        secret_key="neuromemory123",
        bucket="neuromemory",
    ),
)

# 上传文件（自动提取文本、生成 embedding）
doc = await nm.files.upload(
    user_id="alice",
    filename="report.pdf",
    file_data=open("report.pdf", "rb").read(),
    category="work",
    auto_extract=True,
)

# 列出文件
docs = await nm.files.list_documents(user_id="alice", category="work")
```

### 图数据库

```python
from neuromemory.models.graph import NodeType, EdgeType

# 创建节点
await nm.graph.create_node(NodeType.USER, "alice", properties={"name": "Alice"})
await nm.graph.create_node(NodeType.TOPIC, "python", properties={"name": "Python"})

# 创建关系
await nm.graph.create_edge(
    NodeType.USER, "alice",
    EdgeType.INTERESTED_IN,
    NodeType.TOPIC, "python",
)

# 查询邻居
neighbors = await nm.graph.get_neighbors(NodeType.USER, "alice")
```

### 记忆提取（需要 LLM）

```python
from neuromemory import OpenAILLM

nm = NeuroMemory(
    database_url="...",
    embedding=SiliconFlowEmbedding(api_key="..."),
    llm=OpenAILLM(api_key="...", model="deepseek-chat"),
)

# 从对话中自动提取记忆
stats = await nm.extract_memories(user_id="alice", session_id="session_001")
print(f"提取了 {stats['facts_extracted']} 条事实")
```

更多示例见 [使用指南](docs/v2/SDK_GUIDE.md)

---

## 路线图

### Phase 1（已完成）

- [x] PostgreSQL + pgvector 统一存储
- [x] 向量语义检索
- [x] 时间范围查询和时间线聚合
- [x] KV 存储
- [x] 对话管理
- [x] 文件上传和文本提取
- [x] Apache AGE 图数据库
- [x] LLM 记忆分类提取
- [x] 可插拔 Provider（Embedding/LLM/Storage）

### Phase 2（进行中）

- [x] 情感标注（valence / arousal / label）
- [x] 重要性评分（1-10）
- [x] 三因子检索（relevance × recency × importance）
- [x] 访问追踪（access_count / last_accessed_at）
- [x] 反思机制（从记忆中生成高层洞察）
- [ ] 自然遗忘（基于遗忘曲线的记忆衰减）
- [ ] 配额管理
- [ ] 后台任务系统
- [ ] URL 自动下载和解析

### Phase 3（规划中）

- [ ] 用户 Console（Web UI）
- [ ] 运维后台
- [ ] 华为云部署
- [ ] 监控和告警

---

## 贡献

欢迎贡献代码、文档或提出建议！

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交改动 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 提交 Pull Request

---

## 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

---

**NeuroMemory** - 让您的 AI 拥有记忆
