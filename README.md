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
docker compose -f docker-compose.v2.yml up -d db

# 或使用官方镜像
docker run -d -p 5432:5432 \
  -e POSTGRES_USER=neuromemory \
  -e POSTGRES_PASSWORD=neuromemory \
  -e POSTGRES_DB=neuromemory \
  ankane/pgvector:pg16
```

### 2. API Keys（必需）

- **Embedding**: [SiliconFlow](https://siliconflow.cn/) 或 [OpenAI](https://platform.openai.com/)
- **LLM**: [OpenAI](https://platform.openai.com/) 或 [DeepSeek](https://platform.deepseek.com/)（用于自动提取记忆）

### 3. MinIO/S3（可选，仅用于文件存储）

```bash
docker compose -f docker-compose.v2.yml up -d minio
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
    ) as nm:
        # 存储对话消息（推荐方式）
        await nm.conversations.add_message(
            user_id="alice",
            role="user",
            content="I work at ABC Company as a software engineer"
        )

        # 手动触发记忆提取
        await nm.extract_memories(user_id="alice")

        # 三因子检索（相关性 × 时效性 × 重要性）
        result = await nm.recall(user_id="alice", query="Where does Alice work?")
        for r in result["merged"]:
            print(f"[{r['score']:.2f}] {r['content']}")

asyncio.run(main())
```

```python
import asyncio
from neuromemory import NeuroMemory, SiliconFlowEmbedding, OpenAILLM

async def main():
    async with NeuroMemory(
        database_url="postgresql+asyncpg://neuromemory:neuromemory@localhost:5432/neuromemory",
        embedding=SiliconFlowEmbedding(api_key="your-key"),
        llm=OpenAILLM(api_key="your-openai-key"),  # 用于自动提取记忆
    ) as nm:
        # 存储对话消息（推荐方式）
        # NeuroMemory 会按照 ExtractionStrategy 策略自动提取记忆
        # 如需手动指定记忆类型，可使用 nm.add_memory(user_id, content, memory_type="fact")
        await nm.conversations.add_message(
            user_id="alice",
            role="user",
            content="I work at ABC Company as a software engineer"
        )

        # 手动触发记忆提取（可选）
        # 系统会按策略自动提取，这里手动调用是为了演示
        # 提取后会自动分类为 fact、preference、relation 等类型
        await nm.extract_memories(user_id="alice")

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
| **混合检索** | `nm.recall()` | 三因子向量检索 (relevance × recency × importance) + 图实体检索，合并去重 |
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
| **混合检索** | Generative Agents + Ebbinghaus | 三因子向量 (`relevance × recency × importance`) + 图实体遍历，高 arousal 记忆衰减更慢 |
| **访问追踪** | ACT-R 记忆模型 | 自动记录 access_count 和 last_accessed_at |
| **反思机制** | Generative Agents Reflection | 定期从近期记忆提炼高层洞察（pattern/summary），更新情感画像 |

#### 为什么用混合检索（三因子 + 图）

`recall()` 不是简单的向量检索，而是**混合检索**，结合了三因子评分和图遍历：

**1. 三因子向量检索**

```python
Score = relevance × recency × importance

# 相关性 (0-1)：语义相似度
relevance = 1 - cosine_distance

# 时效性 (0-1)：指数衰减，情感唤醒减缓遗忘
recency = e^(-t / decay_rate × (1 + arousal × 0.5))

# 重要性 (0.1-1.0)：LLM 评估或人工标注
importance = metadata.importance / 10
```

**为什么采用三因子？**

| 对比维度 | 纯向量检索 | 三因子检索 |
|---------|-----------|-----------|
| **时间感知** | ❌ 1 年前的记忆和昨天的权重相同 | ✅ 指数衰减，符合 Ebbinghaus 遗忘曲线 |
| **情感影响** | ❌ 不考虑情感强度 | ✅ 高 arousal 记忆（面试、分手）衰减慢 50% |
| **重要性** | ❌ 琐事（天气）和大事（生日）同等对待 | ✅ 重要事件优先级更高 |
| **适用场景** | 静态知识库 | 长期陪伴型 agent |

**实际案例**：

用户问："我在哪工作？"

| 记忆内容 | 时间 | 纯向量 | 三因子 | 应该返回 |
|---------|------|--------|--------|---------|
| "我在 Google 工作" | 1 年前 | 0.95 | 0.008 | ❌ 已过时 |
| "上周从 Google 离职了" | 7 天前 | 0.85 | 0.67 | ✅ 最新且重要 |

纯向量会返回过时信息，三因子优先返回最新相关记忆。

**2. 图实体检索**

从知识图谱中查找实体相关的 facts：
- 查询中提到的实体（如 "Google"）
- 用户自身相关的实体关系

**3. 合并策略（recall() 实现）**

`recall()` 自动执行混合检索并返回三部分结果：

```python
result = await nm.recall(user_id="alice", query="我在哪工作？", limit=10)

# 返回格式
{
    "vector_results": [...],   # 三因子检索结果（带 score）
    "graph_results": [...],    # 图实体检索结果
    "merged": [...],           # 去重后的综合结果（推荐使用）
}

# 使用示例
for memory in result["merged"]:
    print(f"[{memory.get('source')}] {memory['content']}")
    # 输出: [vector] 上周从 Google 离职了
    #      [graph] Alice 在 Mountain View 工作过
```

**实现流程**：

```python
# 步骤 1: 三因子向量检索
vector_results = await scored_search(
    user_id, query, limit,
    # 自动计算：relevance × recency × importance
)

# 步骤 2: 图实体检索（自动并行）
graph_results = []
if graph_enabled:
    # 2.1 查询中提到的实体（如 "Google"）
    entity_facts = await find_entity_facts(user_id, query, limit)
    # 2.2 用户自身相关的关系
    user_facts = await find_entity_facts(user_id, user_id, limit)
    graph_results = entity_facts + user_facts

# 步骤 3: 按 content 去重合并
seen_contents = set()
merged = []
for r in vector_results:
    if r['content'] not in seen_contents:
        merged.append({**r, "source": "vector"})
for r in graph_results:
    if r['content'] not in seen_contents:
        merged.append({**r, "source": "graph"})

return {"vector_results": ..., "graph_results": ..., "merged": merged[:limit]}
```

**为什么需要图检索？**
- 向量检索擅长**语义匹配**："在 Google 工作" ≈ "工作地点"
- 图检索擅长**结构化关系**：(alice)-[works_at]->(Google)-[located_in]->(Mountain View)
- 两者互补，提供更全面的记忆召回
- **去重机制**：避免同一记忆被重复返回

**学术基础**：
- **Generative Agents** (Stanford, 2023)：三因子检索
- **ACT-R 认知架构**：基础激活 = log(Σ t^-d)
- 已在虚拟小镇 Smallville 实验中验证有效性

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

#### 两种记忆管理方式

NeuroMemory 提供两种方式管理记忆，适用于不同场景：

**方式一：会话驱动（推荐用于聊天机器人）**
```python
# 1. 存储原始对话消息
await nm.conversations.add_message(user_id="alice", role="user", content="我在 Google 工作")
await nm.conversations.add_message(user_id="alice", role="assistant", content="了解！")

# 2. 自动提取结构化记忆（LLM 分析对话内容）
await nm.extract_memories(user_id="alice")
# 提取结果：fact="在 Google 工作", preference={"company": "Google"}, relation=(alice)-[works_at]->(Google)

# 3. 定期整理记忆
await nm.reflect(user_id="alice")  # 会自动处理未提取的对话
```

**方式二：直接添加记忆（推荐用于知识库导入）**
```python
# 直接添加结构化记忆，跳过对话存储
await nm.add_memory(
    user_id="alice",
    content="在 Google 工作",
    memory_type="fact",
    metadata={"source": "user_profile", "importance": 8}
)
```

**区别与选择**：

| 维度 | 会话驱动 (conversations) | 直接添加 (add_memory) |
|------|------------------------|---------------------|
| **数据源** | 原始对话消息（user/assistant） | 已知的结构化信息 |
| **处理方式** | 需要 LLM 提取 → 自动分类 | 直接存储，无需 LLM |
| **适用场景** | 聊天机器人、对话 agent | 知识库导入、手动管理 |
| **优势** | 保留完整对话上下文，自动情感标注 | 精确控制，性能更高 |
| **成本** | 需要 LLM API 调用 | 无 LLM 成本 |

**最佳实践**：
- 聊天场景：用 `conversations.add_message()` + `ExtractionStrategy` 自动管理
- 批量导入：用 `add_memory()` 直接添加已知事实
- 混合使用：对话用 conversations，系统信息用 add_memory

---

#### 核心操作流程

NeuroMemory 的核心使用流程围绕三个关键操作：

**插入记忆**：
- 会话驱动：`conversations.add_message()` → `extract_memories()`（自动分类，需要 LLM）
- 直接添加：`add_memory(user_id, content, memory_type)`（手动指定类型）
- 目的：将用户的对话、事件、知识转化为结构化记忆存储

**召回记忆（recall）**：
- 智能检索：`await nm.recall(user_id, query)`
- 目的：根据查询语义，综合考虑相关性、时效性、重要性，找出最匹配的记忆
- 在对话中使用：让 agent 能"想起"相关的历史信息来回应用户

**整理记忆（reflect）**：
- 全面整理：`await nm.reflect(user_id)`
- 三步操作流程：
  1. **查漏补缺**：重新提取未处理的对话，补充遗漏的事实、偏好、关系
  2. **提炼洞察**：从所有近期记忆中生成高层理解（行为模式、阶段总结）
  3. **更新画像**：整合情感数据，更新用户的近期状态和长期特质
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

#### 2. 完整 Agent 示例

以下是一个带记忆的聊天 agent 完整实现：

```python
from neuromemory import NeuroMemory, SiliconFlowEmbedding, OpenAILLM, ExtractionStrategy
from openai import AsyncOpenAI

class MemoryAgent:
    def __init__(self, nm: NeuroMemory, openai_client: AsyncOpenAI):
        self.nm = nm
        self.llm = openai_client

    async def chat(self, user_id: str, user_input: str) -> str:
        """处理用户输入，返回 agent 回复"""

        # === 步骤 1：存储用户消息 ===
        await self.nm.conversations.add_message(
            user_id=user_id,
            role="user",
            content=user_input
        )

        # === 步骤 2：召回相关记忆 ===
        recall_result = await self.nm.recall(user_id=user_id, query=user_input, limit=5)
        memories = recall_result["merged"]

        # 获取用户偏好
        language = await self.nm.kv.get("preferences", user_id, "language") or "zh-CN"

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

        请根据这些记忆和理解，以朋友的口吻自然地回应用户：
        1. 如果记忆中有相关信息，自然地提及它们，展现你记得 ta 说过的话
        2. 利用洞察来理解用户的性格、习惯、情感状态
        3. 如果用户情绪低落（根据历史记忆判断），给予关心和支持
        4. 避免机械地复述记忆，要像真正的朋友一样对话"""

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
        extraction_strategy=ExtractionStrategy(
            message_interval=10,       # 每 10 条消息自动提取记忆
            reflection_interval=50,    # 每 50 次提取后自动反思
        )
    ) as nm:
        agent = MemoryAgent(nm, AsyncOpenAI(api_key="..."))

        # 第一轮对话
        reply1 = await agent.chat("alice", "我在 Google 工作，做后端开发，最近压力有点大")
        print(f"Agent: {reply1}")
        # Agent: "听起来你最近工作挺辛苦的。在 Google 做后端开发一定很有挑战性吧..."

        # 自动提取记忆（达到 message_interval 时触发）
        # 提取结果：
        # - fact: "在 Google 工作", "做后端开发"
        # - episodic: "最近压力有点大" (emotion: {valence: -0.5, label: "压力"})
        # - relation: (alice)-[works_at]->(Google)

        # 第二轮对话（几天后）
        reply2 = await agent.chat("alice", "有什么减压的建议吗？")
        print(f"Agent: {reply2}")
        # Agent: "我记得你在 Google 做后端开发，最近压力挺大的。要不要试试..."
        # ↑ agent 能"记住"之前的对话内容

        # 手动触发反思整理（也可以由 ExtractionStrategy 自动触发）
        result = await nm.reflect(user_id="alice")
        print(f"生成了 {result['insights_generated']} 条洞察")
        # 洞察示例：
        # - pattern: "用户是 Google 的后端工程师，关注技术和工作压力"
        # - summary: "用户近期工作压力较大，寻求减压建议"
        # - emotion_profile: "近期情绪偏焦虑 (valence: -0.5)"
```

**关键点说明**：
1. **召回记忆**：每次对话前，用 `recall()` 找出相关记忆
2. **注入 prompt**：将记忆作为 context 注入到 LLM 的 system prompt
3. **自动提取**：`ExtractionStrategy` 在后台自动提取和整理记忆
4. **持续学习**：agent 随着对话增加，对用户的理解越来越深入

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
| **[API 参考](docs/API.md)** | 完整的 Python API 文档（recall, search, extract_memories 等） |
| **[快速开始](docs/v2/GETTING_STARTED.md)** | 10 分钟上手指南 |
| **[架构设计](docs/v2/ARCHITECTURE.md)** | 系统架构、Provider 模式、数据模型 |
| **[使用指南](docs/v2/SDK_GUIDE.md)** | API 用法和代码示例 |
| **[为什么不提供 Web UI](docs/WHY_NO_WEB_UI.md)** | 设计理念和替代方案 |
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

### Phase 2（已完成）

- [x] 情感标注（valence / arousal / label）
- [x] 重要性评分（1-10）
- [x] 三因子检索（relevance × recency × importance）
- [x] 访问追踪（access_count / last_accessed_at）
- [x] 反思机制（从记忆中生成高层洞察）
- [x] 后台任务系统（ExtractionStrategy 自动触发）

### Phase 3（规划中）

- [ ] 自然遗忘（主动记忆清理/归档机制）
- [ ] 多模态 embedding（图片、音频）
- [ ] 分布式部署支持

---

## 查看和调试记忆

NeuroMemory 是一个 Python 库，不提供 Web 管理界面。记忆的可视化和管理应该由你的 agent 应用程序提供。

**推荐方式**：

```python
# 方式 1: 在 agent 应用中查询并展示
results = await nm.search(user_id="alice", query="工作")
for r in results:
    print(f"{r['content']} (score: {r['score']})")

# 方式 2: Jupyter Notebook（数据分析）
import pandas as pd
results = await nm.search(user_id="alice", query="")
df = pd.DataFrame(results)
df.head()

# 方式 3: 直接查询 PostgreSQL
# psql -U neuromemory -d neuromemory
# SELECT content, memory_type, metadata FROM embeddings WHERE user_id = 'alice';
```

**构建自己的界面**：

如果需要为你的 agent 应用构建管理界面，可以：
- 调用 `nm.search()` / `nm.kv.list()` / `nm.conversations.get_history()` 等 API
- 用任何框架构建 UI（Streamlit、Gradio、Flask、FastAPI + React 等）
- 根据应用场景定制展示方式（聊天界面、数据看板、CLI 工具等）

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
