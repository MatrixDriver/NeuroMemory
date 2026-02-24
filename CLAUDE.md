# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

NeuroMemory (v0.5.1) 是一个 **Python 记忆管理框架**，为 AI agent 开发者提供记忆存储、检索和推理能力。开发者直接 `from neuromemory import NeuroMemory` 在自己程序中使用，无需部署服务器。已发布到 PyPI。

**核心架构**：
- **Python 框架** (`neuromemory/`)：直接在 agent 程序中使用的库
- **可插拔 Provider**：Embedding (SiliconFlow/OpenAI/SentenceTransformer)、LLM (OpenAI/DeepSeek)、Storage (S3/MinIO)
- **PostgreSQL + pgvector + pg_search**：统一存储后端（结构化数据 + 向量检索 + BM25 全文搜索）
- **图存储**：基于关系表（GraphNode/GraphEdge），无 Apache AGE 依赖

**数据隔离**：按 user_id 隔离，所有查询必须包含 user_id 过滤。

## 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| Framework | Python async | 直接嵌入 agent 程序 |
| Database | PostgreSQL + pgvector + pg_search | 向量检索 + BM25 全文搜索 |
| ORM | SQLAlchemy 2.0 (async) | asyncpg 异步驱动 |
| Embedding | 可插拔 (SiliconFlow/OpenAI/SentenceTransformer) | Provider 抽象，1024 维 |
| LLM | 可插拔 (OpenAI/DeepSeek) | 用于记忆提取和反思 |
| Storage | 可插拔 (S3/MinIO) | 文件存储（可选） |
| 图存储 | 关系表 (GraphNode/GraphEdge) | 知识图谱，无 AGE 依赖 |

## 项目结构

```
neuromemory/
  __init__.py              # 公共导出 (NeuroMemory, providers, etc.)
  _core.py                 # NeuroMemory 主类 + Facade 类 (1200+ 行)
  db.py                    # Database 类 (engine, session, init)
  models/
    __init__.py            # _embedding_dims 模块变量
    base.py                # Base, TimestampMixin
    memory.py              # Embedding 模型 (向量存储)
    kv.py                  # KeyValue 模型
    conversation.py        # Conversation, ConversationSession
    document.py            # Document 模型
    graph.py               # GraphNode, GraphEdge, NodeType/EdgeType 枚举
    emotion_profile.py     # EmotionProfile 模型 (情感画像)
  services/
    search.py              # SearchService (混合检索: 向量 + BM25)
    memory.py              # MemoryService (记忆 CRUD + 时间查询)
    memory_extraction.py   # MemoryExtractionService (LLM 提取 facts/episodes)
    reflection.py          # ReflectionService (洞察生成 + 情感画像)
    temporal.py            # TemporalService (时间范围过滤 + 时序记忆)
    conversation.py        # ConversationService (会话管理)
    graph.py               # GraphService (图 CRUD)
    graph_memory.py        # GraphMemoryService (图谱召回)
    kv.py                  # KVService (键值存储)
    files.py               # FileService (文件上传/管理)
    file_processor.py      # 文件验证和文本提取
  providers/
    embedding.py           # ABC EmbeddingProvider
    llm.py                 # ABC LLMProvider
    siliconflow.py         # SiliconFlowEmbedding (BAAI/bge-m3)
    openai_embedding.py    # OpenAIEmbedding
    openai_llm.py          # OpenAILLM (兼容 DeepSeek)
    sentence_transformer.py # SentenceTransformerEmbedding (本地, 可选)
  storage/
    base.py                # ABC ObjectStorage
    s3.py                  # S3Storage (MinIO/AWS/OBS)

tests/                     # 20 个测试文件
  conftest.py              # MockEmbeddingProvider, NeuroMemory fixture
  test_memory_crud.py      # 记忆 CRUD
  test_search.py           # 向量检索
  test_bm25_sanitize.py    # BM25 输入清洗
  test_conversations.py    # 对话管理
  test_conversation_recall.py  # 对话召回
  test_recall.py           # recall() 端到端 (29+ 用例)
  test_recall_emotion.py   # 情感召回
  test_graph.py            # 图 CRUD
  test_graph_memory.py     # 图谱记忆
  test_multi_user_graph.py # 多用户图隔离
  test_memory_time.py      # 时间查询
  test_temporal.py         # 时序记忆
  test_temporal_memory.py  # 时序记忆端到端
  test_reflection.py       # 反思生成
  test_reflect_watermark.py # 反思水位线
  test_memory_extraction.py # LLM 记忆提取
  test_files.py            # 文件管理
  test_kv.py               # KV 存储
  test_transaction_consistency.py  # 事务一致性

evaluation/                # LoCoMo + LongMemEval 基准测试框架
  pipelines/               # 评测 pipeline (locomo.py, longmemeval.py)
  metrics/                 # 评分指标 (token_f1, bleu, llm_judge)
  datasets/                # 数据集加载器
  history/                 # 历史评测结果 (R1-R18)
  results/                 # 评测日志

example/                   # 示例代码
  chat_agent.py            # 完整 AI agent 集成示例

java/                      # Java 实现 (Spring Boot, Maven)

docker/
  postgres-age-vector/     # 自定义 PostgreSQL 镜像 (pgvector + pg_search)

migrations/                # SQL 迁移文件
scripts/                   # 工具脚本 (publish.sh, fix_vector_dims.py)

docker-compose.yml         # PostgreSQL + MinIO
docker-compose-eval.yml    # 评测用 Docker Compose
pyproject.toml             # 包配置 (setuptools, v0.5.1)
```

## 常用命令

```bash
# 启动数据库和 MinIO
docker compose up -d

# 只启动数据库
docker compose up -d db

# 安装开发依赖
uv pip install -e ".[dev]"

# 运行测试（需要 PostgreSQL 运行中）
pytest tests/

# 跳过需要 embedding API 的慢测试
pytest tests/ -m "not slow"

# 构建和发布
bash scripts/publish.sh
```

## 核心 API

```python
from neuromemory import NeuroMemory, SiliconFlowEmbedding, OpenAILLM, S3Storage

async with NeuroMemory(
    database_url="postgresql+asyncpg://neuromemory:neuromemory@localhost:5432/neuromemory",
    embedding=SiliconFlowEmbedding(api_key="..."),
    llm=OpenAILLM(api_key="...", model="deepseek-chat"),  # 必需，用于自动提取和反思
    storage=S3Storage(endpoint="http://localhost:9000"),    # 可选
    auto_extract=True,       # 默认开启，每条 user 消息自动提取记忆
    graph_enabled=False,     # 是否启用图存储
    reflection_interval=20,  # 每 20 条 user 消息后台自动 reflect
) as nm:
    # 对话 → 自动提取 facts/episodes/relations
    await nm.conversations.add_message(user_id="u1", role="user", content="I work at Google")

    # 三因子召回（向量 + 图谱 + 时序，并行执行）
    result = await nm.recall(user_id="u1", query="workplace", include_conversations=False)
    # → {"vector_results": [...], "graph_results": [...], "merged": "..."}

    # 带过滤参数的召回
    result = await nm.recall(user_id="u1", query="workplace",
                             memory_type="fact", created_after=some_datetime)

    # KV 存储
    await nm.kv.set("u1", "config", "language", "zh-CN")

    # 手动触发反思（生成洞察 + 情感画像）
    await nm.reflect(user_id="u1")

    # 图操作 (需要 graph_enabled=True)
    await nm.graph.create_node(node_type=NodeType.PERSON, node_id="u1")
```

## 核心工作流

```
add_message(role="user")
  ├─ 存储到 conversations 表
  ├─ 后台生成 embedding (asyncio.create_task)
  ├─ auto_extract=True → 后台 LLM 提取 facts/episodes/relations
  │    ├─ 存储到 embeddings 表（向量化）
  │    └─ graph_enabled=True → 存储到 graph_nodes/edges 表
  └─ 每 reflection_interval 条消息 → 后台 reflect()

recall(query)
  ├─ 并行获取 (asyncio.gather):
  │    ├─ 向量检索 (pgvector cosine + BM25 RRF)
  │    ├─ 图谱召回 (GraphMemoryService)
  │    └─ 时序过滤 (TemporalService)
  ├─ 合并阶段:
  │    ├─ 图三元组覆盖度 boost (双端+0.5, 单端+0.2, 上限2.0)
  │    ├─ 图三元组 → merged (source="graph")
  │    └─ merged 按 score 降序排序
  └─ 返回结构化结果

reflect()
  ├─ 分析水位线之后新增的 memories
  ├─ LLM 生成行为模式和阶段总结
  ├─ 更新 EmotionProfile
  └─ 推进 last_reflected_at 水位线
```

## 数据库模型

| 模型 | 表名 | 用途 |
|------|------|------|
| Embedding | embeddings | 向量记忆存储 (content + pgvector + memory_type + metadata) |
| Conversation | conversations | 原始对话消息 |
| ConversationSession | conversation_sessions | 会话元数据 |
| KeyValue | key_values | KV 存储 (JSONB value) |
| GraphNode | graph_nodes | 图节点 (NodeType 枚举) |
| GraphEdge | graph_edges | 图边 (EdgeType 枚举) |
| EmotionProfile | emotion_profiles | 用户情感画像 |
| Document | documents | 文档元数据 |

## 环境变量

```bash
DATABASE_URL=postgresql+asyncpg://neuromemory:neuromemory@localhost:5432/neuromemory
SILICONFLOW_API_KEY=...          # Embedding API
EMBEDDING_PROVIDER=siliconflow   # siliconflow | openai | sentence_transformer
EMBEDDING_DIMS=1024              # 默认 1024 (BAAI/bge-m3)
```

## 服务访问

- PostgreSQL: localhost:5432 (用户名: `neuromemory`, 密码: `neuromemory`)
- MinIO: localhost:9000 (Console: localhost:9001)

## 测试

测试需要运行中的 PostgreSQL（`docker compose up -d db`）。

Marker：
- `@pytest.mark.slow`：需要 embedding API（SiliconFlow/OpenAI）
- `@pytest.mark.requires_db`：需要 PostgreSQL

配置：`asyncio_mode = "auto"`，所有测试函数可直接 async def。

## 开发约定

- 数据库操作使用 async SQLAlchemy
- 数据按 user_id 隔离，所有查询必须包含 user_id 过滤
- Provider 通过构造函数注入（不使用全局单例）
- Service 类接收 db session 和 provider 作为构造参数
- Facade 类在 _core.py 中，每次操作开启独立 session
- 后台任务使用 asyncio.create_task()（embedding 生成、记忆提取、反思）
- 不要在 `return` 之后写逻辑（不可达代码）

## 项目定位

NeuroMemory 是一个专注的 Python 库，不提供以下内容：
- Web 管理界面（记忆可视化应由 agent 应用提供）
- HTTP/API 服务器（直接在 Python 代码中使用）
- 独立部署的服务（嵌入到你的 agent 程序中）

## 工程推进流程

过程文件存放于 `rpiv/` 目录（已加入 `.gitignore`，不进版本库）。
