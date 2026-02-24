# NeuroMemory

**AI Agent 多层记忆框架**

基于 PostgreSQL 构建的 Python 记忆库，为 AI agent 提供开箱即用的多层记忆。利用 PostgreSQL 生态 pgvector 向量检索、pg_search 全文检索、图检索、KV 检索等能力实现混合记忆检索。

- `add_message()` 自动提取四种记忆：**Fact**（持久事实）、**Episode**（带时间戳的情景记忆）、**Graph**（实体关系图谱）、**UserProfile**（用户画像）
- `reflect()` 自动周期性反思，从多轮对话中自动提取 **Insight**（用户洞察，如行为模式、情感画像）
- `recall()` 将多层记忆融合排序后返回，零额外代码组装进 prompt

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

> 各框架使用不同的 Judge LLM，分数不完全可比。详见 [LoCoMo 优化历程](https://github.com/MatrixDriver/NeuroMemory/blob/master/evaluation/history/OPTIMIZATION_HISTORY.md)。

---

## 文档

| 文档 | 说明 |
|------|------|
| **[API 参考](https://github.com/MatrixDriver/NeuroMemory/blob/master/docs/API.md)** | 完整的 Python API 文档（add_message, recall, reflect 等） |
| **[快速开始](https://github.com/MatrixDriver/NeuroMemory/blob/master/docs/GETTING_STARTED.md)** | 10 分钟上手指南 |
| **[架构设计](https://github.com/MatrixDriver/NeuroMemory/blob/master/docs/ARCHITECTURE.md)** | 系统架构、Provider 模式、数据模型、情感架构 |
| **[使用指南](https://github.com/MatrixDriver/NeuroMemory/blob/master/docs/SDK_GUIDE.md)** | API 用法、代码示例、Prompt 组装最佳实践 |
| **[为什么不提供 Web UI](https://github.com/MatrixDriver/NeuroMemory/blob/master/docs/WHY_NO_WEB_UI.md)** | 设计理念和替代方案 |
| **[LoCoMo 优化历程](https://github.com/MatrixDriver/NeuroMemory/blob/master/evaluation/history/OPTIMIZATION_HISTORY.md)** | 基准测试迭代记录（0.125 → 0.802，+541%） |

---

## 安装

### 方式 1: 从 PyPI 安装（推荐）

```bash
# 基础安装（包含核心功能）
pip install neuromemory

# 或安装所有可选依赖（推荐）
pip install neuromemory[all]
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

### 3. LLM API Key（必需，用于自动提取记忆和反思）

- [OpenAI](https://platform.openai.com/) 或 [DeepSeek](https://platform.deepseek.com/)

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
        llm=OpenAILLM(api_key="your-openai-key"),  # 必需，用于自动提取记忆
        auto_extract=True,  # 默认启用，像 mem0 那样实时提取记忆
    ) as nm:
        # 1. 存储对话消息 → 自动提取记忆（facts/episodes/relations）
        await nm.conversations.add_message(
            user_id="alice", role="user",
            content="I work at ABC Company as a software engineer"
        )
        # → 后台自动提取：fact: "在 ABC Company 工作", relation: (alice)-[works_at]->(ABC Company)

        # 2. 多因子检索（cosine 相关性 + 时效性 + 重要性）
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

**召回记忆（recall）**：
- `await nm.recall(user_id, query)` — cosine 相似度为主信号，时效性和重要性为加成，找出最匹配的记忆
- 在对话中使用：让 agent 能"想起"相关的历史信息来回应用户

**生成洞察（reflect）**（可选，定期调用）：
- `await nm.reflect(user_id)` — 高层记忆分析：
  1. **提炼洞察**：从已提取的记忆生成高层理解（行为模式、阶段总结）
  2. **更新画像**：整合情感数据，更新用户情感画像
- 让记忆从"事实"升华为"洞察"

> `add_message()` 默认 `auto_extract=True`，每次调用自动提取记忆。`reflect()` 专注于生成 Insight 和更新情感画像，不处理基础记忆提取。

**逻辑关系**：
```
对话进行中 → 存储消息 (add_message) → 自动提取记忆
     ↓
agent 需要上下文 → 召回记忆 (recall)
     ↓
定期分析 → 生成洞察 (reflect) → 洞察 + 情感画像
```

---

## 核心特性

### 记忆分类

NeuroMemory 提供 7 种记忆类型，每种有不同的存储和获取方式：

| <nobr>记忆类型</nobr> | 存储方式 | 底层存储 | 获取方式 | 示例 |
|---------|---------|---------|---------|------|
| <nobr>**事实 Fact**</nobr> | Embedding + Graph | pgvector + 关系表 | `nm.recall(user_id, query)` | "在 Google 工作" |
| <nobr>**情景 Episode**</nobr> | Embedding | pgvector | `nm.recall(user_id, query)` | "昨天面试很紧张" |
| <nobr>**关系 Relation**</nobr> | Graph Store | PostgreSQL 关系表 | `nm.graph.get_neighbors(user_id, type, id)` | `(user)-[works_at]->(Google)` |
| <nobr>**洞察 Insight**</nobr> | Embedding | pgvector | `nm.recall(user_id, query)` | "用户倾向于晚上工作" |
| <nobr>**情感画像**</nobr> | Table | PostgreSQL | `reflect()` 自动更新 | "容易焦虑，对技术兴奋" |
| <nobr>**偏好 Preference**</nobr> | KV (Profile) | PostgreSQL | `nm.kv.get(user_id, "profile", "preferences")` | `["喜欢喝咖啡", "偏好深色模式"]` |
| <nobr>**通用 General**</nobr> | Embedding | pgvector | `nm.recall(user_id, query)` | 通用记忆 |

### 单一 PostgreSQL 架构优势

NeuroMemory 将所有记忆（向量、图谱、对话、KV、文档、情感画像）存储在**单一 PostgreSQL** 中，而非拼装多个独立数据库。这不是偶然选择，而是刻意的架构决策，带来六大差异化优势：

**1. 联合融合排序** — 图谱与向量结果交叉增强，而非各自为政

`recall()` 中，图三元组不仅提供结构化关系，还参与向量结果的排序：被图三元组覆盖的向量记忆获得加法 boost（双端命中 +0.10，单端命中 +0.04，上限 +0.20），图三元组本身以 `source="graph"` 进入统一的 `merged` 列表。竞品（mem0、graphiti）的图和向量存储在不同数据库中，无法实现这种交叉增强。

**2. 事务一致性 + 数据治理** — 单库原子操作，零数据不一致风险

`delete_user_data()` 在一个数据库事务内原子删除 8 张表的用户数据；`export_user_data()` 在一个快照内导出完整用户画像。竞品需要跨 3-4 个数据库协调删除/导出，任何一个库失败都会造成数据不一致。对于 GDPR/合规场景，单库事务意味着"删除即彻底删除"，无需担心残留。

**3. 时间旅行查询** — 记忆版本化与时间点回溯

利用 PostgreSQL 原生能力实现记忆版本化：查询某个时间点的记忆快照、回滚错误更新。这在多库架构中几乎不可能实现——你无法对 Redis 缓存、Neo4j 图谱、Qdrant 向量同时做时间点快照。

**4. 跨类型记忆分析** — 让开发者获得记忆系统的可观测性

`entity_profile()` 通过 SQL JOIN 跨事实记忆、图谱关系、对话历史三种来源，构建一个实体的完整画像和时间线；`stats()` 提供按类型、按周的记忆分布统计；`cold_memories()` 发现长期未访问的记忆。这些分析能力让 agent 开发者能够观测和诊断记忆系统的健康状况，而不是把它当成黑盒。

**5. 安全与用户隔离** — 框架级强制隔离 + 集中式数据治理

NeuroMemory 的所有 API 都强制要求 `user_id` 参数，框架层面保证每个查询都包含 `WHERE user_id = :uid` 过滤——开发者无法绕过隔离边界。所有数据存储在单一 PostgreSQL 中，可统一应用备份策略、审计日志和访问控制，数据治理只需管理一个数据库，而非 3-4 个不同技术栈的数据库。

**6. 部署极简** — 一个 PostgreSQL 搞定一切

| 框架 | 需要的存储组件 | 部署复杂度 |
|------|-------------|-----------|
| **NeuroMemory** | PostgreSQL（含 pgvector + pg_search） | ⭐ 一个容器 |
| Mem0 | PostgreSQL + Qdrant + Neo4j | 3 个独立服务 |
| MemOS | PostgreSQL + Redis + Qdrant + Neo4j | 4 个独立服务 |
| graphiti | PostgreSQL + Neo4j + 向量数据库 | 3+ 个独立服务 |

开发者只需 `docker compose up -d db` 即可拥有完整的记忆存储——向量检索、全文检索、图查询、KV 存储全部内置。生产环境只需一个托管 PostgreSQL（如 AWS RDS、Supabase），无需额外运维 Redis、Neo4j、Qdrant 等专用数据库。

### LLM 驱动的记忆提取与反思

- **提取**：`add_message()` 自动从对话中识别事实、事件、关系，附带情感标注（valence/arousal/label）和重要性评分（1-10），偏好存入用户画像
- **反思** (`reflect`)：定期从近期记忆提炼高层洞察（行为模式、阶段总结），更新情感画像
- **访问追踪**：自动记录 access_count 和 last_accessed_at，符合 ACT-R 记忆模型

理论基础：Generative Agents (Park 2023) 的 Reflection 机制 + LeDoux 情感标记 + Ebbinghaus 遗忘曲线 + ACT-R 记忆模型。

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
- [x] 多因子检索（cosine similarity + recency bonus + importance bonus）
- [x] 访问追踪（access_count / last_accessed_at）
- [x] 反思机制（从记忆中生成高层洞察）
- [x] 后台任务系统（ExtractionStrategy 自动触发）
- [x] auto_extract 模式后台自动 reflect（`reflection_interval` 参数）

### Phase 3（进行中）

- [x] 基准测试：[LoCoMo](https://github.com/MatrixDriver/NeuroMemory/blob/master/evaluation/history/OPTIMIZATION_HISTORY.md)（ACL 2024，Judge 0.802，13 轮迭代，+541%）
- [x] 联合融合排序（图三元组覆盖度 boost）
- [x] 事务一致性 API（delete_user_data / export_user_data）
- [x] 时间旅行查询（记忆版本化 + as_of 召回 + rollback）
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
