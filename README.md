# NeuroMemory

**AI Agent 记忆框架**

为 AI agent 开发者提供记忆管理能力。直接在 Python 程序中使用，无需部署服务器。

---

## 安装

### 方式 1: 从 PyPI 安装（推荐）

```bash
# 基础安装（包含核心功能）
pip install neuromemory

# 或安装所有可选依赖（推荐）
pip install neuromemory[all]

# 按需安装
pip install neuromemory[s3]    # S3/MinIO 文件存储
pip install neuromemory[pdf]   # PDF 文件处理
pip install neuromemory[docx]  # Word 文档处理
```

**依赖自动安装**: SQLAlchemy、asyncpg、pgvector、httpx 等核心依赖会自动安装。

### 方式 2: 从源码安装（开发者）

```bash
git clone https://github.com/yourusername/NeuroMemory
cd NeuroMemory
pip install -e ".[dev]"  # 包含测试工具
```

---

## 外部依赖

NeuroMemory 需要以下外部服务（**不包含在 pip 包中**）：

### 1. PostgreSQL 16+ with pgvector（必需）

```bash
# 使用项目提供的 Docker Compose
docker compose -f docker-compose.yml up -d db

# 或使用官方镜像
docker run -d -p 5432:5432 \
  -e POSTGRES_USER=neuromemory \
  -e POSTGRES_PASSWORD=neuromemory \
  -e POSTGRES_DB=neuromemory \
  ankane/pgvector:pg16
```

### 2. Embedding Provider（必需，三选一）

- **本地模型**（无需 API Key）：`pip install sentence-transformers`，使用本地 transformer 模型
- **SiliconFlow**：[siliconflow.cn](https://siliconflow.cn/)，需要 API Key
- **OpenAI**：[platform.openai.com](https://platform.openai.com/)，需要 API Key

### 3. LLM API Key（用于自动提取记忆，可选）

- [OpenAI](https://platform.openai.com/) 或 [DeepSeek](https://platform.deepseek.com/)
- 不使用 LLM 时，仍可手动通过 `add_memory()` 添加记忆并用 `recall()`/`search()` 检索

### 4. MinIO/S3（可选，仅用于文件存储）

```bash
docker compose -f docker-compose.yml up -d minio
```

---

## 快速开始

```python
import asyncio
from neuromemory import NeuroMemory, SiliconFlowEmbedding, OpenAILLM

async def main():
    async with NeuroMemory(
        database_url="postgresql+asyncpg://neuromemory:neuromemory@localhost:5432/neuromemory",
        embedding=SiliconFlowEmbedding(api_key="your-key"),
        llm=OpenAILLM(api_key="your-openai-key"),  # 用于自动提取记忆
        auto_extract=True,  # 默认启用，像 mem0 那样实时提取记忆
    ) as nm:
        # 1. 存储对话消息 → 自动提取记忆（facts/episodes/relations）
        await nm.conversations.add_message(
            user_id="alice", role="user",
            content="I work at ABC Company as a software engineer"
        )
        # → 后台自动提取：fact: "在 ABC Company 工作", relation: (alice)-[works_at]->(ABC Company)

        # 2. 三因子检索（相关性 × 时效性 × 重要性）
        result = await nm.recall(user_id="alice", query="Where does Alice work?")
        for r in result["merged"]:
            print(f"[{r['score']:.2f}] {r['content']}")

        # 3. 生成洞察和情感画像（可选，定期调用）
        insights = await nm.reflect(user_id="alice")
        print(f"生成了 {insights['insights_generated']} 条洞察")

asyncio.run(main())
```

### 核心操作流程

NeuroMemory 的核心使用围绕三个操作：

**插入记忆**（自动模式，默认）：
- 对话驱动：`add_message()` 存储对话 **并自动提取记忆**（推荐，像 mem0）
- 直接添加：`add_memory(user_id, content, memory_type)`（手动指定类型，不需要 LLM）

**召回记忆（recall）**：
- `await nm.recall(user_id, query)` — 综合考虑相关性、时效性、重要性，找出最匹配的记忆
- 在对话中使用：让 agent 能"想起"相关的历史信息来回应用户

**生成洞察（reflect）**（可选，定期调用）：
- `await nm.reflect(user_id)` — 高层记忆分析：
  1. **提炼洞察**：从已提取的记忆生成高层理解（行为模式、阶段总结）
  2. **更新画像**：整合情感数据，更新用户情感画像
- 让记忆从"事实"升华为"洞察"

> **关键变化**（v0.2.0）：`add_message()` 现在默认自动提取记忆（`auto_extract=True`），无需手动调用 `extract_memories()` 或 `reflect()`。`reflect()` 专注于生成洞察和情感画像，不再提取基础记忆。

**逻辑关系**：
```
对话进行中 → 存储消息 (add_message) → 自动提取记忆
     ↓
agent 需要上下文 → 召回记忆 (recall)
     ↓
定期分析 → 生成洞察 (reflect) → 洞察 + 情感画像
```

**配置选项**：
- **自动模式**（默认，推荐）：`auto_extract=True`，每次 `add_message` 都提取记忆
- **手动模式**：`auto_extract=False`，手动调用 `extract_memories()`
- **策略模式**：`auto_extract=False` + `ExtractionStrategy(message_interval=10)`，每 10 条消息触发

---

## 核心特性

### 记忆分类

NeuroMemory 提供 7 种记忆类型，每种有不同的存储和获取方式：

| 记忆类型 | 存储方式 | 底层存储 | 获取方式 | 示例 |
|---------|---------|---------|---------|------|
| **事实** | Embedding + Graph | pgvector + Apache AGE | `nm.recall(user_id, query)` | "在 Google 工作" |
| **情景** | Embedding | pgvector | `nm.recall(user_id, query)` | "昨天面试很紧张" |
| **关系** | Graph Store | Apache AGE | `nm.graph.get_neighbors(user_id, type, id)` | `(user)-[works_at]->(Google)` |
| **洞察** | Embedding | pgvector | `nm.search(user_id, query, memory_type="insight")` | "用户倾向于晚上工作" |
| **情感画像** | Table | PostgreSQL | `reflect()` 自动更新 | "容易焦虑，对技术兴奋" |
| **偏好** | KV (Profile) | PostgreSQL | `nm.kv.get(user_id, "profile", "preferences")` | `["喜欢喝咖啡", "偏好深色模式"]` |
| **通用** | Embedding | pgvector | `nm.search(user_id, query)` | 手动 `add_memory()` 的内容 |

### 三因子混合检索

不是简单的向量数据库封装。`recall()` 综合三个因子评分并融合图谱遍历：

```python
Score = rrf_score × recency × importance

rrf_score  = RRF(vector_rank, bm25_rank)                 # 向量 + BM25 关键词混合检索 (RRF 融合)
recency    = e^(-t / decay_rate × (1 + arousal × 0.5))   # 时效性，高情感唤醒衰减更慢
importance = metadata.importance / 10                     # LLM 评估的重要性 (0.1-1.0)
```

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

**图实体检索**：从知识图谱中查找结构化关系（`(alice)-[works_at]->(Google)`），与向量结果去重合并。`recall()` 返回 `vector_results`、`graph_results` 和合并后的 `merged` 列表。

### 三层情感架构

唯一实现三层情感设计的开源记忆框架：

| 层次 | 类型 | 存储位置 | 时间性 | 示例 |
|------|------|---------|--------|------|
| **微观** | 事件情感标注 | 记忆 metadata (valence/arousal/label) | 瞬时 | "说到面试时很紧张(valence=-0.6)" |
| **中观** | 近期情感状态 | emotion_profiles.latest_state | 1-2周 | "最近工作压力大，情绪低落" |
| **宏观** | 长期情感画像 | emotion_profiles.* | 长期稳定 | "容易焦虑，但对技术话题兴奋" |

- 微观：捕捉瞬时情感，丰富记忆细节
- 中观：追踪近期状态，agent 可以关心"你最近还好吗"
- 宏观：理解长期特质，形成真正的用户画像

> **隐私合规**：不自动推断用户人格 (Big Five) 或价值观。EU AI Act Article 5 禁止此类自动化画像。人格和价值观应由开发者通过 system prompt 设定 agent 角色。

### LLM 驱动的记忆提取与反思

- **提取** (`extract_memories`)：从对话中自动识别事实、事件、关系，附带情感标注（valence/arousal/label）和重要性评分（1-10），偏好存入用户画像
- **反思** (`reflect`)：定期从近期记忆提炼高层洞察（行为模式、阶段总结），更新情感画像
- **访问追踪**：自动记录 access_count 和 last_accessed_at，符合 ACT-R 记忆模型

理论基础：Generative Agents (Park 2023) 的 Reflection 机制 + LeDoux 情感标记 + Ebbinghaus 遗忘曲线 + ACT-R 记忆模型。

### 与同类框架对比

| 特性 | NeuroMemory | Mem0 | LangChain Memory |
|------|------------|------|-----------------|
| 三层情感架构 | ✅ 微观+中观+宏观 | ❌ | ❌ |
| 情感标注 | ✅ valence/arousal/label | ❌ | ❌ |
| 重要性评分 + 三因子检索 | ✅ | 🔶 有评分 | ❌ |
| 反思机制 | ✅ 洞察 + 画像更新 | ❌ | ❌ |
| 知识图谱 | ✅ Apache AGE (Cypher) | 🔶 简单图 | 🔶 LangGraph |
| 多模态文件 | ✅ PDF/DOCX 提取 | ✅ | ❌ |
| 框架嵌入 | ✅ Python 库 | ✅ | ✅ |
| 隐私合规 | ✅ 不推断人格 | ❓ | ❓ |

---

## API 使用说明

> 完整 API 参考文档见 **[docs/API.md](docs/API.md)**，包含所有方法的签名、参数、返回值和示例。

NeuroMemory 有三组容易混淆的 API，以下是快速对比：

### ✏️ 写入 API：add_message() vs add_memory()

| API | 用途 | 写入目标 | 何时使用 |
|-----|------|---------|---------|
| **add_message()** ⭐ | 存储对话消息 | 对话历史 → 后续通过 `reflect()` 提取记忆 | **日常使用（推荐）** |
| **add_memory()** | 直接写入记忆 | 记忆表（embedding），立即可检索 | 手动导入、批量初始化、已知结构化信息 |

```python
# add_message(): 对话驱动（推荐）— 先存对话，再用 reflect() 提取记忆
await nm.conversations.add_message(user_id="alice", role="user",
    content="我在 Google 工作，做后端开发")
await nm.reflect(user_id="alice")
# → 自动提取: fact: "在 Google 工作" + 情感标注 + 重要性评分 + 洞察

# add_memory(): 直接写入（手动指定一切）
await nm.add_memory(user_id="alice", content="在 Google 工作",
    memory_type="fact", metadata={"importance": 8})
```

### 📚 检索 API：recall() vs search()

| API | 用途 | 检索方式 | 何时使用 |
|-----|------|---------|---------|
| **recall()** ⭐ | 智能混合检索 | 三因子向量（相关性×时效×重要性）+ 图实体检索 + 去重 | **日常使用（推荐）** |
| **search()** | 纯语义检索 | 仅 embedding 余弦相似度 | 只需语义相似度，不考虑时间和重要性 |

```python
# recall(): 综合考虑，最近的重要记忆优先
result = await nm.recall(user_id="alice", query="工作")
# → "昨天面试 Google"（最近 + 重要）优先于 "去年在微软实习"（久远）

# search(): 只看语义，可能返回很久以前的记忆
results = await nm.search(user_id="alice", query="工作")
# → "去年在微软实习" 和 "昨天面试 Google" 都可能返回，只按相似度排序
```

### 🧠 记忆管理 API：reflect() vs extract_memories()

| API | 用途 | 处理内容 | 何时使用 |
|-----|------|---------|---------|
| **reflect()** ⭐ | 一站式记忆处理 | 提取事实/情景/关系 + 生成洞察 + 更新画像 | **推荐使用**：手动处理记忆时 |
| **extract_memories()** | 仅提取新记忆 | 从对话中提取事实/情景/关系（不生成洞察） | 底层方法：由 `ExtractionStrategy` 自动调用 |

```python
# reflect(): 推荐 — 一站式处理（提取 + 洞察 + 画像）
await nm.conversations.add_message(user_id="alice", role="user", content="我在 Google 工作")
result = await nm.reflect(user_id="alice")
# → 提取: fact: "在 Google 工作", relation: (alice)-[works_at]->(Google)
# → 洞察: "用户近期求职，面试了 Google 和微软"
# → 画像: 更新情感状态

# extract_memories(): 底层方法（通常不需要直接调用）
# 由 ExtractionStrategy 自动调用，用于高频轻量的增量提取
```

### 策略配置（ExtractionStrategy）

通过 `ExtractionStrategy` 控制自动记忆管理，配置后 `add_message()` 会在满足条件时自动触发提取：

```python
from neuromemory import ExtractionStrategy

nm = NeuroMemory(
    ...,
    extraction=ExtractionStrategy(
        message_interval=10,      # 每 10 条消息自动提取记忆（0 = 禁用）
        idle_timeout=600,         # 闲置 10 分钟后自动提取（0 = 禁用）
        reflection_interval=50,   # 每 50 次提取后触发 reflect() 整理（0 = 禁用）
        on_session_close=True,    # 会话关闭时提取
        on_shutdown=True,         # 程序关闭时提取
    )
)
```

**推荐配置**：
- **实时应用**（聊天机器人）：`message_interval=10, reflection_interval=50`
- **批处理**（每日总结）：`message_interval=0, on_session_close=True`，手动调用 `reflect()`
- **开发调试**：全部设为 0，手动控制提取和反思时机

---

## 完整 Agent 示例

> 可运行的完整示例见 **[example/](example/)**，支持终端交互、命令查询、自动记忆提取。无需 Embedding API Key。

以下是一个带记忆的聊天 agent 核心实现：

```python
from neuromemory import NeuroMemory, SiliconFlowEmbedding, OpenAILLM, ExtractionStrategy
from openai import AsyncOpenAI

class MemoryAgent:
    def __init__(self, nm: NeuroMemory, openai_client: AsyncOpenAI):
        self.nm = nm
        self.llm = openai_client

    async def chat(self, user_id: str, user_input: str) -> str:
        """处理用户输入，返回 agent 回复"""

        # === 步骤 1：存储用户消息（自动提取记忆）===
        await self.nm.conversations.add_message(
            user_id=user_id,
            role="user",
            content=user_input
        )
        # → 如果启用 auto_extract，记忆已自动提取

        # === 步骤 2：召回相关记忆 ===
        recall_result = await self.nm.recall(user_id=user_id, query=user_input, limit=5)
        memories = recall_result["merged"]

        # 获取用户偏好（从 profile 中）
        lang_kv = await self.nm.kv.get(user_id, "profile", "language")
        language = lang_kv.value if lang_kv else "zh-CN"

        # 获取近期洞察
        insights = await self.nm.search(user_id, user_input, memory_type="insight", limit=3)

        # === 步骤 3：构建包含记忆的 prompt ===
        memory_context = "\n".join([
            f"- {m['content']} (重要性: {m.get('metadata', {}).get('importance', 5)})"
            for m in memories[:3]
        ]) if memories else "暂无相关记忆"

        insight_context = "\n".join([
            f"- {i['content']}" for i in insights
        ]) if insights else "暂无深度理解"

        system_prompt = f"""你是一个有记忆的 AI 助手。请用 {language} 语言回复。

        **关于用户的具体记忆**：
        {memory_context}

        **对用户的深度理解（洞察）**：
        {insight_context}

        请根据这些记忆和理解，以朋友的口吻自然地回应用户。"""

        # === 步骤 4：调用 LLM 生成回复 ===
        response = await self.llm.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ]
        )
        assistant_reply = response.choices[0].message.content

        # === 步骤 5：存储 assistant 回复 ===
        await self.nm.conversations.add_message(
            user_id=user_id,
            role="assistant",
            content=assistant_reply
        )

        return assistant_reply


# 使用示例
async def main():
    async with NeuroMemory(
        database_url="postgresql+asyncpg://...",
        embedding=SiliconFlowEmbedding(api_key="..."),
        llm=OpenAILLM(api_key="..."),
        auto_extract=True,  # 默认启用，每次 add_message 都提取记忆（推荐）
    ) as nm:
        agent = MemoryAgent(nm, AsyncOpenAI(api_key="..."))

        # 第一轮对话
        reply1 = await agent.chat("alice", "我在 Google 工作，做后端开发，最近压力有点大")
        print(f"Agent: {reply1}")

        # → add_message 自动提取记忆：
        #   fact: "在 Google 工作", episodic: "最近压力有点大"
        #   relation: (alice)-[works_at]->(Google)

        # 第二轮对话（几天后）— agent 能"记住"之前的对话
        reply2 = await agent.chat("alice", "有什么减压的建议吗？")
        print(f"Agent: {reply2}")

        # 定期生成洞察（可选，如每天晚上或每 100 条消息）
        result = await nm.reflect(user_id="alice")
        print(f"生成了 {result['insights_generated']} 条洞察")
```

**关键点**：
1. **实时提取**：`auto_extract=True` 让每次 `add_message` 都立即提取记忆（像 mem0）
2. **召回记忆**：每次对话前用 `recall()` 找出相关记忆
3. **注入 prompt**：将记忆作为 context 注入到 LLM 的 system prompt
4. **生成洞察**：定期调用 `reflect()` 提炼高层洞察和更新情感画像
5. **持续学习**：agent 随着对话增加，对用户的理解越来越深入

---

## 架构

### 架构概览

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

### 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| **Framework** | Python 3.12+ async | 直接嵌入 agent 程序 |
| **数据库** | PostgreSQL 16 + pgvector | 向量检索 + 结构化存储 |
| **图数据库** | Apache AGE | Cypher 查询语言 |
| **ORM** | SQLAlchemy 2.0 (async) | asyncpg 驱动 |
| **Embedding** | 可插拔 Provider | SiliconFlow / OpenAI |
| **LLM** | 可插拔 Provider | OpenAI / DeepSeek |
| **文件存储** | S3 兼容 | MinIO / AWS S3 / 华为云 OBS |

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

---

## 文档

| 文档 | 说明 |
|------|------|
| **[API 参考](docs/API.md)** | 完整的 Python API 文档（recall, search, extract_memories 等） |
| **[快速开始](docs/GETTING_STARTED.md)** | 10 分钟上手指南 |
| **[架构设计](docs/ARCHITECTURE.md)** | 系统架构、Provider 模式、数据模型 |
| **[使用指南](docs/SDK_GUIDE.md)** | API 用法和代码示例 |
| **[为什么不提供 Web UI](docs/WHY_NO_WEB_UI.md)** | 设计理念和替代方案 |

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

### Phase 2（已完成）

- [x] 情感标注（valence / arousal / label）
- [x] 重要性评分（1-10）
- [x] 三因子检索（relevance × recency × importance）
- [x] 访问追踪（access_count / last_accessed_at）
- [x] 反思机制（从记忆中生成高层洞察）
- [x] 后台任务系统（ExtractionStrategy 自动触发）

### Phase 3（规划中）

- [ ] 基准测试：LoCoMo（ACL 2024，长对话记忆评测，10 组多轮对话 + 1986 个 QA）
- [ ] 基准测试：LongMemEval（ICLR 2025，超长记忆评测，500 个问题，115k~1.5M tokens）
- [ ] 自然遗忘（主动记忆清理/归档机制）
- [ ] 多模态 embedding（图片、音频）
- [ ] 分布式部署支持

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
