# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

neuromem (v0.8.0) 是一个 **AI 记忆管理框架**，为 AI agent 开发者提供记忆存储、检索和推理能力。已发布到 PyPI。

**三种访问方式**：
- **Python SDK**：`from neuromem import NeuroMemory`，直接嵌入 agent 程序（本仓库 `neuromem/`）
- **Cloud REST API**：`https://api.neuromem.cloud/api/v1/{ingest,recall,digest}`，任意语言 HTTP 调用
- **MCP**：`https://api.neuromem.cloud/mcp/`，兼容 Claude Code/Desktop、Cursor、ChatGPT

**调用链路**：Cloud REST API 和 MCP 均直接调用本仓库的 Python SDK 作为记忆引擎：
```
MCP 客户端 → FastMCP tools (ingest/recall/digest)  ┐
REST 客户端 → FastAPI endpoints                     ├→ neuromem Python SDK → PostgreSQL
Web 控制台 → Next.js → Internal API → FastAPI       ┘
```

**neuromem.cloud 实现**（独立仓库 `neuromem-cloud`）：
- **后端**：FastAPI + FastMCP 2.x（Streamable HTTP），依赖 `neuromem >= 0.8.0`
- **前端**：Next.js 16 + React 19 + Tailwind CSS + shadcn/ui
- **认证**：NextAuth.js（GitHub/Google OAuth）+ API Key（Bearer `nm_sk_*`）
- **多租户**：每个租户独立 PostgreSQL schema（`tenant_{slug}`）
- **智能体**：Agent 实体绑定自定义 ingest/recall/digest 指令，API Key 关联到 Agent

本仓库 `java/` 为 Cloud Server 的早期 Spring Boot 原型，已被 neuromem-cloud 的 FastAPI 实现取代。

**仓库结构**：
- **Python SDK** (`neuromem/`)：核心记忆框架库，可插拔 Provider（Embedding/LLM/Storage）
- **PostgreSQL + pgvector + pg_search**：统一存储后端（结构化数据 + 向量检索 + BM25 全文搜索）
- **图存储**：基于关系表（GraphNode/GraphEdge），无 Apache AGE 依赖
- **Java 早期原型** (`java/`)：已废弃，被 neuromem-cloud 取代

**数据隔离**：Python SDK 按 user_id 隔离；Cloud Server 按 tenant_slug schema + user_id 双层隔离。

## 常用命令

```bash
# 启动开发数据库（端口 5432）
docker compose up -d db

# 启动数据库 + MinIO（文件存储）
docker compose up -d

# 安装开发依赖
uv pip install -e ".[dev]"

# 运行全部测试（需要 PostgreSQL 在端口 5436 运行）
pytest tests/

# 跳过需要 embedding API 的慢测试
pytest tests/ -m "not slow"

# 运行单个测试文件
pytest tests/test_recall.py -v

# 运行单个测试函数
pytest tests/test_recall.py::test_function_name -v

# 构建和发布
bash scripts/publish.sh
```

**重要：测试端口差异**：docker-compose.yml 将 PostgreSQL 映射到 **5432**，但所有测试文件硬编码使用 **5436**（`conftest.py` 中 `TEST_DATABASE_URL`）。运行测试前需确保有 PostgreSQL 实例在 5436 端口可用。

## 架构

### 分层结构

```
NeuroMemory (Facade, _core.py)
  ├── Database (db.py) — engine + async session 管理
  ├── Services (services/) — 业务逻辑层，每个 Service 接收 db session + provider
  │    ├── SearchService — 混合检索 (pgvector cosine + BM25 RRF 融合)
  │    ├── MemoryService — 记忆 CRUD + 时间查询
  │    ├── MemoryExtractionService — LLM 提取 facts/episodes/relations
  │    ├── ReflectionService — 洞察生成 + 情感画像更新
  │    ├── TemporalService — 时间范围过滤 + 时序记忆
  │    ├── GraphService / GraphMemoryService — 图 CRUD + 图谱召回
  │    ├── ConversationService — 会话管理
  │    ├── KVService — 键值存储
  │    └── FileService — 文件上传/管理
  ├── Models (models/) — SQLAlchemy 2.0 async 模型
  ├── Providers (providers/) — 可插拔 ABC + 实现
  └── Storage (storage/) — 对象存储 ABC + S3 实现
```

### Facade 模式

`_core.py` 中 `NeuroMemory` 是唯一的主 Facade 类，持有 Database 实例，每次操作开启独立 session，调用 Service 层。提供 `ingest()`, `recall()`, `digest()` 三个核心方法，并通过子 Facade 暴露子接口：
- `self.kv` → `KVFacade`：键值存储操作
- `self.conversations` → `ConversationsFacade`：会话管理 + 自动提取
- `self.graph` → `GraphFacade`：图谱 CRUD
- `self.files` → `FilesFacade`：文件上传/管理（需传入 storage 参数）

### 核心工作流

```
nm.ingest(role="user")
  ├── 存储到 conversations 表
  ├── 后台生成 embedding (asyncio.create_task)
  ├── auto_extract=True → 后台 LLM 提取 facts/episodes/relations
  │    ├── 存储到 embeddings 表（向量化）
  │    └── graph_enabled=True → 存储到 graph_nodes/edges 表
  └── 每 reflection_interval 条消息 → 后台 digest()

recall(query)
  ├── 并行获取 (asyncio.gather):
  │    ├── 向量检索 (pgvector cosine + BM25 RRF)
  │    ├── 图谱召回 (GraphMemoryService)
  │    └── 时序过滤 (TemporalService)
  ├── 合并阶段:
  │    ├── 图三元组覆盖度 boost (双端+0.10, 单端+0.04, 上限0.20)
  │    ├── 图三元组 → merged (source="graph")
  │    └── merged 按 score 降序排序
  └── 返回结构化结果

digest()
  ├── 分析水位线之后新增的 memories
  ├── LLM 生成行为模式和阶段总结
  ├── 更新 EmotionProfile
  └── 推进 last_reflected_at 水位线
```

### API 重命名历史 (v0.8.0)

公共方法已重命名：`add_message()` → `ingest()`，`reflect()` → `digest()`。代码中如遇旧名称，应使用新名称。

## 核心 API

```python
from neuromem import NeuroMemory, SiliconFlowEmbedding, OpenAILLM, S3Storage

async with NeuroMemory(
    database_url="postgresql+asyncpg://neuromem:neuromem@localhost:5432/neuromem",
    embedding=SiliconFlowEmbedding(api_key="..."),
    llm=OpenAILLM(api_key="...", model="deepseek-chat"),  # 必需，用于自动提取和反思
    storage=S3Storage(endpoint="http://localhost:9000"),    # 可选
    auto_extract=True,       # 默认开启，每条 user 消息自动提取记忆
    graph_enabled=False,     # 是否启用图存储
    reflection_interval=20,  # 每 20 条 user 消息后台自动 digest
) as nm:
    await nm.ingest(user_id="u1", role="user", content="I work at Google")
    result = await nm.recall(user_id="u1", query="workplace")
    await nm.digest(user_id="u1")
```

## 测试

测试需要运行中的 PostgreSQL（端口 **5436**）。

**Fixture 体系**（`conftest.py`）：
- `MockEmbeddingProvider`：基于文本 hash 生成确定性向量，无外部 API
- `MockLLMProvider`：返回空 JSON，无外部 API
- `nm` fixture：完整的 NeuroMemory 实例，使用 mock providers
- `db_session` fixture：每个测试函数独立，自动 drop/create 表 + rollback

**Marker**：
- `@pytest.mark.slow`：需要 embedding API（SiliconFlow/OpenAI）
- `@pytest.mark.requires_db`：需要 PostgreSQL

**配置**：`asyncio_mode = "auto"`，所有测试函数可直接 `async def`。

## 环境变量

```bash
DATABASE_URL=postgresql+asyncpg://neuromem:neuromem@localhost:5432/neuromem
SILICONFLOW_API_KEY=...          # Embedding API
EMBEDDING_PROVIDER=siliconflow   # siliconflow | openai | sentence_transformer
EMBEDDING_DIMS=1024              # 默认 1024 (BAAI/bge-m3)
```

## 服务端口

- PostgreSQL 开发：localhost:5432（用户名/密码: `neuromem`/`neuromem`）
- PostgreSQL 测试：localhost:5436（同上凭据）
- PostgreSQL 评测：localhost:5433（`docker-compose-eval.yml`，数据库名 `neuromem_eval`）
- MinIO API：localhost:9000 / Console：localhost:9001

## 开发约定

- 数据库操作使用 async SQLAlchemy，数据按 user_id 隔离
- Provider 通过构造函数注入（不使用全局单例）
- Service 类接收 db session 和 provider 作为构造参数
- Facade 类在 `_core.py` 中，每次操作开启独立 session
- 后台任务使用 `asyncio.create_task()`（embedding 生成、记忆提取、反思）
- 向量维度通过 `models/__init__.py` 的模块变量 `_embedding_dims` 控制，在 db init 前设置

## 工程推进流程

过程文件存放于 `rpiv/` 目录（已加入 `.gitignore`，不进版本库）。
