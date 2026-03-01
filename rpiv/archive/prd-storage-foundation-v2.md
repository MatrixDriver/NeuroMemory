---
description: "产品需求文档: storage-foundation-v2"
status: archived
created_at: 2026-02-28T22:30:00
updated_at: 2026-03-02T00:05:00
archived_at: 2026-03-02T00:05:00
---

# PRD: 存储基座 V2（Schema + ORM + 迁移）

## 1. 执行摘要

neuromem SDK 当前使用单表 `embeddings` + 全 JSONB 架构存储所有类型的记忆。这一架构在记忆分类 V2（fact/episodic/trait/document 四类体系 + trait 三层子类 + 生命周期管理）需求下暴露出严重局限：无法为 trait 提供专用列（导致 JSONB 写放大和无统计信息）、缺少双时间线（无法支持矛盾保留和时间旅行查询）、缺少证据链和审计日志的独立存储。

本项目（RPIV-1）的目标是 **为 V2 记忆分类铺设存储基座** —— 完成 schema 改造（表改名 + 新增列 + 辅助表）、ORM 模型重写、数据回填、halfvec 迁移、写入/读取路径适配和索引更新，确保现有功能无感知升级，所有公共 API 行为不变。

**核心价值**：RPIV-1 完成后，V2 分类体系所需的全部存储基础设施就位，RPIV-2（Reflection 引擎 + Trait 生命周期 + 召回改造）可在此基础上快速实施。

## 2. 使命

**使命声明**：为 neuromem SDK 建立面向记忆分类 V2 的存储基座，在不破坏现有功能的前提下完成 schema 演进。

**核心原则**：

1. **无感知升级**：所有公共 API（`ingest()`、`recall()`、`digest()`、`add_memory()`、`search()`）行为保持不变，现有用户无需修改代码
2. **幂等迁移**：所有 DDL 操作（`ALTER TABLE ADD COLUMN IF NOT EXISTS`、`CREATE TABLE IF NOT EXISTS`）可重复执行无副作用，不引入 Alembic
3. **渐进式迁移**：先扩展（加列、加表），再回填数据，最后更新写入路径 —— 任何步骤中断都不影响系统可用性
4. **向后兼容读取**：专用列优先，fallback 到 JSONB，兼容回填前的旧数据
5. **PG 单栈优先**：所有存储在 PostgreSQL 内完成（pgvector + 关系表 + JSONB），保持 ACID 事务一致性优势

## 3. 目标用户

**主要用户角色**：neuromem SDK 使用方

| 用户类型 | 描述 | 需求 |
|----------|------|------|
| **neuromem-cloud** | Cloud 服务端，依赖 SDK >= 0.8.0 | Schema 变更后服务无中断，API 兼容 |
| **Me2** | 陪伴式 AI 聊天应用，依赖 SDK == 0.8.0 | 升级 SDK 后现有数据自动迁移，无需手动操作 |
| **第三方开发者** | 直接使用 Python SDK 构建 AI agent | API 行为不变，新 schema 透明 |

**技术舒适度**：中高级 Python 开发者，熟悉 async/await 和 PostgreSQL 基础操作。

**关键需求**：
- 升级 SDK 后 `db.init()` 自动完成所有迁移，无需手动 SQL
- 现有存储的记忆数据不丢失
- 性能不退化（halfvec 迁移实际应带来存储减半和召回速度提升）

## 4. MVP 范围

### 范围内

**Schema 变更**：
- ✅ 表改名：`embeddings` -> `memories`（检测旧表存在时执行 `ALTER TABLE RENAME`）
- ✅ 新增 12 个 trait 专用列（trait_subtype, trait_stage, trait_confidence, trait_context, trait_parent_id, trait_reinforcement_count, trait_contradiction_count, trait_last_reinforced, trait_first_observed, trait_window_start, trait_window_end, trait_derived_from）
- ✅ 新增双时间线列（valid_at, invalid_at, expired_at, updated_at）
- ✅ 新增 content_hash VARCHAR(32)（MD5 去重）
- ✅ 新增实体关联列（subject_entity_id UUID, object_entity_id UUID）
- ✅ 新增 source_episode_ids UUID[]（对话溯源）
- ✅ 旧列兼容处理（valid_from -> valid_at 语义映射）
- ✅ `conversation_sessions` 新增 `last_reflected_at` 列

**辅助表**：
- ✅ `trait_evidence` 表（证据链）
- ✅ `memory_history` 表（变更审计日志）
- ✅ `reflection_cycles` 表（反思周期记录）
- ✅ `memory_sources` 表（记忆-对话关联溯源）

**ORM 模型**：
- ✅ `Embedding` 类重命名为 `Memory`，`__tablename__` 改为 `"memories"`，新增全部字段
- ✅ 新增 `TraitEvidence`、`MemoryHistory`、`ReflectionCycle`、`MemorySource` 四个 ORM 模型
- ✅ 全面更新代码中引用旧模型名/旧表名的地方

**数据回填**：
- ✅ trait metadata JSONB -> 专用列（WHERE memory_type = 'trait' AND trait_subtype IS NULL）
- ✅ `general` -> `fact` 类型迁移
- ✅ `insight` -> `trait`（stage='trend'）类型迁移
- ✅ `content_hash` 回填（MD5(content)）
- ✅ `valid_at` 回填（COALESCE(valid_from, created_at)）

**halfvec 迁移**：
- ✅ 检测 embedding 列类型为 `vector` -> 迁移为 `halfvec(N)`
- ✅ 重建向量索引（HNSW + halfvec_cosine_ops）

**写入路径更新**：
- ✅ `add_memory` 写入时计算 `content_hash = MD5(content)`
- ✅ 写入前 hash 去重检查（同 user_id + 同 memory_type）
- ✅ trait 类型写入时填充 trait_* 专用列
- ✅ 所有写入同时写 metadata JSONB（向后兼容）

**读取兼容**：
- ✅ 搜索结果返回时优先读专用列，fallback 到 JSONB
- ✅ 现有 search API 返回格式不变

**索引更新**：
- ✅ trait 专用索引（stage+confidence, parent, context, window）
- ✅ content_hash 去重索引
- ✅ halfvec 向量索引重建
- ✅ 旧索引清理/更新

### 范围外

- ❌ LIST 分区（P1 阶段，当前保持单表 + 混合 Schema）
- ❌ Reflection 引擎实现（RPIV-2）
- ❌ Trait 生命周期管理逻辑（RPIV-2）
- ❌ LLM 操作判断 ADD/UPDATE/DELETE（RPIV-2）
- ❌ 召回公式改造 / trait_stage_boost（RPIV-2）
- ❌ 物化视图 mv_trait_decayed（P1，需分区支持）
- ❌ fillfactor/autovacuum 调优（P1，需分区支持）
- ❌ 周边表改动（graph_nodes/edges、key_values、emotion_profiles）
- ❌ neuromem-cloud 部署和数据迁移
- ❌ Me2 部署和数据迁移
- ❌ BM25 索引迁移（表名变更后自动跟随或在 db.init() 中重建）

## 5. 用户故事

**US-1**：作为 neuromem SDK 用户，我希望升级到新版本后 `db.init()` 自动完成所有 schema 迁移，以便无需手动执行 SQL 脚本。

- 示例：现有数据库有 `embeddings` 表 -> 升级后 `db.init()` 自动 RENAME 为 `memories`，新增所有列，创建辅助表
- 验证：`db.init()` 执行后，`SELECT * FROM memories LIMIT 1` 可正常返回

**US-2**：作为 neuromem SDK 用户，我希望升级后调用 `ingest()` / `recall()` 行为完全不变，以便我不需要修改任何业务代码。

- 示例：`await nm.ingest(user_id="u1", role="user", content="I work at Google")` 和升级前行为完全一致
- 验证：所有现有测试通过，无需修改测试代码（除了内部实现引用）

**US-3**：作为 neuromem SDK 用户，我希望旧数据中的 `general` 类型记忆自动迁移为 `fact`，`insight` 类型自动迁移为 `trait(trend)`，以便我无需手动处理历史数据。

- 示例：数据库中 memory_type='general' 的行 -> 回填后变为 memory_type='fact'
- 验证：`SELECT COUNT(*) FROM memories WHERE memory_type IN ('general', 'insight')` 返回 0

**US-4**：作为 neuromem SDK 用户，我希望 halfvec 迁移自动完成，以便获得存储空间减半和 <0.3% 的召回精度损失。

- 示例：embedding 列从 `vector(1024)` 自动迁移为 `halfvec(1024)`
- 验证：`SELECT pg_column_size(embedding) FROM memories LIMIT 1` 返回值约为迁移前的一半

**US-5**：作为 neuromem SDK 开发者，我希望有完整的 ORM 模型覆盖所有新表和新列，以便后续 RPIV-2 开发时可以直接使用 SQLAlchemy ORM 操作。

- 示例：`Memory.trait_stage`、`TraitEvidence.quality` 等字段可直接在 SQLAlchemy 查询中使用
- 验证：所有新 ORM 模型通过 `Base.metadata.create_all()` 能正确创建表

**US-6（技术用户故事）**：作为 RPIV-2 的开发者，我希望 RPIV-1 完成后所有 trait 专用列、证据表、反思记录表都已就位，以便我可以直接实现 reflection 引擎和生命周期管理逻辑。

- 示例：`INSERT INTO trait_evidence (trait_id, memory_id, evidence_type, quality) VALUES (...)` 可正常执行
- 验证：四张辅助表存在且结构正确

## 6. 核心架构与模式

### 高级架构

```
NeuroMemory (Facade, _core.py)
  ├── Database (db.py)
  │    ├── init() — 自动迁移（表改名 + 加列 + 辅助表 + 回填 + halfvec + 索引）
  │    └── session() — async session 管理
  ├── Models (models/)
  │    ├── memory.py — Memory (原 Embedding)
  │    ├── trait_evidence.py — TraitEvidence
  │    ├── memory_history.py — MemoryHistory
  │    ├── reflection_cycle.py — ReflectionCycle
  │    └── memory_source.py — MemorySource
  └── Services (services/)
       ├── search.py — 表名 embeddings -> memories
       ├── memory.py — Embedding -> Memory
       ├── memory_extraction.py — Embedding -> Memory
       └── ...其他 services 更新引用
```

### 关键设计模式

1. **幂等迁移模式**：所有 DDL 操作使用 `IF NOT EXISTS` / `IF EXISTS` 语义，`db.init()` 可重复执行
2. **混合 Schema 模式**：热字段（trait 专用列）为专用列，冷字段保留 JSONB，平衡查询性能与灵活性
3. **向后兼容读取模式**：读取时先查专用列，为 NULL 则 fallback 到 JSONB，确保回填前后数据均可正确读取
4. **Facade 不变模式**：`_core.py` 中的公共 API 签名和行为完全不变，变更封装在 db/model/service 层

### 迁移执行顺序（db.init() 内部）

```
Phase 1: 扩展 Schema（非破坏性）
  1.1  检测 embeddings 表 -> RENAME TO memories（幂等）
  1.2  ADD COLUMN IF NOT EXISTS x 20+ 列
  1.3  CREATE TABLE IF NOT EXISTS（4 张辅助表，通过 create_all）
  1.4  ALTER TABLE conversation_sessions ADD COLUMN IF NOT EXISTS last_reflected_at

Phase 2: 数据回填（幂等，WHERE 条件保证只更新未填充行）
  2.1  trait metadata -> 专用列
  2.2  general -> fact
  2.3  insight -> trait(trend)
  2.4  content_hash 回填
  2.5  valid_at 回填

Phase 3: 向量迁移（检测型，已完成则跳过）
  3.1  vector -> halfvec 列类型变更
  3.2  向量索引重建

Phase 4: 索引更新
  4.1  创建 trait 专用索引（IF NOT EXISTS）
  4.2  创建 content_hash 索引
  4.3  更新/重建 BM25 索引（表名变更）
```

## 7. 功能规格

### 7.1 表改名 + 新增列

**输入**：`db.init()` 被调用
**处理**：
1. 检查 `embeddings` 表是否存在（`information_schema.tables`）
2. 存在 -> `ALTER TABLE embeddings RENAME TO memories`
3. 不存在 + `memories` 存在 -> 跳过（已迁移）
4. 都不存在 -> `create_all` 直接创建 `memories`
5. 逐个执行 `ALTER TABLE memories ADD COLUMN IF NOT EXISTS ...`（20+ 列）

**新增列清单**：

| 列名 | 类型 | 用途 |
|------|------|------|
| trait_subtype | VARCHAR(20) | behavior/preference/core |
| trait_stage | VARCHAR(20) | trend/candidate/emerging/established/core/dissolved |
| trait_confidence | REAL | 置信度 |
| trait_context | VARCHAR(20) | work/personal/social/learning/general |
| trait_parent_id | UUID | 父 trait（升级链） |
| trait_reinforcement_count | INTEGER DEFAULT 0 | 强化次数 |
| trait_contradiction_count | INTEGER DEFAULT 0 | 矛盾次数 |
| trait_last_reinforced | TIMESTAMPTZ | 最后强化时间 |
| trait_first_observed | TIMESTAMPTZ | 首次观测时间 |
| trait_window_start | TIMESTAMPTZ | trend 窗口开始 |
| trait_window_end | TIMESTAMPTZ | trend 窗口结束 |
| trait_derived_from | VARCHAR(20) | 产生方式 |
| valid_at | TIMESTAMPTZ | 事件开始成立时间 |
| invalid_at | TIMESTAMPTZ | 事件停止成立时间 |
| expired_at | TIMESTAMPTZ | 被 supersede 的系统时间 |
| content_hash | VARCHAR(32) | MD5 去重 |
| subject_entity_id | UUID | 主语实体 |
| object_entity_id | UUID | 宾语实体 |
| source_episode_ids | UUID[] | 对话溯源 |
| importance | REAL DEFAULT 0.5 | 重要性（如不存在则新增） |

**注意**：`updated_at` 已由 `TimestampMixin` 提供，无需单独添加。

### 7.2 辅助表创建

四张辅助表通过 ORM 模型定义 + `Base.metadata.create_all()` 自动创建，天然幂等。

**trait_evidence**：
```
id          UUID PK DEFAULT gen_random_uuid()
trait_id    UUID NOT NULL           -- 应用层引用 memories.id
memory_id   UUID NOT NULL           -- 支持/矛盾的源记忆
evidence_type VARCHAR(15) NOT NULL  -- supporting / contradicting
quality     CHAR(1) NOT NULL        -- A/B/C/D
created_at  TIMESTAMPTZ DEFAULT NOW()
```

**memory_history**：
```
id          UUID PK DEFAULT gen_random_uuid()
memory_id   UUID NOT NULL
memory_type VARCHAR(50) NOT NULL
event       VARCHAR(20) NOT NULL    -- ADD/UPDATE/DELETE/SUPERSEDE/STAGE_CHANGE
old_content TEXT
new_content TEXT
old_metadata JSONB
new_metadata JSONB
actor       VARCHAR(50) DEFAULT 'system'
created_at  TIMESTAMPTZ DEFAULT NOW()
```

**reflection_cycles**：
```
id                UUID PK DEFAULT gen_random_uuid()
user_id           VARCHAR(255) NOT NULL
trigger_type      VARCHAR(20) NOT NULL
trigger_value     REAL
memories_scanned  INTEGER DEFAULT 0
traits_created    INTEGER DEFAULT 0
traits_updated    INTEGER DEFAULT 0
traits_dissolved  INTEGER DEFAULT 0
started_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
completed_at      TIMESTAMPTZ
status            VARCHAR(20) DEFAULT 'running'
error_message     TEXT
```

**memory_sources**：
```
memory_id       UUID NOT NULL       -- PK 1/2
session_id      UUID NOT NULL       -- PK 2/2
conversation_id UUID                -- 可选，精确到消息
created_at      TIMESTAMPTZ DEFAULT NOW()
```

### 7.3 ORM 模型重写

- `Embedding` 类重命名为 `Memory`，保留 `Embedding` 作为别名（向后兼容导入）
- `__tablename__` 从 `"embeddings"` 改为 `"memories"`
- 新增所有 trait 专用列、双时间线列、content_hash、实体关联列的 ORM 定义
- embedding 列类型从 `Vector` 改为 `HALFVEC`（通过 `pgvector.sqlalchemy` 的 `HalfVec` 类型）
- 更新 `__table_args__` 中的索引定义和约束，包括 `CHECK (memory_type IN ('fact', 'episodic', 'trait', 'document'))` 约束（与 storage-schema-v2.md 一致）
- 全面搜索并更新所有 `.py` 文件中引用 `Embedding` 类、`"embeddings"` 表名的代码

### 7.4 数据回填

所有回填在 `db.init()` 中执行，用 `WHERE ... IS NULL` / `WHERE memory_type = 'xxx'` 保证幂等。

```sql
-- trait metadata -> 专用列
UPDATE memories SET
    trait_subtype = metadata->>'trait_subtype',
    trait_stage = metadata->>'trait_stage',
    trait_confidence = (metadata->>'confidence')::float,
    trait_context = metadata->>'context',
    trait_reinforcement_count = COALESCE((metadata->>'reinforcement_count')::int, 0),
    trait_contradiction_count = COALESCE((metadata->>'contradiction_count')::int, 0),
    trait_derived_from = metadata->>'derived_from'
WHERE memory_type = 'trait' AND trait_subtype IS NULL;

-- general -> fact
UPDATE memories SET memory_type = 'fact' WHERE memory_type = 'general';

-- insight -> trait(trend)
UPDATE memories SET
    memory_type = 'trait',
    trait_stage = 'trend',
    trait_window_start = created_at,
    trait_window_end = created_at + interval '30 days'
WHERE memory_type = 'insight';

-- content_hash
UPDATE memories SET content_hash = MD5(content) WHERE content_hash IS NULL;

-- valid_at
UPDATE memories SET valid_at = COALESCE(valid_from, created_at) WHERE valid_at IS NULL;
```

### 7.5 halfvec 迁移

**检测**：查询 `information_schema.columns` 获取 embedding 列的 `udt_name`，如果是 `vector` 则迁移。

**迁移步骤**：
1. `ALTER TABLE memories ALTER COLUMN embedding TYPE halfvec(N) USING embedding::halfvec(N)`
2. DROP 旧向量索引（如 `idx_embeddings_hnsw`）
3. CREATE 新 HNSW 索引（`halfvec_cosine_ops`）
4. 同步迁移 `conversations` 表的 embedding 列（如果存在向量索引）

### 7.6 写入路径更新

`search.py:add_memory()` 修改：
1. 计算 `content_hash = hashlib.md5(content.encode()).hexdigest()`
2. 写入前查重：`SELECT 1 FROM memories WHERE user_id = :uid AND memory_type = :type AND content_hash = :hash LIMIT 1`
3. 命中 -> NOOP（跳过写入）
4. trait 类型记忆：从 metadata 提取 trait_* 字段填充专用列
5. 所有写入同时填 metadata JSONB（向后兼容）
6. 填充 `valid_at`（取 valid_from 或 NOW()）

`memory_extraction.py:_store_facts/_store_episodes` 修改：
1. 写入时同步填充 `content_hash`
2. 使用新的 `Memory` 模型（替代 `Embedding`）

### 7.7 读取兼容

`search.py:search()` / `scored_search()` 修改：
- SQL 中表名 `embeddings` -> `memories`
- 返回结果中增加专用列字段（trait_stage, trait_subtype 等）
- 读取 trait 信息时：`COALESCE(trait_subtype, metadata->>'trait_subtype')`

### 7.8 索引更新

**新增索引**（全部 `CREATE INDEX IF NOT EXISTS`）：

```sql
-- Trait 专用索引
idx_trait_stage_confidence ON memories (user_id, trait_stage, trait_confidence DESC)
    WHERE trait_stage NOT IN ('dissolved', 'trend')
idx_trait_parent ON memories (trait_parent_id) WHERE trait_parent_id IS NOT NULL
idx_trait_context ON memories (user_id, trait_context) WHERE trait_context IS NOT NULL
idx_trait_window ON memories (trait_window_end)
    WHERE trait_stage = 'trend' AND trait_window_end IS NOT NULL

-- 去重索引
idx_content_hash ON memories (content_hash) WHERE content_hash IS NOT NULL

-- 向量索引（halfvec）
idx_memories_hnsw ON memories USING hnsw (embedding halfvec_cosine_ops)
    WITH (m = 16, ef_construction = 64)
```

**旧索引处理**：表 RENAME 后 PostgreSQL 自动保留索引，索引名不变但作用于新表名。BM25 索引需要在新表名上重建。

## 8. 技术栈

**后端核心**：
- Python 3.11+
- SQLAlchemy 2.0（async ORM）
- asyncpg（PostgreSQL async driver）
- pgvector 0.3+（`pgvector.sqlalchemy` 提供 `Vector` / `HalfVec` 类型）
- PostgreSQL 14+（支持分区表 PK 不含分区键 —— 为 P1 分区预留）

**依赖变更**：
- `pgvector` >= 0.3.0（需要 `HalfVec` 类型支持）

**构建/测试**：
- uv（包管理器）
- pytest + pytest-asyncio（`asyncio_mode = "auto"`）
- Mock providers（无外部 API 依赖的测试）

## 9. 安全与配置

### 配置管理

- **向量维度**：通过 `models/__init__.py` 的 `_embedding_dims` 模块变量控制，由 `NeuroMemory.__init__()` 在 `db.init()` 前设置
- **数据库连接**：通过构造函数传入 `database_url`
- **环境变量**：`EMBEDDING_DIMS`（可选，默认 1024）

### 数据安全

- 所有数据按 `user_id` 隔离，SQL 查询始终包含 `WHERE user_id = :user_id`
- 迁移操作在事务中执行，失败自动回滚
- 无外键到分区表（PG 限制），通过应用层保证引用一致性 + 软删除（设 expired_at 而非物理删除）

### 安全范围

- **范围内**：数据完整性、迁移原子性、用户隔离
- **范围外**：认证授权（由 neuromem-cloud 处理）、传输加密（由基础设施处理）

## 10. API 规范

本项目 **不改变任何公共 API**。以下列出受影响的内部 API：

### 内部 API 变更

| 模块 | 变更 | 影响 |
|------|------|------|
| `models/memory.py` | `Embedding` -> `Memory`（保留 Embedding 别名） | 所有 import Embedding 的文件 |
| `db.py:Database.init()` | 新增迁移逻辑 | 初始化时间略增（首次迁移） |
| `services/search.py` | SQL 中 `embeddings` -> `memories`；add_memory 增加 hash 去重 | 写入可能跳过重复内容 |
| `services/memory.py` | `Embedding` -> `Memory` | 内部类型引用 |
| `services/memory_extraction.py` | `Embedding` -> `Memory` | 内部类型引用 |

### 公共 API 不变保证

```python
# 以下调用在 RPIV-1 前后行为完全一致
await nm.ingest(user_id="u1", role="user", content="I work at Google")
result = await nm.recall(user_id="u1", query="workplace")
await nm.digest(user_id="u1")

# 以下子 Facade 接口行为不变
await nm.kv.get("profile", user_id, "language")
await nm.conversations.list(user_id)
await nm.graph.get_triples(user_id)
```

## 11. 成功标准

### MVP 成功定义

RPIV-1 完成 = 所有现有测试通过 + 新 schema 就位 + 数据回填正确 + 公共 API 行为不变。

### 功能要求

- ✅ `db.init()` 在全新数据库上执行后，`memories` 表和 4 张辅助表正确创建
- ✅ `db.init()` 在已有 `embeddings` 表的数据库上执行后，自动完成 RENAME + 加列 + 回填
- ✅ `db.init()` 可重复执行（幂等），第二次执行无副作用
- ✅ `general` 类型记忆自动迁移为 `fact`
- ✅ `insight` 类型记忆自动迁移为 `trait`（stage='trend'）
- ✅ `content_hash` 正确回填
- ✅ `valid_at` 正确回填
- ✅ embedding 列成功迁移为 halfvec
- ✅ 所有现有测试通过（无需修改测试逻辑，可能需要更新导入路径）
- ✅ 新增 trait 专用列可通过 ORM 正常读写

### 质量指标

- 迁移执行时间：< 30 秒（空数据库），< 5 分钟（10 万条记忆的数据库）
- 查询性能：recall 延迟不增加（halfvec 应略微降低延迟）
- 存储空间：embedding 列存储减少约 50%（halfvec 效果）

### 用户体验目标

- 用户升级 SDK 后执行 `db.init()` 一次即完成所有迁移
- 无需手动执行 SQL 或修改配置
- 无需修改业务代码

## 12. 实施阶段

### Phase 1：ORM 模型 + Schema 扩展

**目标**：完成所有模型定义和非破坏性 schema 变更

**交付物**：
- ✅ `models/memory.py` 重写（Memory 类 + Embedding 别名）
- ✅ `models/trait_evidence.py` 新建
- ✅ `models/memory_history.py` 新建
- ✅ `models/reflection_cycle.py` 新建
- ✅ `models/memory_source.py` 新建
- ✅ `models/__init__.py` 更新导出
- ✅ `db.py:init()` 增加表改名 + 加列逻辑

**验证**：`db.init()` 在全新数据库上创建所有表，在已有数据库上完成扩展

### Phase 2：数据回填 + halfvec 迁移

**目标**：完成数据迁移和向量类型升级

**交付物**：
- ✅ `db.py:init()` 增加数据回填 SQL
- ✅ `db.py:init()` 增加 halfvec 迁移逻辑
- ✅ 向量索引重建

**验证**：回填后旧数据正确映射，halfvec 索引可用

### Phase 3：代码引用更新 + 写入路径

**目标**：更新所有代码引用，实现新写入逻辑

**交付物**：
- ✅ 全面搜索/替换 `Embedding` -> `Memory`、`"embeddings"` -> `"memories"` 的引用
- ✅ `search.py:add_memory()` 增加 hash 去重
- ✅ `search.py` SQL 更新表名
- ✅ `memory_extraction.py` 更新引用
- ✅ 读取兼容层（专用列优先 + JSONB fallback）

**验证**：所有现有测试通过

### Phase 4：索引更新 + 清理

**目标**：创建新索引，清理遗留

**交付物**：
- ✅ 创建 trait 专用索引
- ✅ 创建 content_hash 索引
- ✅ BM25 索引重建
- ✅ 旧索引清理

**验证**：全部测试通过 + 手动验证索引存在

## 13. 未来考虑

### MVP 后增强（RPIV-2）

- Reflection 引擎：扫描 fact/episodic 生成 trait、管理 trait 生命周期
- Trait 生命周期管理：升级/降级/dissolved 全自动化
- LLM 操作判断：ingest 时 LLM 输出 ADD/UPDATE/DELETE/NOOP 指令
- 召回改造：RRF 四维评分（+ trait_stage_boost）
- 乐观锁应用：reflection worker 并发控制

### P1 高级特性

- LIST 分区迁移（单表 -> 4 分区）
- 各分区差异化 fillfactor + autovacuum
- 物化视图 mv_trait_decayed（预计算衰减置信度）
- 定时任务（trend 过期清除、低置信度 dissolved、一致性检查）

### 远期演进

- VectorChord prefilter（向量数据 > 500K 时）
- 图边双时间线
- 两阶段反思（先提问再检索验证）
- 程序性记忆、前瞻记忆

## 14. 风险与缓解措施

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| **表 RENAME 期间并发访问失败** | 短暂服务中断 | 中 | RENAME 是瞬时操作（元数据修改），影响窗口极短；Cloud 部署时安排维护窗口 |
| **halfvec 迁移阻塞** | ALTER COLUMN 持有排他锁，大表耗时 | 中 | 预估数据量，大表考虑分批迁移或 pg_repack；当前数据量（<10 万行）迁移时间 < 1 分钟 |
| **数据回填遗漏** | 旧数据未正确映射到新列 | 低 | WHERE 条件精确匹配；回填后执行一致性校验 SQL；fallback 读取保底 |
| **ORM 引用遗漏** | 运行时 AttributeError | 中 | 全面 grep 搜索 `Embedding`、`embeddings`；保留 Embedding 别名；CI 全量测试 |
| **pgvector 版本不支持 HalfVec** | halfvec 迁移失败 | 低 | 检测 pgvector 版本，不支持则跳过 halfvec 迁移，保持 vector 类型运行 |

## 15. 附录

### 相关文档

| 文档 | 路径 | 说明 |
|------|------|------|
| 记忆分类 V2 设计 | `docs/design/memory-classification-v2.md` | 分类体系、trait 子类、生命周期、置信度模型 |
| 存储方案 V2 设计 | `docs/design/storage-schema-v2.md` | 表结构、索引、迁移路径、检索管道 |
| 需求摘要 | `rpiv/brainstorm-summary-storage-foundation-v2.md` | 9 个核心场景、产品边界 |
| 项目 CLAUDE.md | `CLAUDE.md` | 技术栈、架构、开发约定 |

### 仓库结构（受影响文件）

```
neuromem/
  _core.py                     # Facade: 导入更新
  db.py                        # 迁移逻辑主体
  models/
    __init__.py                # 导出更新
    base.py                    # 不变
    memory.py                  # Embedding -> Memory 重写
    trait_evidence.py           # 新建
    memory_history.py           # 新建
    reflection_cycle.py         # 新建
    memory_source.py            # 新建
    conversation.py             # 不变（ConversationSession 加列在 db.init 中）
    document.py                 # 不变
    emotion_profile.py          # 不变
    graph.py                    # 不变
    kv.py                       # 不变
  services/
    search.py                   # SQL 表名更新 + hash 去重
    memory.py                   # 引用更新
    memory_extraction.py        # 引用更新
    reflection.py               # 引用更新
    temporal.py                 # 不变
    conversation.py             # 不变
    graph.py                    # 不变
    graph_memory.py             # 不变
    kv.py                       # 不变
    files.py                    # 不变
tests/
  conftest.py                   # 引用更新
  test_*.py                     # 可能需要更新 import
```

### RPIV-1 与 V2 设计的对齐矩阵

| V2 设计要素 | RPIV-1 覆盖 | 说明 |
|-------------|-------------|------|
| 4 类分类（fact/episodic/trait/document） | 部分 | schema 支持，分类逻辑在 RPIV-2 |
| trait 三层子类（behavior/preference/core） | 列就位 | trait_subtype 列已创建，逻辑在 RPIV-2 |
| trait 6 阶段生命周期 | 列就位 | trait_stage 列已创建，管理在 RPIV-2 |
| 双时间线 | 列就位 | valid_at/invalid_at/expired_at 列已创建 |
| 证据链 | 表就位 | trait_evidence 表已创建，写入在 RPIV-2 |
| 审计日志 | 表就位 | memory_history 表已创建，写入在 RPIV-2 |
| 反思记录 | 表就位 | reflection_cycles 表已创建，写入在 RPIV-2 |
| 情境标注 | 列就位 | trait_context 列已创建，标注在 RPIV-2 |
| content_hash 去重 | 完全覆盖 | hash 计算 + 写入去重 + 回填 |
| halfvec 量化 | 完全覆盖 | 向量类型迁移 + 索引重建 |
| general/insight 废弃 | 完全覆盖 | 数据回填 + 类型映射 |
