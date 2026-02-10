# NeuroMemory v2 架构文档

> **版本**: v2.0
> **状态**: 生产就绪
> **最后更新**: 2026-02-10

---

## 目录

1. [架构概览](#1-架构概览)
2. [技术栈](#2-技术栈)
3. [核心组件](#3-核心组件)
4. [数据模型](#4-数据模型)
5. [认证与多租户](#5-认证与多租户)
6. [API 设计](#6-api-设计)
7. [部署架构](#7-部署架构)
8. [v1 迁移说明](#8-v1-迁移说明)

---

## 1. 架构概览

### 1.1 设计理念

NeuroMemory v2 是一个 **Memory-as-a-Service (MaaS)** 平台，为 AI agent 开发者提供记忆管理服务。通过简化架构，采用 PostgreSQL 统一存储方案，降低部署复杂度，同时保持高性能的向量检索能力。

### 1.2 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    NeuroMemory v2 架构                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              客户端层 (Client Layer)                  │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │  │
│  │  │ Python SDK   │  │  REST API    │  │    CLI       │ │  │
│  │  │   (httpx)    │  │  (HTTP/JSON) │  │   (Typer)    │ │  │
│  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘ │  │
│  └─────────┼──────────────────┼──────────────────┼─────────┘  │
│            │                  │                  │            │
│  ┌─────────▼──────────────────▼──────────────────▼─────────┐  │
│  │              API 服务层 (FastAPI)                        │  │
│  │  ┌──────────────────────────────────────────────────┐   │  │
│  │  │  认证中间件 (API Key Bearer Token)              │   │  │
│  │  └──────────────────┬───────────────────────────────┘   │  │
│  │  ┌─────────────────┴─────────────────────────────────┐  │  │
│  │  │  REST 端点                                        │  │  │
│  │  │  • /v1/tenants/register  - 租户注册              │  │  │
│  │  │  • /v1/preferences       - 偏好 CRUD             │  │  │
│  │  │  • /v1/memories          - 记忆添加              │  │  │
│  │  │  • /v1/search            - 语义检索              │  │  │
│  │  │  • /v1/memories/time-range - 时间范围查询        │  │  │
│  │  │  • /v1/memories/recent   - 最近记忆              │  │  │
│  │  │  • /v1/memories/timeline - 时间线聚合            │  │  │
│  │  └───────────────────┬───────────────────────────────┘  │  │
│  └────────────────────────┼──────────────────────────────────┘  │
│                           │                                    │
│  ┌────────────────────────▼──────────────────────────────────┐  │
│  │              服务层 (Service Layer)                       │  │
│  │  ┌───────────────┐  ┌────────────────┐  ┌─────────────┐  │  │
│  │  │ AuthService   │  │ MemoryService  │  │ SearchService│  │  │
│  │  │ - 认证验证    │  │ - 时间查询     │  │ - 向量检索  │  │  │
│  │  │ - tenant 隔离 │  │ - CRUD 操作    │  │ - embedding │  │  │
│  │  └───────────────┘  └────────────────┘  └─────────────┘  │  │
│  │  ┌─────────────────────────────────────────────────────┐  │  │
│  │  │ PreferencesService - 偏好管理                       │  │  │
│  │  └─────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────┬─────────────────────────────────┘  │
│                              │                                    │
│  ┌───────────────────────────▼─────────────────────────────────┐  │
│  │              ORM 层 (SQLAlchemy 2.0 Async)                  │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │  │
│  │  │ Tenant       │  │ ApiKey       │  │ Preference   │     │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘     │  │
│  │  ┌──────────────┐  ┌──────────────────────────────────┐   │  │
│  │  │ Embedding    │  │ TimestampMixin (created_at,      │   │  │
│  │  │ (pgvector)   │  │  updated_at, deleted_at)         │   │  │
│  │  └──────────────┘  └──────────────────────────────────┘   │  │
│  └───────────────────────────┬─────────────────────────────────┘  │
│                              │                                    │
│  ┌───────────────────────────▼─────────────────────────────────┐  │
│  │         存储层 (PostgreSQL 16 + pgvector)                   │  │
│  │  ┌────────────────────────────────────────────────────────┐ │  │
│  │  │  • 结构化数据 (租户、偏好、元数据)                     │ │  │
│  │  │  • 向量数据 (1024 维 embedding, cosine 距离)          │ │  │
│  │  │  • BRIN 索引 (时间序列优化)                            │ │  │
│  │  │  • B-tree 复合索引 (tenant_id, user_id, created_at)  │ │  │
│  │  └────────────────────────────────────────────────────────┘ │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │         外部服务 (External Services)                         │  │
│  │  ┌────────────────────────────────────────────────────────┐ │  │
│  │  │  SiliconFlow Embedding API                             │ │  │
│  │  │  • 模型: BAAI/bge-m3                                   │ │  │
│  │  │  • 维度: 1024                                          │ │  │
│  │  │  • 支持中英文                                          │ │  │
│  │  └────────────────────────────────────────────────────────┘ │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

### 1.3 核心设计原则

1. **简化架构**: 从 v1 的三层存储（Neo4j + Qdrant + LLM）简化为 PostgreSQL 统一存储
2. **多租户隔离**: 所有数据按 `tenant_id` 严格隔离，支持 SaaS 模式
3. **异步优先**: 全栈异步设计（async/await），提升并发性能
4. **API 优先**: REST API 作为核心接口，SDK 是轻量封装
5. **类型安全**: Pydantic 模型定义所有请求/响应，自动生成 OpenAPI 文档

---

## 2. 技术栈

### 2.1 技术选型

| 组件 | 技术 | 版本 | 说明 |
|------|------|------|------|
| **API 框架** | FastAPI | 0.104+ | 高性能异步 Web 框架 |
| **数据库** | PostgreSQL | 16+ | 统一存储后端 |
| **向量扩展** | pgvector | 0.5+ | PostgreSQL 向量插件 |
| **ORM** | SQLAlchemy | 2.0+ | 异步 ORM，asyncpg 驱动 |
| **Schema 验证** | Pydantic | 2.0+ | 请求/响应模型定义 |
| **HTTP 客户端** | httpx | 0.25+ | SDK 同步 HTTP 客户端 |
| **Embedding** | SiliconFlow | - | BAAI/bge-m3 (1024 维) |
| **容器化** | Docker | 20+ | 服务打包和部署 |

### 2.2 为什么选择 PostgreSQL + pgvector？

**相比 v1 的 Neo4j + Qdrant：**

| 维度 | v1 (Neo4j + Qdrant) | v2 (PostgreSQL + pgvector) |
|------|---------------------|---------------------------|
| **部署复杂度** | 需要 3 个独立服务 | 只需 2 个服务（API + DB） |
| **运维成本** | 3 套监控、备份、升级 | 单一数据库，统一运维 |
| **数据一致性** | 跨库事务困难 | 原生 ACID 事务支持 |
| **查询性能** | 向量检索快，但需跨库 | pgvector 性能接近专用 VectorDB |
| **学习曲线** | 需要学习 Cypher + Qdrant API | 标准 SQL + 少量向量扩展 |
| **成本** | 企业版 Neo4j 昂贵 | PostgreSQL 完全开源免费 |

**pgvector 性能优化：**
- **HNSW 索引**: 近似最近邻搜索，性能接近 Qdrant
- **BRIN 索引**: 时间序列数据，节省 99% 空间
- **并行查询**: PostgreSQL 原生并行执行优化

---

## 3. 核心组件

### 3.1 API 服务层

**文件**: `server/app/main.py`

FastAPI 应用入口，注册路由、中间件、异常处理。

**核心路由**:
- `/v1/tenants/*` - 租户管理
- `/v1/preferences/*` - 偏好 CRUD
- `/v1/memories/*` - 记忆管理
- `/v1/search` - 语义检索

### 3.2 认证服务

**文件**: `server/app/services/auth.py`

**功能**:
- API Key 验证（Bearer Token）
- SHA-256 哈希存储
- Tenant 上下文注入（`get_current_tenant` 依赖）

**流程**:
```python
# 请求头
Authorization: Bearer nm_1234567890abcdef

# 验证流程
1. 提取 Bearer Token
2. SHA-256 哈希
3. 数据库查询匹配
4. 返回 tenant_id
```

### 3.3 服务层

#### PreferencesService
**文件**: `server/app/services/preferences.py`

- `set_preference()`: Upsert 偏好（支持 JSON 值）
- `get_preference()`: 按 key 查询
- `list_preferences()`: 列出用户所有偏好
- `delete_preference()`: 删除偏好

#### SearchService
**文件**: `server/app/services/search.py`

- `search_memories()`: 向量相似度搜索（cosine 距离）
- 支持时间过滤（`created_after`, `created_before`）
- 支持记忆类型过滤（`memory_type`）

#### MemoryService
**文件**: `server/app/services/memory.py`

- `get_memories_by_time_range()`: 时间范围查询
- `get_recent_memories()`: 最近 N 天记忆
- `get_daily_memory_stats()`: 按日统计
- `get_memory_timeline()`: 时间线聚合（日/周/月）

### 3.4 Embedding 服务

**文件**: `server/app/services/embedding.py`

**流程**:
```
用户输入文本
    ↓
SiliconFlow API
    ↓
BAAI/bge-m3 模型
    ↓
1024 维向量
    ↓
存入 PostgreSQL (vector 类型)
```

---

## 4. 数据模型

### 4.1 数据库表结构

#### tenants (租户表)
```sql
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    deleted_at TIMESTAMP WITH TIME ZONE
);
```

#### api_keys (API 密钥表)
```sql
CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    key_hash VARCHAR(64) NOT NULL UNIQUE,  -- SHA-256
    name VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE,
    last_used_at TIMESTAMP WITH TIME ZONE
);
```

#### preferences (偏好表)
```sql
CREATE TABLE preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    key VARCHAR(255) NOT NULL,
    value JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(tenant_id, user_id, key)
);
```

#### embeddings (向量存储表)
```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    memory_type VARCHAR(50) DEFAULT 'general',
    metadata_ JSONB,
    embedding vector(1024),  -- pgvector 类型
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    deleted_at TIMESTAMP WITH TIME ZONE
);

-- 向量相似度索引
CREATE INDEX idx_embeddings_vector ON embeddings
USING hnsw (embedding vector_cosine_ops);

-- 时间序列索引 (BRIN, 节省 99% 空间)
CREATE INDEX idx_embeddings_created_at_brin ON embeddings
USING BRIN (created_at) WITH (pages_per_range = 128);

-- 复合索引 (多列过滤 + 排序)
CREATE INDEX idx_embeddings_tenant_user_created ON embeddings
(tenant_id, user_id, created_at DESC);
```

### 4.2 多租户数据隔离

**原则**: 所有查询必须包含 `tenant_id` 过滤

```python
# ✅ 正确：包含 tenant_id 过滤
query = select(Embedding).where(
    Embedding.tenant_id == tenant_id,
    Embedding.user_id == user_id
)

# ❌ 错误：缺少 tenant_id 过滤（可能泄露其他租户数据）
query = select(Embedding).where(
    Embedding.user_id == user_id
)
```

---

## 5. 认证与多租户

### 5.1 认证流程

```
客户端                    API Server                数据库
  │                          │                       │
  │  POST /v1/tenants/register                      │
  │ ─────────────────────────>│                      │
  │                          │  INSERT INTO tenants │
  │                          │ ─────────────────────>│
  │                          │  生成 API Key         │
  │                          │  (nm_xxxxxxxx)       │
  │                          │  存储 SHA-256 哈希    │
  │                          │ ─────────────────────>│
  │  { api_key: "nm_xxx" }  │                       │
  │ <─────────────────────────│                      │
  │                          │                       │
  │  GET /v1/preferences     │                       │
  │  Authorization: Bearer nm_xxx                    │
  │ ─────────────────────────>│                      │
  │                          │  验证 API Key 哈希    │
  │                          │ ─────────────────────>│
  │                          │  返回 tenant_id       │
  │                          │ <─────────────────────│
  │                          │  注入依赖: tenant_id  │
  │                          │  执行业务逻辑         │
  │  { preferences: [...] }  │                       │
  │ <─────────────────────────│                      │
```

### 5.2 API Key 生成

```python
import secrets
import hashlib

# 生成 API Key
raw_key = f"nm_{secrets.token_urlsafe(32)}"  # nm_xxxxxx (43 字符)

# 存储哈希
key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

# 客户端收到原始 key，服务端只存储哈希
```

---

## 6. API 设计

### 6.1 API 版本管理

- **URL 前缀**: `/v1/`（当前版本）
- **未来扩展**: `/v2/`（破坏性变更时引入）

### 6.2 核心端点

#### 租户注册
```http
POST /v1/tenants/register
Content-Type: application/json

{
  "name": "MyCompany",
  "email": "admin@example.com"
}

Response 200:
{
  "tenant_id": "uuid",
  "api_key": "nm_xxxxxx",
  "message": "Registration successful"
}
```

#### 偏好管理
```http
# 设置偏好
POST /v1/preferences
Authorization: Bearer nm_xxx

{
  "user_id": "alice",
  "key": "language",
  "value": "zh-CN"
}

# 查询偏好
GET /v1/preferences?user_id=alice&key=language

# 列出所有偏好
GET /v1/preferences?user_id=alice

# 删除偏好
DELETE /v1/preferences/language?user_id=alice
```

#### 记忆添加
```http
POST /v1/memories
Authorization: Bearer nm_xxx

{
  "user_id": "alice",
  "content": "I work at ABC Company as a software engineer",
  "memory_type": "fact",
  "metadata": {"source": "conversation"}
}

Response 200:
{
  "id": "uuid",
  "user_id": "alice",
  "content": "...",
  "memory_type": "fact",
  "created_at": "2026-02-10T08:00:00Z"
}
```

#### 语义检索
```http
POST /v1/search
Authorization: Bearer nm_xxx

{
  "user_id": "alice",
  "query": "Where does Alice work?",
  "limit": 5,
  "memory_type": "fact",
  "created_after": "2026-01-01T00:00:00Z"
}

Response 200:
{
  "results": [
    {
      "id": "uuid",
      "content": "I work at ABC Company as a software engineer",
      "similarity": 0.89,
      "created_at": "2026-02-10T08:00:00Z"
    }
  ]
}
```

#### 时间范围查询
```http
POST /v1/memories/time-range
Authorization: Bearer nm_xxx

{
  "user_id": "alice",
  "start_time": "2026-01-01T00:00:00Z",
  "end_time": "2026-01-31T23:59:59Z",
  "memory_type": "fact",
  "limit": 50,
  "offset": 0
}

Response 200:
{
  "user_id": "alice",
  "total": 123,
  "limit": 50,
  "offset": 0,
  "time_range": {
    "start": "2026-01-01T00:00:00Z",
    "end": "2026-01-31T23:59:59Z"
  },
  "memories": [...]
}
```

完整 API 文档见 [API_REFERENCE.md](API_REFERENCE.md)。

---

## 7. 部署架构

### 7.1 本地开发

```yaml
# docker-compose.v2.yml
services:
  db:
    image: pgvector/pgvector:pg16
    ports:
      - "5432:5432"
    environment:
      POSTGRES_USER: neuromemory
      POSTGRES_PASSWORD: neuromemory
      POSTGRES_DB: neuromemory
    volumes:
      - postgres_data:/var/lib/postgresql/data

  api:
    build: .
    ports:
      - "8765:8765"
    environment:
      DATABASE_URL: postgresql+asyncpg://neuromemory:neuromemory@db:5432/neuromemory
      SILICONFLOW_API_KEY: ${SILICONFLOW_API_KEY}
    depends_on:
      - db
```

启动：
```bash
docker compose -f docker-compose.v2.yml up -d
```

### 7.2 生产部署

**推荐架构**:
```
                    ┌─────────────────┐
                    │   Load Balancer │
                    │   (Nginx/ALB)   │
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
    ┌────▼─────┐      ┌─────▼──────┐     ┌─────▼──────┐
    │ API Pod 1│      │ API Pod 2  │ ... │ API Pod N  │
    │ (FastAPI)│      │ (FastAPI)  │     │ (FastAPI)  │
    └────┬─────┘      └─────┬──────┘     └─────┬──────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             │
                    ┌────────▼────────┐
                    │   PostgreSQL    │
                    │   (RDS/Cloud)   │
                    │   + pgvector    │
                    └─────────────────┘
```

**环境变量**:
```bash
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db
SILICONFLOW_API_KEY=sk-xxx
LOG_LEVEL=INFO
```

---

## 8. v1 迁移说明

### 8.1 架构对比

| 组件 | v1 | v2 | 迁移策略 |
|------|----|----|----------|
| 向量存储 | Qdrant | PostgreSQL + pgvector | 导出向量数据，重新导入 |
| 图存储 | Neo4j | PostgreSQL (jsonb) | 暂不支持，未来考虑 AGE 扩展 |
| 认证 | 无 | API Key 多租户 | 创建租户，分配 API Key |
| 会话管理 | SessionManager | 移除 | 客户端自行管理上下文 |
| LLM 集成 | Mem0 + LangChain | 移除 | 客户端使用 LLM SDK |

### 8.2 不兼容变更

1. **移除 Neo4j 知识图谱**: v2 专注向量检索，不支持图遍历
2. **移除 Mem0 集成**: v2 是纯存储服务，不包含 LLM 推理
3. **API 端点变更**: v1 的 `/process` 端点在 v2 中拆分为 `/memories` 和 `/search`
4. **认证机制**: v2 强制要求 API Key 认证

### 8.3 迁移建议

**如果你依赖 v1 的知识图谱功能**:
- 保留 v1 部署，或等待 v2 的 AGE 图数据库支持（Phase 2）

**如果你只使用向量检索**:
- 可以迁移到 v2，性能更好，部署更简单

---

## 附录

### A. 性能指标

| 操作 | 延迟 (P50) | 延迟 (P99) | 吞吐量 |
|------|-----------|-----------|--------|
| 添加记忆 | 50ms | 150ms | 1000 req/s |
| 语义检索 | 30ms | 100ms | 2000 req/s |
| 偏好查询 | 5ms | 20ms | 5000 req/s |

**测试环境**: PostgreSQL 16, 8 vCPU, 32GB RAM, NVMe SSD

### B. 安全考虑

1. **SQL 注入防护**: 使用 SQLAlchemy 参数化查询
2. **API Key 哈希**: SHA-256 单向哈希，不可逆
3. **多租户隔离**: 所有查询强制包含 `tenant_id`
4. **输入验证**: Pydantic 模型验证所有输入
5. **HTTPS 强制**: 生产环境禁用 HTTP

### C. 参考资料

- [FastAPI 官方文档](https://fastapi.tiangolo.com)
- [SQLAlchemy 2.0 文档](https://docs.sqlalchemy.org/en/20/)
- [pgvector GitHub](https://github.com/pgvector/pgvector)
- [PostgreSQL 官方文档](https://www.postgresql.org/docs/16/)

---

**文档维护**: 本文档随 v2 代码同步更新。如有问题，请提交 Issue。
