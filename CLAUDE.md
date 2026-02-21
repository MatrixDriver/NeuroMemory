# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

NeuroMemory 是一个 **Python 框架**，为 AI agent 开发者提供记忆管理能力。开发者直接 `from neuromemory import NeuroMemory` 在自己程序中使用，无需部署服务器。

**核心架构**：
- **Python 框架** (`neuromemory/`)：直接在 agent 程序中使用的库
- **可插拔 Provider**：Embedding (SiliconFlow/OpenAI)、LLM (OpenAI/DeepSeek)、Storage (S3/MinIO)
- **PostgreSQL + pgvector + AGE**：统一存储后端（结构化数据 + 向量检索 + 图数据库）

**数据隔离**：按 user_id 隔离，无多租户（tenant_id 已移除）。

## 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| Framework | Python async | 直接嵌入 agent 程序 |
| Database | PostgreSQL 16 + pgvector + AGE | 向量检索 + 图数据库 |
| ORM | SQLAlchemy 2.0 (async) | asyncpg 异步驱动 |
| Embedding | 可插拔 (SiliconFlow/OpenAI) | Provider 抽象 |
| LLM | 可插拔 (OpenAI/DeepSeek) | 用于记忆分类 |
| Storage | 可插拔 (S3/MinIO) | 文件存储 |

## 项目结构

```
neuromemory/
  __init__.py              # 公共导出 (NeuroMemory, providers, etc.)
  _core.py                 # NeuroMemory 主类 + Facade 类
  db.py                    # Database 类 (engine, session, init)
  models/
    __init__.py            # _embedding_dims 模块变量
    base.py                # Base, TimestampMixin
    memory.py              # Embedding 模型
    kv.py                  # KeyValue 模型
    conversation.py        # Conversation, ConversationSession
    document.py            # Document 模型
    graph.py               # GraphNode, GraphEdge, 枚举
  services/
    search.py              # SearchService (向量检索 + 记忆添加)
    memory.py              # MemoryService (时间查询)
    kv.py                  # KVService (键值存储)
    conversation.py        # ConversationService (会话管理)
    files.py               # FileService (文件上传/管理)
    file_processor.py      # 文件验证和文本提取
    graph.py               # GraphService (图数据库)
    memory_extraction.py   # MemoryExtractionService (LLM 记忆提取)
  providers/
    embedding.py           # ABC EmbeddingProvider
    llm.py                 # ABC LLMProvider
    siliconflow.py         # SiliconFlowEmbedding
    openai_embedding.py    # OpenAIEmbedding
    openai_llm.py          # OpenAILLM (兼容 DeepSeek)
  storage/
    base.py                # ABC ObjectStorage
    s3.py                  # S3Storage (MinIO/AWS/OBS)

tests/
  conftest.py              # MockEmbeddingProvider, NeuroMemory fixture
  test_kv.py
  test_search.py
  test_conversations.py
  test_memory_time.py
  test_files.py
  test_graph.py
  test_memory_extraction.py

docker-compose.yml      # PostgreSQL + MinIO (无 API 服务)
```

## 常用命令

```bash
# 启动数据库和 MinIO
docker compose -f docker-compose.yml up -d

# 只启动数据库
docker compose -f docker-compose.yml up -d db

# 安装开发依赖
uv pip install -e ".[dev]"

# 运行测试（需要 PostgreSQL 运行中）
pytest tests/

# 跳过需要 embedding API 的慢测试
pytest tests/ -m "not slow"
```

## 框架用法

```python
from neuromemory import NeuroMemory, SiliconFlowEmbedding, OpenAILLM, S3Storage

# 默认模式：自动提取（推荐）
async with NeuroMemory(
    database_url="postgresql+asyncpg://neuromemory:neuromemory@localhost:5432/neuromemory",
    embedding=SiliconFlowEmbedding(api_key="..."),
    llm=OpenAILLM(api_key="...", model="deepseek-chat"),  # 必需（自动提取）
    storage=S3Storage(endpoint="http://localhost:9000"),    # 可选
    auto_extract=True,  # 默认，每次 add_message 自动提取
) as nm:
    # 对话管理（自动提取记忆）
    await nm.conversations.add_message(user_id="u1", role="user", content="I work at Google")
    # → 自动提取: fact: "在 Google 工作"

    # 召回记忆（立即可用）
    result = await nm.recall(user_id="u1", query="workplace")

    # KV 存储
    await nm.kv.set("u1", "config", "language", "zh-CN")
    lang = await nm.kv.get("u1", "config", "language")

    # 定期生成洞察（可选）
    await nm.reflect(user_id="u1")  # 生成行为模式和阶段总结

    # 文件上传 (需要 storage)
    await nm.files.upload(user_id="u1", filename="doc.pdf", file_data=data)

    # 图数据库
    await nm.graph.create_node(node_type=NodeType.USER, node_id="u1")

# 手动模式：关闭自动提取
nm = NeuroMemory(
    database_url="...",
    embedding=SiliconFlowEmbedding(api_key="..."),
    llm=OpenAILLM(api_key="..."),
    auto_extract=False,  # 关闭自动提取
)
await nm.init()
await nm.conversations.add_message(user_id="u1", role="user", content="Hello")
await nm.reflect(user_id="u1")  # 手动提取 + 生成洞察
await nm.close()
```

## 服务访问

- PostgreSQL: localhost:5432 (用户名: `neuromemory`, 密码: `neuromemory`)
- MinIO: localhost:9000 (Console: localhost:9001)

## 测试

测试需要运行中的 PostgreSQL（通过 `docker compose -f docker-compose.yml up -d db` 启动）。

Marker：
- `@pytest.mark.slow`：需要 embedding API（SiliconFlow/OpenAI）
- `@pytest.mark.requires_db`：需要 PostgreSQL

## 开发约定

- 数据库操作使用 async SQLAlchemy
- 数据按 user_id 隔离（无 tenant_id）
- Provider 通过构造函数注入（不使用全局单例）
- Service 类接收 db session 和 provider 作为构造参数
- Facade 类在 _core.py 中，每次操作开启独立 session
- 不要在 `return` 之后写逻辑（不可达代码）

## 项目定位

NeuroMemory 是一个专注的 Python 库，不提供以下内容：
- ❌ Web 管理界面（记忆可视化应由 agent 应用提供）
- ❌ HTTP/API 服务器（直接在 Python 代码中使用）
- ❌ 独立部署的服务（嵌入到你的 agent 程序中）

详见 `docs/WHY_NO_WEB_UI.md`
