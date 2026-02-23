# NeuroMemory

**AI Agent 记忆框架**

为 AI agent 开发者提供记忆管理能力。直接在 Python 程序中使用，无需部署服务器。

---

## LoCoMo 基准测试成绩

在 [LoCoMo 长对话记忆基准](https://arxiv.org/abs/2309.11696)（ACL 2024）上的对比成绩（Judge: GPT-4o-mini）：

| 框架 | Single-Hop | Multi-Hop | Open-Dom | Temporal | Overall |
|------|:---:|:---:|:---:|:---:|:---:|
| memU | — | — | — | — | 92.1% |
| Backboard | 89.4% | 75.0% | 91.2% | 91.9% | 90.0% |
| **NeuroMemory** | **87.1%** | **80.9%** | **81.9%** | **71.6%** | **80.2%** |
| MemOS | — | — | — | — | 75.8% |
| Memobase v0.0.37 | 70.9% | 46.9% | 77.2% | 85.1% | 75.8% |
| Zep | 74.1% | 66.0% | 67.7% | 79.8% | 75.1% |
| Letta | — | — | — | — | 74.0% |
| Mem0-Graph | 65.7% | 47.2% | 75.7% | 58.1% | 68.4% |
| Mem0 | 67.1% | 51.2% | 72.9% | 55.5% | 66.9% |
| LangMem | 62.2% | 47.9% | 71.1% | 23.4% | 58.1% |
| OpenAI Memory | 63.8% | 42.9% | 62.3% | 21.7% | 52.9% |

> 各框架使用不同的 Judge LLM，分数不完全可比。详见 [LoCoMo 优化历程](evaluation/history/OPTIMIZATION_HISTORY.md)。

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

### 1. PostgreSQL 18 + pgvector + pg_search（必需）

NeuroMemory 使用 [ParadeDB](https://www.paradedb.com/) 镜像，内置 PostgreSQL 18、pgvector 和 pg_search（BM25 全文检索）。

```bash
# 使用项目提供的 Docker Compose（推荐）
docker compose -f docker-compose.yml up -d db
```

> **pg_search 说明**：pg_search 提供 BM25 关键词检索，与向量检索融合为混合排序（RRF）。若 pg_search 不可用，系统自动降级到 PostgreSQL 内置的 tsvector 全文检索，功能仍可正常使用。

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

> **关键变化**（v0.3.0）：`add_message()` 现在默认自动提取记忆（`auto_extract=True`），无需手动调用 `extract_memories()` 或 `reflect()`。`reflect()` 专注于生成洞察和情感画像，不再提取基础记忆。

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
- **自动模式 + 后台 reflect**：`auto_extract=True, reflection_interval=10`，每 10 次提取后自动后台 reflect，无阻塞
- **手动模式**：`auto_extract=False`，手动调用 `extract_memories()`
- **策略模式**：`auto_extract=False` + `ExtractionStrategy(message_interval=10)`，每 10 条消息触发

---

## 核心特性

### 记忆分类

NeuroMemory 提供 7 种记忆类型，每种有不同的存储和获取方式：

| 记忆类型 | 存储方式 | 底层存储 | 获取方式 | 示例 |
|---------|---------|---------|---------|------|
| **事实** | Embedding + Graph | pgvector + 关系表 | `nm.recall(user_id, query)` | "在 Google 工作" |
| **情景** | Embedding | pgvector | `nm.recall(user_id, query)` | "昨天面试很紧张" |
| **关系** | Graph Store | PostgreSQL 关系表 | `nm.graph.get_neighbors(user_id, type, id)` | `(user)-[works_at]->(Google)` |
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
| 知识图谱 | ✅ 关系表图谱（无 Cypher 依赖） | 🔶 简单图 | 🔶 LangGraph |
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

### 后台 reflect 自动配置（推荐）

`auto_extract=True` 模式下，通过 `reflection_interval` 参数让 reflect 完全自动化，不阻塞任何对话流程：

```python
nm = NeuroMemory(
    ...,
    auto_extract=True,           # 每条消息自动提取记忆（默认）
    reflection_interval=10,      # 每 10 次提取后，后台自动 reflect()（0 = 禁用）
    llm=OpenAILLM(api_key="..."),
)
```

- `reflection_interval=10`：用户每说 10 句话，后台自动运行一次 reflect，生成洞察
- reflect 使用 `asyncio.create_task()`，**完全不阻塞** `add_message()` 的响应
- reflect 生成的 `insight` 自动进入 recall() 的向量检索，下次对话立即可用

### 策略配置（ExtractionStrategy，高级用法）

需要按会话/闲置时间触发时使用：

```python
from neuromemory import ExtractionStrategy

nm = NeuroMemory(
    ...,
    auto_extract=False,
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
- **实时对话**（推荐）：`auto_extract=True, reflection_interval=10`，最简单
- **精细控制**：`ExtractionStrategy(message_interval=10, reflection_interval=50)`
- **批处理**（每日总结）：`auto_extract=False, on_session_close=True`，手动调用 `reflect()`

---

## 如何用 recall() 组装 Prompt（最佳实践）

> 可运行的完整示例见 **[example/](example/)**，支持终端交互、命令查询、自动记忆提取。

这是使用 NeuroMemory 最关键的一步——**如何把 recall() 的结果变成高质量的 LLM 上下文**。正确组装 prompt 能充分利用 NeuroMemory 的全部能力：三因子检索、图谱关系、用户画像、情感洞察。

### recall() 返回的完整结构

```python
result = await nm.recall(user_id="alice", query=user_input, limit=10)

# result 包含以下字段：
result["merged"]               # ⭐ 主要使用：vector + conversation 去重合并，已按评分排序
result["user_profile"]         # ⭐ 用户画像：occupation, interests, identity 等
result["graph_context"]        # ⭐ 图谱三元组文本：["alice → WORKS_AT → google", ...]
result["vector_results"]       # 提取的记忆（fact/episodic/insight），含评分
result["conversation_results"] # 原始对话片段，保留了日期细节
result["graph_results"]        # 图谱原始三元组
```

**merged 中每条记忆的关键字段**：
```python
{
    "content": "[2025-03-01 | sentiment: positive] 在 Google 工作",
    "source": "vector",          # "vector" 或 "conversation"
    "memory_type": "fact",       # fact / episodic / insight
    "score": 0.646,              # 综合评分（recall 三因子）
    "metadata": {
        "importance": 8,         # 重要性 (1-10)
        "emotion": {"label": "满足", "valence": 0.6}
    }
}
```

### 推荐的 Prompt 组装模板

```python
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

    # 2. merged 按类型分层，提取最相关的记忆
    merged = recall_result.get("merged", [])
    facts     = [m for m in merged if m.get("memory_type") == "fact"][:3]
    episodes  = [m for m in merged if m.get("memory_type") == "episodic"][:2]
    insights  = [m for m in merged if m.get("memory_type") == "insight"][:2]
    # 其余高分记忆（对话片段等）
    others    = [m for m in merged
                 if m.get("memory_type") not in ("fact", "episodic", "insight")][:2]

    def fmt(items):
        return "\n".join(f"- {m['content']}" for m in items) or "暂无"

    # 3. 图谱关系 → 结构化事实，补充向量检索的盲区
    graph_lines = recall_result.get("graph_context", [])[:5]
    graph_text = "\n".join(f"- {g}" for g in graph_lines) or "暂无"

    return f"""你是一个有长期记忆的 AI 助手，能根据对用户的了解提供个性化回复。

## 用户画像
{profile_text}

## 关于当前话题，你记得的事实
{fmt(facts)}

## 相关经历和情景
{fmt(episodes)}

## 对用户的深层理解（洞察）
{fmt(insights)}

## 结构化关系
{graph_text}

## 其他相关记忆
{fmt(others)}

---
请根据以上记忆自然地回应用户，不要逐条引用记忆，而是像一个真正了解他的朋友那样对话。
如果记忆与当前问题不相关，忽略它们即可。"""
```

### 完整 Agent 实现

```python
import asyncio
from neuromemory import NeuroMemory, SiliconFlowEmbedding, OpenAILLM
from openai import AsyncOpenAI

class MemoryAgent:
    def __init__(self, nm: NeuroMemory, openai_client: AsyncOpenAI):
        self.nm = nm
        self.llm = openai_client

    async def chat(self, user_id: str, user_input: str) -> str:
        # 1. 存储用户消息（后台自动提取记忆，不阻塞）
        await self.nm.conversations.add_message(
            user_id=user_id, role="user", content=user_input
        )

        # 2. 召回相关记忆（一次 recall 获取所有上下文）
        recall_result = await self.nm.recall(user_id=user_id, query=user_input, limit=10)

        # 3. 组装 system prompt
        system_prompt = build_system_prompt(recall_result, user_input)

        # 4. 调用 LLM
        response = await self.llm.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ]
        )
        reply = response.choices[0].message.content

        # 5. 存储 assistant 回复
        await self.nm.conversations.add_message(
            user_id=user_id, role="assistant", content=reply
        )
        return reply


async def main():
    async with NeuroMemory(
        database_url="postgresql+asyncpg://neuromemory:neuromemory@localhost:5432/neuromemory",
        embedding=SiliconFlowEmbedding(api_key="..."),
        llm=OpenAILLM(api_key="..."),
        auto_extract=True,        # 每条消息自动提取记忆
        reflection_interval=10,   # 每 10 次提取后后台自动 reflect，生成洞察
    ) as nm:
        agent = MemoryAgent(nm, AsyncOpenAI(api_key="..."))

        reply = await agent.chat("alice", "我在 Google 工作，做后端开发，最近压力很大")
        print(f"Agent: {reply}")
        # → 自动提取：fact "在 Google 工作"，episodic "最近压力很大"
        # → 图谱关系：(alice)-[WORKS_AT]->(google)

        reply = await agent.chat("alice", "有什么减压的建议吗？")
        print(f"Agent: {reply}")
        # → recall 返回"最近压力很大"的情景记忆和画像，agent 给出个性化建议
```

### 组装 Prompt 的核心原则

| 原则 | 说明 |
|------|------|
| **一次 recall，完整上下文** | 一次 `recall()` 已包含 merged、profile、graph，无需额外查询 |
| **profile 放 system prompt** | 职业、兴趣等稳定画像每次都要注入，是 agent 个性化的基础 |
| **merged 按类型分层** | fact（事实）→ episodic（经历）→ insight（洞察）→ 其他，优先级递减 |
| **graph_context 补充结构化知识** | 向量检索可能遗漏"alice 在 Google 工作"这类关系，图谱能补充 |
| **insight 无需单独 search** | `reflection_interval` 开启后，insight 自动进入 merged，无需额外调用 |
| **token 预算控制** | 每类记忆取 2-3 条，总记忆上下文建议 300-500 tokens |
| **自然注入，不逐条引用** | system prompt 结尾提示 LLM"像朋友一样对话"，避免机械引用 |

---

## 如何用 recall() 组装 Prompt（最佳实践）

> 可运行的完整示例见 **[example/](example/)**，支持终端交互、命令查询、自动记忆提取。

这是使用 NeuroMemory 最关键的一步——**如何把 recall() 的结果变成高质量的 LLM 上下文**。正确组装 prompt 能充分利用 NeuroMemory 的全部能力：三因子检索、图谱关系、用户画像、情感洞察。

### recall() 返回的完整结构

```python
result = await nm.recall(user_id="alice", query=user_input, limit=10)

# result 包含以下字段：
result["merged"]               # ⭐ 主要使用：vector + conversation 去重合并，已按评分排序
result["user_profile"]         # ⭐ 用户画像：occupation, interests, identity 等
result["graph_context"]        # ⭐ 图谱三元组文本：["alice → WORKS_AT → google", ...]
result["vector_results"]       # 提取的记忆（fact/episodic/insight），含评分
result["conversation_results"] # 原始对话片段，保留了日期细节
result["graph_results"]        # 图谱原始三元组
```

**merged 中每条记忆的关键字段**：
```python
{
    "content": "[2025-03-01 | sentiment: positive] 在 Google 工作",
    "source": "vector",          # "vector" 或 "conversation"
    "memory_type": "fact",       # fact / episodic / insight
    "score": 0.646,              # 综合评分（recall 三因子）
    "metadata": {
        "importance": 8,         # 重要性 (1-10)
        "emotion": {"label": "满足", "valence": 0.6}
    }
}
```

### 推荐的 Prompt 组装模板

```python
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

    # 2. merged 按类型分层，提取最相关的记忆
    merged = recall_result.get("merged", [])
    facts     = [m for m in merged if m.get("memory_type") == "fact"][:3]
    episodes  = [m for m in merged if m.get("memory_type") == "episodic"][:2]
    insights  = [m for m in merged if m.get("memory_type") == "insight"][:2]
    # 其余高分记忆（对话片段等）
    others    = [m for m in merged
                 if m.get("memory_type") not in ("fact", "episodic", "insight")][:2]

    def fmt(items):
        return "\n".join(f"- {m['content']}" for m in items) or "暂无"

    # 3. 图谱关系 → 结构化事实，补充向量检索的盲区
    graph_lines = recall_result.get("graph_context", [])[:5]
    graph_text = "\n".join(f"- {g}" for g in graph_lines) or "暂无"

    return f"""你是一个有长期记忆的 AI 助手，能根据对用户的了解提供个性化回复。

## 用户画像
{profile_text}

## 关于当前话题，你记得的事实
{fmt(facts)}

## 相关经历和情景
{fmt(episodes)}

## 对用户的深层理解（洞察）
{fmt(insights)}

## 结构化关系
{graph_text}

## 其他相关记忆
{fmt(others)}

---
请根据以上记忆自然地回应用户，不要逐条引用记忆，而是像一个真正了解他的朋友那样对话。
如果记忆与当前问题不相关，忽略它们即可。"""
```

### 完整 Agent 实现

```python
import asyncio
from neuromemory import NeuroMemory, SiliconFlowEmbedding, OpenAILLM
from openai import AsyncOpenAI

class MemoryAgent:
    def __init__(self, nm: NeuroMemory, openai_client: AsyncOpenAI):
        self.nm = nm
        self.llm = openai_client

    async def chat(self, user_id: str, user_input: str) -> str:
        # 1. 存储用户消息（后台自动提取记忆，不阻塞）
        await self.nm.conversations.add_message(
            user_id=user_id, role="user", content=user_input
        )

        # 2. 召回相关记忆（一次 recall 获取所有上下文）
        recall_result = await self.nm.recall(user_id=user_id, query=user_input, limit=10)

        # 3. 组装 system prompt
        system_prompt = build_system_prompt(recall_result, user_input)

        # 4. 调用 LLM
        response = await self.llm.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ]
        )
        reply = response.choices[0].message.content

        # 5. 存储 assistant 回复
        await self.nm.conversations.add_message(
            user_id=user_id, role="assistant", content=reply
        )
        return reply


async def main():
    async with NeuroMemory(
        database_url="postgresql+asyncpg://neuromemory:neuromemory@localhost:5432/neuromemory",
        embedding=SiliconFlowEmbedding(api_key="..."),
        llm=OpenAILLM(api_key="..."),
        auto_extract=True,        # 每条消息自动提取记忆
        reflection_interval=10,   # 每 10 次提取后后台自动 reflect，生成洞察
    ) as nm:
        agent = MemoryAgent(nm, AsyncOpenAI(api_key="..."))

        reply = await agent.chat("alice", "我在 Google 工作，做后端开发，最近压力很大")
        print(f"Agent: {reply}")
        # → 自动提取：fact "在 Google 工作"，episodic "最近压力很大"
        # → 图谱关系：(alice)-[WORKS_AT]->(google)

        reply = await agent.chat("alice", "有什么减压的建议吗？")
        print(f"Agent: {reply}")
        # → recall 返回"最近压力很大"的情景记忆和画像，agent 给出个性化建议
```

### 组装 Prompt 的核心原则

| 原则 | 说明 |
|------|------|
| **一次 recall，完整上下文** | 一次 `recall()` 已包含 merged、profile、graph，无需额外查询 |
| **profile 放 system prompt** | 职业、兴趣等稳定画像每次都要注入，是 agent 个性化的基础 |
| **merged 按类型分层** | fact（事实）→ episodic（经历）→ insight（洞察）→ 其他，优先级递减 |
| **graph_context 补充结构化知识** | 向量检索可能遗漏"alice 在 Google 工作"这类关系，图谱能补充 |
| **insight 无需单独 search** | `reflection_interval` 开启后，insight 自动进入 merged，无需额外调用 |
| **token 预算控制** | 每类记忆取 2-3 条，总记忆上下文建议 300-500 tokens |
| **自然注入，不逐条引用** | system prompt 结尾提示 LLM"像朋友一样对话"，避免机械引用 |

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
│  │  PostgreSQL + pgvector │ MinIO/S3 (可选)               │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| **Framework** | Python 3.12+ async | 直接嵌入 agent 程序 |
| **数据库** | PostgreSQL 18 + pgvector + pg_search | 向量检索 + BM25 混合排序 (ParadeDB) |
| **图数据库** | PostgreSQL 关系表 | 无 Cypher 依赖 |
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
| **[LoCoMo 优化历程](evaluation/history/OPTIMIZATION_HISTORY.md)** | 基准测试迭代记录（0.125 → 0.802，+541%） |

---

## 路线图

### Phase 1（已完成）

- [x] PostgreSQL + pgvector 统一存储
- [x] 向量语义检索
- [x] 时间范围查询和时间线聚合
- [x] KV 存储
- [x] 对话管理
- [x] 文件上传和文本提取
- [x] 图数据库（关系表实现，无 AGE 依赖）
- [x] LLM 记忆分类提取
- [x] 可插拔 Provider（Embedding/LLM/Storage）

### Phase 2（已完成）

- [x] 情感标注（valence / arousal / label）
- [x] 重要性评分（1-10）
- [x] 三因子检索（relevance × recency × importance）
- [x] 访问追踪（access_count / last_accessed_at）
- [x] 反思机制（从记忆中生成高层洞察）
- [x] 后台任务系统（ExtractionStrategy 自动触发）
- [x] auto_extract 模式后台自动 reflect（`reflection_interval` 参数）

### Phase 3（规划中）

- [x] 基准测试：[LoCoMo](evaluation/history/OPTIMIZATION_HISTORY.md)（ACL 2024，Judge 0.802，13 轮迭代，+541%）
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
