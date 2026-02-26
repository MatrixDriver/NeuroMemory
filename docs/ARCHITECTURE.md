# neuromem 架构文档

> **最后更新**: 2026-02-24

---

## 目录

1. [架构概览](#1-架构概览)
2. [技术栈](#2-技术栈)
3. [核心设计模式](#3-核心设计模式)
4. [数据模型](#4-数据模型)
5. [Provider 系统](#5-provider-系统)
6. [服务层](#6-服务层)
7. [部署架构](#7-部署架构)
8. [架构差异化：单一 PostgreSQL vs 多库拼装](#8-架构差异化单一-postgresql-vs-多库拼装)
9. [情感架构](#9-情感架构)

---

## 1. 架构概览

### 1.1 设计理念

neuromem 是一个 **Python 框架**（非 Client-Server），AI agent 开发者直接 `from neuromem import neuromem` 嵌入自己的程序使用。核心设计原则：

1. **框架而非服务**: 无需部署后台服务器，直接在 Python 程序中使用
2. **可插拔 Provider**: Embedding、LLM、Storage 通过抽象接口注入
3. **异步优先**: 全链路 async/await
4. **user_id 隔离**: 数据按 user_id 隔离，无多租户
5. **门面模式**: 简洁的顶层 API，复杂逻辑在服务层

### 1.2 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│                   neuromem 架构                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  应用层 (Your Agent Code)                             │  │
│  │  nm = NeuroMemory(database_url=..., embedding=...)    │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐  │
│  │  门面层 (neuromem/_core.py)                        │  │
│  │  neuromem 主类                                     │  │
│  │  ├── nm.add_memory() / nm.search()                    │  │
│  │  ├── nm.kv          (KVFacade)                        │  │
│  │  ├── nm.conversations (ConversationsFacade)           │  │
│  │  ├── nm.files       (FilesFacade)                     │  │
│  │  └── nm.graph       (GraphFacade)                     │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐  │
│  │  服务层 (neuromem/services/)                        │  │
│  │  SearchService │ KVService │ ConversationService       │  │
│  │  FileService │ GraphService │ MemoryExtractionService  │  │
│  │  MemoryService │ FileProcessor                        │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐  │
│  │  Provider 层 (neuromem/providers/)                  │  │
│  │  EmbeddingProvider (ABC)                               │  │
│  │  ├── SiliconFlowEmbedding (BAAI/bge-m3, 1024 维)     │  │
│  │  └── OpenAIEmbedding (text-embedding-3-small, 1536 维)│  │
│  │  LLMProvider (ABC)                                     │  │
│  │  └── OpenAILLM (兼容 OpenAI/DeepSeek)                 │  │
│  │  ObjectStorage (ABC)                                   │  │
│  │  └── S3Storage (MinIO/AWS/OBS)                        │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐  │
│  │  数据层                                               │  │
│  │  Database (neuromem/db.py)                          │  │
│  │  ├── PostgreSQL + pgvector (向量 + 结构化)            │  │
│  │  ├── 关系表图谱 (GraphNode/GraphEdge)                  │  │
│  │  └── SQLAlchemy 2.0 async (asyncpg)                   │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  外部存储 (可选)                                       │  │
│  │  MinIO / AWS S3 / 华为云 OBS (文件存储)               │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 技术栈

| 组件 | 技术 | 版本 | 说明 |
|------|------|------|------|
| **语言** | Python | 3.10+ | async/await 全链路 |
| **数据库** | PostgreSQL | 16+ | 统一存储后端 |
| **向量扩展** | pgvector | 0.7+ | 向量相似度检索 |
| **图存储** | PostgreSQL 关系表 | - | GraphNode/GraphEdge（无 Cypher 依赖） |
| **ORM** | SQLAlchemy | 2.0+ | asyncpg 异步驱动 |
| **Embedding** | SiliconFlow / OpenAI | - | 可插拔 Provider |
| **LLM** | OpenAI / DeepSeek | - | 记忆分类提取 |
| **文件存储** | boto3 | - | S3 兼容接口 |

---

## 3. 核心设计模式

### 3.1 门面模式 (Facade)

`neuromem` 主类是门面，提供简洁的顶层 API。每个子模块是一个 Facade 类：

```python
class neuromem:
    def __init__(self, database_url, embedding, llm=None, storage=None):
        self._db = Database(database_url)
        self._embedding = embedding
        self.kv = KVFacade(self._db)
        self.conversations = ConversationsFacade(self._db)
        self.files = FilesFacade(self._db, embedding, storage)
        self.graph = GraphFacade(self._db)
```

Facade 类每次操作开启独立 session：

```python
class KVFacade:
    async def set(self, namespace, scope_id, key, value):
        async with self._db.session() as session:
            return await KVService(session).set(namespace, scope_id, key, value)
```

### 3.2 Provider 注入

Provider 通过构造函数注入，不使用全局单例：

```python
# 开发者选择 Provider
nm = NeuroMemory(
    database_url="...",
    embedding=SiliconFlowEmbedding(api_key="..."),  # 或 OpenAIEmbedding
    llm=OpenAILLM(api_key="..."),                    # 可选
    storage=S3Storage(endpoint="..."),                # 可选
)
```

### 3.3 Database 类

替代 FastAPI 的 `get_db` 依赖注入，提供 session 上下文管理器：

```python
class Database:
    def __init__(self, url, pool_size=10):
        self.engine = create_async_engine(url, pool_size=pool_size)
        self.session_factory = async_sessionmaker(engine, ...)

    @asynccontextmanager
    async def session(self):
        async with self.session_factory() as s:
            try:
                yield s
                await s.commit()
            except:
                await s.rollback()
                raise

    async def init(self):   # CREATE EXTENSION vector; create_all
    async def close(self):  # engine.dispose()
```

### 3.4 动态向量维度

Embedding 维度在运行时确定（不同 Provider 维度不同）：

```python
# neuromem/models/__init__.py
_embedding_dims = 1024  # 默认值

# neuromem.__init__() 中设置
import neuromem.models as _models
_models._embedding_dims = embedding.dims  # 在 init() 建表前设置
```

`Embedding` 模型使用 `__declare_last__` 在表创建时读取维度值。

---

## 4. 数据模型

所有模型按 `user_id` 隔离，无 `tenant_id`。

### 4.1 embeddings (向量存储)

```sql
CREATE TABLE embeddings (
    id UUID PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1024),  -- 维度由 Provider 决定
    memory_type VARCHAR(50) DEFAULT 'general',
    metadata_ JSONB,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
);

-- 向量索引
CREATE INDEX idx_emb_vector ON embeddings USING hnsw (embedding vector_cosine_ops);
-- 用户索引
CREATE INDEX ix_emb_user ON embeddings (user_id);
```

### 4.2 key_values (KV 存储)

```sql
CREATE TABLE key_values (
    id UUID PRIMARY KEY,
    namespace VARCHAR(255) NOT NULL,
    scope_id VARCHAR(255) NOT NULL,
    key VARCHAR(255) NOT NULL,
    value JSONB NOT NULL,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    UNIQUE (namespace, scope_id, key)
);
```

### 4.3 conversations (对话)

```sql
CREATE TABLE conversations (
    id UUID PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    session_id VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    extracted BOOLEAN DEFAULT FALSE,
    metadata_ JSONB,
    created_at TIMESTAMPTZ
);

CREATE TABLE conversation_sessions (
    id UUID PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    session_id VARCHAR(255) NOT NULL UNIQUE,
    message_count INTEGER DEFAULT 0,
    last_message_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
);
```

### 4.4 documents (文件)

```sql
CREATE TABLE documents (
    id UUID PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    filename VARCHAR(500) NOT NULL,
    file_type VARCHAR(50),
    mime_type VARCHAR(100),
    file_size INTEGER,
    object_key VARCHAR(500),
    extracted_text TEXT,
    embedding_id UUID REFERENCES embeddings(id),
    category VARCHAR(100) DEFAULT 'general',
    tags JSONB,
    metadata_ JSONB,
    source_type VARCHAR(50),
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
);
```

### 4.5 graph_nodes / graph_edges (图)

```sql
CREATE TABLE graph_nodes (
    id UUID PRIMARY KEY,
    user_id VARCHAR(255),
    node_type VARCHAR(100) NOT NULL,
    node_id VARCHAR(255) NOT NULL,
    properties JSONB,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
);

CREATE TABLE graph_edges (
    id UUID PRIMARY KEY,
    user_id VARCHAR(255),
    source_type VARCHAR(100) NOT NULL,
    source_id VARCHAR(255) NOT NULL,
    edge_type VARCHAR(100) NOT NULL,
    target_type VARCHAR(100) NOT NULL,
    target_id VARCHAR(255) NOT NULL,
    properties JSONB,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
);
```

图数据存储在 PostgreSQL 关系表中，通过 SQL 查询实现图遍历，无需 Apache AGE 或 Cypher。

---

## 5. Provider 系统

### 5.1 EmbeddingProvider

```python
class EmbeddingProvider(ABC):
    @abstractmethod
    async def embed(self, text: str) -> list[float]: ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...

    @property
    @abstractmethod
    def dims(self) -> int: ...
```

内置实现：
- `SiliconFlowEmbedding`: BAAI/bge-m3, 1024 维，支持中英文
- `OpenAIEmbedding`: text-embedding-3-small, 1536 维

### 5.2 LLMProvider

```python
class LLMProvider(ABC):
    @abstractmethod
    async def chat(self, messages: list[dict], temperature=0.7, max_tokens=1024) -> str: ...
```

内置实现：
- `OpenAILLM`: 兼容 OpenAI 和 DeepSeek API

用于 `MemoryExtractionService` 从对话中分类提取记忆。

### 5.3 ObjectStorage

```python
class ObjectStorage(ABC):
    async def init(self) -> None: ...
    async def upload(self, prefix, filename, data, content_type) -> str: ...
    async def download(self, object_key) -> bytes: ...
    async def delete(self, object_key) -> None: ...
    async def get_presigned_url(self, object_key, expires_in=3600) -> str: ...
```

内置实现：
- `S3Storage`: 使用 boto3，兼容 MinIO / AWS S3 / 华为云 OBS

### 5.4 自定义 Provider

实现 ABC 接口即可：

```python
from neuromem.providers.embedding import EmbeddingProvider

class MyEmbedding(EmbeddingProvider):
    @property
    def dims(self) -> int:
        return 768

    async def embed(self, text: str) -> list[float]:
        # 调用你的 embedding 服务
        return await my_api.embed(text)

nm = NeuroMemory(database_url="...", embedding=MyEmbedding())
```

---

## 6. 服务层

每个 Service 接收 `db session` 和 Provider 作为构造参数：

| 服务 | 依赖 | 功能 |
|------|------|------|
| `SearchService` | session, embedding | 向量检索、记忆添加、RRF 混合排序 |
| `KVService` | session | 键值 CRUD、batch 操作 |
| `ConversationService` | session | 会话消息管理 |
| `MemoryService` | session | 时间范围/时间线查询 |
| `FileService` | session, embedding, storage | 文件上传、文本提取 |
| `GraphService` | session | 图节点/边 CRUD |
| `GraphMemoryService` | session | 图三元组存储/冲突检测/实体查询 |
| `MemoryExtractionService` | session, embedding, llm | LLM 记忆分类提取 |
| `ReflectionService` | session, embedding, llm | 洞察生成 + 情感画像更新 |
| `TemporalService` | session | 时序记忆与时间范围过滤 |

### 6.1 recall() 融合排序流程

`recall()` 是核心检索方法，通过并行获取 + 合并阶段实现多源融合：

```
recall(query)
  ├─ asyncio.gather 并行执行:
  │   ├─ _fetch_vector_memories()    → SearchService.scored_search()
  │   │     └─ SQL 内融合: RRF(vector, BM25) × recency × importance
  │   ├─ _fetch_user_profile()       → KV profile 读取
  │   ├─ _search_conversations()     → 对话向量检索 (可选)
  │   └─ _fetch_graph_memories()     → GraphMemoryService.find_entity_facts()
  │
  ├─ 合并阶段 (Python):
  │   ├─ 构建图三元组集合
  │   ├─ 向量结果 + 图 boost (三元组覆盖度)
  │   │     └─ 双端命中 +0.5, 单端命中 +0.2, 上限 2.0
  │   ├─ 图三元组 → merged (source="graph")
  │   ├─ 对话结果 → merged (source="conversation")
  │   └─ merged 按 score 降序排序
  │
  └─ 返回: vector_results, graph_results, graph_context, user_profile, merged
```

---

## 7. 部署架构

### 7.1 开发环境

```bash
docker compose -f docker-compose.yml up -d
```

提供：
- PostgreSQL（含 pgvector + pg_search）: `localhost:5432`
- MinIO（可选）: `localhost:9000`（Console: `localhost:9001`）

### 7.2 生产环境

```
┌───────────────────────────────┐
│  Your Agent Application       │
│  ┌─────────────────────────┐ │
│  │  neuromem Framework  │ │
│  └───────────┬─────────────┘ │
└──────────────┼───────────────┘
               │
    ┌──────────▼───────────┐
    │  PostgreSQL (RDS)    │
    │  + pgvector + pg_search    │
    └──────────────────────┘
               │
    ┌──────────▼───────────┐
    │  S3 / MinIO / OBS    │  (可选，用于文件存储)
    └──────────────────────┘
```

neuromem 作为库嵌入你的应用，不需要独立部署。只需确保：
1. PostgreSQL 可访问
2. Embedding API 可用
3. S3 存储可访问（如果使用文件功能）

---

## 8. 架构差异化：单一 PostgreSQL vs 多库拼装

### 8.1 竞品架构对比

| 框架 | 向量存储 | 图存储 | KV/缓存 | 结构化数据 | 部署组件数 |
|------|---------|--------|---------|-----------|-----------|
| **neuromem** | pgvector | 关系表 | PostgreSQL | PostgreSQL | **1** |
| Mem0 | Qdrant | Neo4j | — | PostgreSQL | 3 |
| MemOS | Qdrant | Neo4j | Redis | PostgreSQL | 4 |
| graphiti | 向量数据库 | Neo4j | — | PostgreSQL | 3+ |

### 8.2 单一 PostgreSQL 架构的技术优势

**事务一致性**：所有数据操作（向量、图谱、对话、KV）在同一个数据库事务内完成。`delete_user_data()` 跨 8 张表原子删除，`export_user_data()` 在一个快照内导出——多库架构中需要分布式事务或 saga 模式才能实现类似保证。

**跨类型查询**：`entity_profile()` 通过 SQL JOIN 跨 embeddings、graph_nodes/edges、conversations 三种数据源构建实体画像。`stats()` 聚合所有记忆类型的分布统计。这些操作在单库中是简单的 SQL 查询，在多库架构中需要应用层数据聚合。

**联合排序**：`recall()` 的图 boost 融合排序依赖于图三元组和向量结果在同一进程内交叉匹配。图和向量分属不同数据库时，跨库 JOIN 的延迟和复杂度使类似的实时融合排序变得不切实际。

**运维简化**：
- 备份：`pg_dump` 一次导出全部数据（向量 + 图谱 + 对话 + KV + 画像）
- 监控：一个 PostgreSQL 实例的指标即为全部
- 扩展：垂直扩展 PostgreSQL 即可提升所有子系统性能
- 迁移：一个 `create_all()` 完成所有表创建，无需协调多个数据库的 schema

### 8.3 部署架构

```
开发环境:
  docker compose up -d db  →  PostgreSQL (pgvector + pg_search) ready

生产环境:
  托管 PostgreSQL (AWS RDS / Supabase / 阿里云 RDS)
  + pip install neuromem
  → 完整记忆系统就绪
```

对比竞品的生产部署：
```
Mem0:    PostgreSQL + Qdrant Cloud + Neo4j Aura    → 3 个服务的连接串、认证、监控
MemOS:   PostgreSQL + Redis Cloud + Qdrant + Neo4j → 4 个服务的运维负担
```

---

## 9. 情感架构

### 9.1 三层情感设计

neuromem 实现了三层情感架构，从瞬时情感到长期画像全覆盖：

| 层次 | 类型 | 存储位置 | 时间性 | 示例 |
|------|------|---------|--------|------|
| **微观** | 事件情感标注 | 记忆 metadata (valence/arousal/label) | 瞬时 | "说到面试时很紧张(valence=-0.6)" |
| **中观** | 近期情感状态 | emotion_profiles.latest_state | 1-2周 | "最近工作压力大，情绪低落" |
| **宏观** | 长期情感画像 | emotion_profiles.* | 长期稳定 | "容易焦虑，但对技术话题兴奋" |

**各层职责**：

- **微观**：捕捉瞬时情感，丰富记忆细节。每条记忆的 `metadata.emotion` 包含 `valence`（情感效价 -1~1）、`arousal`（唤醒度 0~1）、`label`（情感标签），由 LLM 提取时自动标注
- **中观**：追踪近期状态，agent 可以关心"你最近还好吗"。`emotion_profiles.latest_state` 由 `reflect()` 自动更新
- **宏观**：理解长期特质，形成真正的用户画像。`emotion_profiles` 中的 `dominant_emotions`、`valence_avg` 等字段反映长期情感倾向

### 9.2 情感与记忆检索的联动

情感标注不只是元数据——它直接参与 `recall()` 的评分计算：

```
recency = e^(-t / (decay_rate × (1 + arousal × 0.5)))
```

高情感唤醒（arousal）的记忆衰减更慢，模拟人类对强烈情感事件的持久记忆（闪光灯记忆效应）。

### 9.3 隐私合规

> **EU AI Act Article 5** 禁止自动推断用户人格（Big Five）或价值观。neuromem 不自动推断此类信息。情感画像仅记录用户在对话中表达的情感状态，不做人格推断。人格和价值观应由开发者通过 system prompt 设定 agent 角色。

---

**文档维护**: 本文档随代码同步更新。如有问题，请提交 Issue。
