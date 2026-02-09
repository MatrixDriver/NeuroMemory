# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

NeuroMemory v2 是一个 **Memory-as-a-Service** 平台，为 AI agent 开发者提供记忆管理服务。通过 Python SDK 和 REST API，开发者可以为终端用户存储和检索偏好、事实、事件和文档等记忆数据。

**核心架构**：
- **Python SDK** (`sdk/neuromemory_client/`)：agent 开发者集成记忆能力的客户端库
- **REST API Server** (`server/`)：FastAPI 服务端，处理认证、存储、检索
- **PostgreSQL + pgvector**：统一存储后端（结构化数据 + 向量检索）

**多租户设计**：每个开发者（Tenant）通过 API Key 认证，数据按 tenant 隔离。

## 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| API Server | FastAPI | REST API + Swagger UI |
| Database | PostgreSQL 16 + pgvector | 结构化存储 + 向量检索 |
| ORM | SQLAlchemy 2.0 (async) | asyncpg 异步驱动 |
| Embedding | SiliconFlow (BAAI/bge-m3) | 1024 维向量 |
| SDK | httpx | 同步 HTTP 客户端 |
| Auth | API Key (Bearer Token) | SHA-256 哈希存储 |

## 项目结构

```
server/                    # API 服务端
  app/
    api/v1/               # v1 版本 API 路由
      schemas.py          # Pydantic 请求/响应模型
      preferences.py      # 偏好 CRUD 端点
      search.py           # 语义检索 + 记忆添加
      users.py            # 用户记忆概览
      health.py           # 健康检查
      tenants.py          # 租户注册
    core/
      config.py           # Pydantic Settings 配置
      logging.py          # 结构化 JSON 日志 + trace_id
      security.py         # API Key 生成和哈希
    db/
      session.py          # SQLAlchemy 异步引擎和会话
      init_db.py          # 数据库初始化（建表 + pgvector 扩展）
    models/
      base.py             # SQLAlchemy Base + TimestampMixin
      tenant.py           # Tenant 和 ApiKey 模型
      memory.py           # Preference 和 Embedding 模型
    services/
      auth.py             # API Key 认证中间件
      embedding.py        # Embedding 生成服务
      preferences.py      # 偏好 CRUD 服务
      search.py           # 向量检索服务
    main.py               # FastAPI 应用入口
  Dockerfile              # 服务端 Docker 镜像

sdk/                       # Python SDK 客户端
  neuromemory_client/
    __init__.py           # 导出 NeuroMemoryClient
    client.py             # 主客户端类
    preferences.py        # 偏好子客户端
    search.py             # 检索子客户端
  pyproject.toml          # SDK 包配置

tests/v2/                  # v2 测试
  conftest.py             # 测试固件（DB、认证、HTTP 客户端）
  test_auth.py            # 认证测试
  test_preferences.py     # 偏好 CRUD 测试
  test_search.py          # 检索测试（需 embedding API）
  test_health.py          # 健康检查测试

docker-compose.v2.yml      # v2 Docker Compose（PostgreSQL + API）
```

## 常用命令

```bash
# 启动数据库
docker compose -f docker-compose.v2.yml up -d db

# 启动 API 服务（开发模式）
.venv/bin/uvicorn server.app.main:app --reload --host 0.0.0.0 --port 8765

# 启动所有服务
docker compose -f docker-compose.v2.yml up -d

# 运行测试（需要 PostgreSQL 运行中）
pytest tests/v2/

# 跳过需要 embedding API 的慢测试
pytest tests/v2/ -m "not slow"

# 安装开发依赖
uv pip install -e ".[dev]"

# 安装 SDK（开发模式）
uv pip install -e sdk/
```

## 服务访问

**本地（docker compose up 后）：**
- REST API: http://localhost:8765
- API 文档: http://localhost:8765/docs (Swagger UI)
- PostgreSQL: localhost:5432 (用户名: `neuromemory`, 密码: `neuromemory`)

## REST API 端点

| 端点 | 方法 | 认证 | 说明 |
|------|------|------|------|
| `/` | GET | 无 | 存活探测 |
| `/v1/health` | GET | 无 | 健康检查（含数据库状态） |
| `/v1/tenants/register` | POST | 无 | 注册租户，获取 API Key |
| `/v1/preferences` | POST | 需要 | 设置偏好（upsert） |
| `/v1/preferences` | GET | 需要 | 列出用户所有偏好 |
| `/v1/preferences/{key}` | GET | 需要 | 获取单个偏好 |
| `/v1/preferences/{key}` | DELETE | 需要 | 删除偏好 |
| `/v1/memories` | POST | 需要 | 添加记忆（自动生成 embedding） |
| `/v1/search` | POST | 需要 | 语义检索 |
| `/v1/users/{user_id}/memories` | GET | 需要 | 用户记忆概览 |

**认证方式**：`Authorization: Bearer nm_xxx`

## SDK 用法

```python
from neuromemory_client import NeuroMemoryClient

client = NeuroMemoryClient(api_key="nm_xxx", base_url="http://localhost:8765")

# 偏好管理
client.preferences.set(user_id="u1", key="language", value="zh-CN")
client.preferences.get(user_id="u1", key="language")
client.preferences.list(user_id="u1")
client.preferences.delete(user_id="u1", key="language")

# 记忆存储和检索
client.add_memory(user_id="u1", content="I work at ABC Company")
results = client.search(user_id="u1", query="workplace")

# 用户记忆概览
client.get_user_memories(user_id="u1")
```

## 环境变量

在 `.env` 文件中配置：
```
DATABASE_URL=postgresql+asyncpg://neuromemory:neuromemory@localhost:5432/neuromemory
SILICONFLOW_API_KEY=your-api-key
EMBEDDING_PROVIDER=siliconflow
LOG_LEVEL=INFO
```

## 测试

测试需要运行中的 PostgreSQL（通过 `docker compose -f docker-compose.v2.yml up -d db` 启动）。

Marker：
- `@pytest.mark.slow`：需要 embedding API（SiliconFlow）
- `@pytest.mark.requires_db`：需要 PostgreSQL

## 分阶段开发

- **Phase 1**（当前）：SDK + API + 偏好 CRUD + 向量检索 + API Key 认证
- **Phase 2**：OBS 文档存储 + KV (jsonb) + 图数据库 (AGE) + LLM 分类器 + 配额管理
- **Phase 3**：用户 Console + 运维后台 + 华为云部署

## 工程推进流程

过程文件存放于 `rpiv/` 目录（已加入 `.gitignore`，不进版本库）。

## 开发约定

- 所有 API 响应使用 Pydantic 模型定义
- 数据库操作使用 async SQLAlchemy
- 日志使用结构化 JSON 格式（含 trace_id）
- 数据按 tenant_id 隔离，所有查询必须包含 tenant_id 过滤
- API 版本通过 URL 前缀 `/v1/` 管理
- 修改响应格式时，成功与错误两种响应、以及 docstring / OpenAPI 需一并更新
- 不要在 `return` 之后写逻辑（不可达代码）

## v1 文件（保留但不再使用）

v1 相关文件（`private_brain.py`、`session_manager.py`、`config.py`、`http_server.py` 等根目录 Python 文件）保留在仓库中作为参考，v2 代码在 `server/` 和 `sdk/` 目录下。
