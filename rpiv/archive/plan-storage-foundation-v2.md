---
description: "功能实施计划: storage-foundation-v2"
status: archived
created_at: 2026-02-28T23:00:00
updated_at: 2026-03-02T00:05:00
archived_at: 2026-03-02T00:05:00
related_files:
  - rpiv/requirements/prd-storage-foundation-v2.md
---

# 功能：存储基座 V2（Schema + ORM + 迁移）

以下计划应该是完整的，但在开始实施之前，验证文档和代码库模式以及任务合理性非常重要。

特别注意现有工具、类型和模型的命名。从正确的文件导入等。

## 功能描述

将 neuromem SDK 的存储层从 `embeddings` 单表 + 全 JSONB 架构升级为 `memories` 表 + 混合 Schema（trait 专用列 + JSONB 冷字段），同时新增 4 张辅助表、完成 halfvec 向量迁移和数据回填。所有变更对公共 API 透明，用户升级 SDK 后 `db.init()` 自动完成全部迁移。

## 用户故事

作为 neuromem SDK 用户，我希望升级到新版本后 `db.init()` 自动完成所有 schema 迁移，以便无需手动执行 SQL 且现有代码无需修改。

## 问题陈述

当前 `embeddings` 单表 + 全 JSONB 架构无法为记忆分类 V2 提供 trait 专用列、双时间线、证据链等能力，阻碍 RPIV-2（Reflection 引擎 + Trait 生命周期）的实施。

## 解决方案陈述

在不破坏公共 API 的前提下，通过幂等迁移（ADD COLUMN IF NOT EXISTS + CREATE TABLE IF NOT EXISTS）完成 schema 扩展、ORM 重写、数据回填和向量类型升级，为 V2 分类体系铺设完整的存储基座。

## 功能元数据

**功能类型**：重构
**估计复杂度**：高
**主要受影响的系统**：models/、db.py、services/search.py、services/memory.py、services/memory_extraction.py、services/reflection.py、_core.py
**依赖项**：pgvector >= 0.3.0（Python）、pgvector PG 扩展 >= 0.7.0（halfvec）、SQLAlchemy >= 2.0

---

## 上下文参考

### 相关代码库文件（实施前必读）

- `neuromem/models/memory.py`（全文）- 当前 Embedding ORM 模型，需要完全重写
- `neuromem/models/base.py`（全文）- Base 和 TimestampMixin，Memory 继承这两个
- `neuromem/models/__init__.py`（全文）- 模型导出和 `_embedding_dims` 全局变量
- `neuromem/db.py`（全文）- 数据库初始化，迁移逻辑的主要载体
- `neuromem/services/search.py`（全文）- add_memory 和搜索 SQL，最多硬编码 `embeddings` 的文件
- `neuromem/services/memory.py`（全文）- MemoryService，引用 Embedding 类
- `neuromem/services/memory_extraction.py`（第 690、732、780、834 行）- 去重 SQL 和 Embedding 实例化
- `neuromem/services/reflection.py`（第 14、111 行）- 导入和实例化 Embedding
- `neuromem/_core.py`（第 1410-1450、1505-1560、1645-1680、1720-1740、1765-1770、1905-1935、1980-2040 行）- 硬编码 `embeddings` 表名的 raw SQL
- `neuromem/models/conversation.py`（第 65-91 行）- ConversationSession 模型，需加 last_reflected_at
- `tests/conftest.py`（全文）- 测试 fixture，可能需要更新 import

### 要创建的新文件

- `neuromem/models/trait_evidence.py` - TraitEvidence ORM 模型
- `neuromem/models/memory_history.py` - MemoryHistory ORM 模型
- `neuromem/models/reflection_cycle.py` - ReflectionCycle ORM 模型
- `neuromem/models/memory_source.py` - MemorySource ORM 模型

### 相关设计文档（实施前应阅读）

- `docs/design/storage-schema-v2.md` - 完整 schema 设计（表结构、索引、迁移路径）
- `docs/design/memory-classification-v2.md` - 记忆分类 V2（trait 子类、生命周期、置信度模型）
- `rpiv/brainstorm-summary-storage-foundation-v2.md` - 9 个核心场景
- `rpiv/research-storage-foundation-v2.md` - 技术可行性调研（HALFVEC、RENAME 幂等性等）

### 要遵循的模式

**ORM 模型声明模式**（`neuromem/models/memory.py` 现有模式）：

```python
class ModelName(Base, TimestampMixin):
    __tablename__ = "table_name"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # 字段定义使用 Mapped + mapped_column
    field_name: Mapped[str] = mapped_column(String(255), nullable=False)
    optional_field: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
```

**TimestampMixin 已提供 `created_at` 和 `updated_at`**（`models/base.py`），不要在新模型中重复定义。

**db.init() 幂等迁移模式**（`db.py` 第 63-74 行）：

```python
# 使用 ADD COLUMN IF NOT EXISTS 的幂等 ALTER TABLE
for col_sql in [
    "ALTER TABLE xxx ADD COLUMN IF NOT EXISTS col_name TYPE",
]:
    await conn.execute(text(col_sql))
```

**向量维度动态设置模式**（`models/memory.py` 第 63-65 行）：

```python
@classmethod
def __declare_last__(cls):
    cls.__table__.c.embedding.type = Vector(_models._embedding_dims)
```

**日志模式**：使用 `logger = logging.getLogger(__name__)` 模块级 logger。

**服务类构造模式**（`services/memory.py` 第 23-25 行）：

```python
class ServiceName:
    def __init__(self, db: AsyncSession, embedding: Optional[EmbeddingProvider] = None):
        self.db = db
        self._embedding = embedding
```

---

## 实施计划

### 阶段 1：ORM 模型重写 + 新模型创建

完成 Memory 模型重写和 4 个辅助表模型创建，更新模型导出。

### 阶段 2：数据库迁移逻辑

在 db.py 中实现完整的幂等迁移：表改名、加列、回填、halfvec 迁移、索引更新。

### 阶段 3：代码引用全面更新

将所有 `.py` 文件中的 `Embedding` -> `Memory`、`"embeddings"` -> `"memories"` 引用替换。

### 阶段 4：写入路径增强

在 add_memory 和记忆提取中实现 content_hash 计算和去重逻辑。

---

## 逐步任务

### 任务 1: UPDATE `neuromem/models/memory.py` — 重写 Memory 模型

- **IMPLEMENT**：
  1. 将类名 `Embedding` 重命名为 `Memory`
  2. `__tablename__` 从 `"embeddings"` 改为 `"memories"`
  3. 将 `Vector` 导入改为 `HALFVEC`（从 `pgvector.sqlalchemy` 导入 `HALFVEC`）
  4. `embedding` 列类型从 `Vector(_models._embedding_dims)` 改为 `HALFVEC(_models._embedding_dims)`
  5. 新增以下列定义：

  ```python
  # 双时间线
  valid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
  invalid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
  expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

  # 重要性（如当前不存在则新增）
  importance: Mapped[float] = mapped_column(Float, default=0.5, server_default="0.5", nullable=False)

  # 去重
  content_hash: Mapped[str | None] = mapped_column(String(32), nullable=True)

  # Trait 专用列
  trait_subtype: Mapped[str | None] = mapped_column(String(20), nullable=True)
  trait_stage: Mapped[str | None] = mapped_column(String(20), nullable=True)
  trait_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
  trait_context: Mapped[str | None] = mapped_column(String(20), nullable=True)
  trait_parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
  trait_reinforcement_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
  trait_contradiction_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
  trait_last_reinforced: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
  trait_first_observed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
  trait_window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
  trait_window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
  trait_derived_from: Mapped[str | None] = mapped_column(String(20), nullable=True)

  # 实体关联
  subject_entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
  object_entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

  # 对话溯源
  source_episode_ids: Mapped[list | None] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=True)
  ```

  6. 保留现有列：`valid_from`, `valid_until`, `version`, `superseded_by`, `extracted_timestamp`, `access_count`, `last_accessed_at`
  7. 更新 `__table_args__`：
     - 将 `ix_emb_` 前缀的索引名更新
     - 添加 CHECK 约束（与设计文档 storage-schema-v2.md 一致）：
     ```python
     CheckConstraint(
         "memory_type IN ('fact', 'episodic', 'trait', 'document')",
         name="chk_memory_type",
     ),
     ```
  8. 在文件末尾添加向后兼容别名：`Embedding = Memory`
  9. `__declare_last__` 中将 `Vector` 改为 `HALFVEC`

- **IMPORTS**：
  ```python
  from pgvector.sqlalchemy import HALFVEC  # 替换 Vector
  from sqlalchemy import CheckConstraint, Float  # 新增
  from sqlalchemy.dialects.postgresql import ARRAY  # 新增
  ```

- **GOTCHA**：
  - `TimestampMixin` 已提供 `created_at` 和 `updated_at`，不要重复定义
  - `HALFVEC` 是大写（`pgvector.sqlalchemy.HALFVEC`），不是 `HalfVec`
  - 保留 `valid_from` 和 `valid_until` 列（旧数据兼容），新增 `valid_at` / `invalid_at` / `expired_at`
  - `importance` 列可能已存在于某些数据库中（作为 metadata 字段），需要 ADD COLUMN IF NOT EXISTS
  - `ARRAY(UUID(as_uuid=True))` 需要从 `sqlalchemy.dialects.postgresql` 导入 ARRAY

- **VALIDATE**：`uv run python -c "from neuromem.models.memory import Memory, Embedding; print('OK')"`

### 任务 2: CREATE `neuromem/models/trait_evidence.py`

- **IMPLEMENT**：

  ```python
  """Trait evidence model - evidence chain for trait memories."""

  from __future__ import annotations

  import uuid
  from datetime import datetime

  from sqlalchemy import CheckConstraint, DateTime, Index, String, func
  from sqlalchemy.dialects.postgresql import UUID
  from sqlalchemy.orm import Mapped, mapped_column

  from neuromem.models.base import Base


  class TraitEvidence(Base):
      __tablename__ = "trait_evidence"

      id: Mapped[uuid.UUID] = mapped_column(
          UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
      )
      trait_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
      memory_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
      evidence_type: Mapped[str] = mapped_column(String(15), nullable=False)
      quality: Mapped[str] = mapped_column(String(1), nullable=False)
      created_at: Mapped[datetime] = mapped_column(
          DateTime(timezone=True), server_default=func.now()
      )

      __table_args__ = (
          CheckConstraint(
              "evidence_type IN ('supporting', 'contradicting')",
              name="chk_evidence_type",
          ),
          CheckConstraint("quality IN ('A', 'B', 'C', 'D')", name="chk_quality"),
          Index("idx_evidence_trait", "trait_id", "evidence_type"),
          Index("idx_evidence_memory", "memory_id"),
      )
  ```

- **GOTCHA**：不使用 TimestampMixin（只需要 created_at，不需要 updated_at）
- **VALIDATE**：`uv run python -c "from neuromem.models.trait_evidence import TraitEvidence; print('OK')"`

### 任务 3: CREATE `neuromem/models/memory_history.py`

- **IMPLEMENT**：

  ```python
  """Memory history model - audit log for memory changes."""

  from __future__ import annotations

  import uuid
  from datetime import datetime

  from sqlalchemy import DateTime, Index, String, Text, func
  from sqlalchemy.dialects.postgresql import JSONB, UUID
  from sqlalchemy.orm import Mapped, mapped_column

  from neuromem.models.base import Base


  class MemoryHistory(Base):
      __tablename__ = "memory_history"

      id: Mapped[uuid.UUID] = mapped_column(
          UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
      )
      memory_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
      memory_type: Mapped[str] = mapped_column(String(50), nullable=False)
      event: Mapped[str] = mapped_column(String(20), nullable=False)
      old_content: Mapped[str | None] = mapped_column(Text, nullable=True)
      new_content: Mapped[str | None] = mapped_column(Text, nullable=True)
      old_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
      new_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
      actor: Mapped[str] = mapped_column(String(50), default="system", server_default="'system'")
      created_at: Mapped[datetime] = mapped_column(
          DateTime(timezone=True), server_default=func.now()
      )

      __table_args__ = (
          Index("idx_history_memory", "memory_id", "created_at"),
      )
  ```

- **VALIDATE**：`uv run python -c "from neuromem.models.memory_history import MemoryHistory; print('OK')"`

### 任务 4: CREATE `neuromem/models/reflection_cycle.py`

- **IMPLEMENT**：

  ```python
  """Reflection cycle model - records of reflection engine runs."""

  from __future__ import annotations

  import uuid
  from datetime import datetime

  from sqlalchemy import DateTime, Float, Index, Integer, String, Text, func
  from sqlalchemy.dialects.postgresql import UUID
  from sqlalchemy.orm import Mapped, mapped_column

  from neuromem.models.base import Base


  class ReflectionCycle(Base):
      __tablename__ = "reflection_cycles"

      id: Mapped[uuid.UUID] = mapped_column(
          UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
      )
      user_id: Mapped[str] = mapped_column(String(255), nullable=False)
      trigger_type: Mapped[str] = mapped_column(String(20), nullable=False)
      trigger_value: Mapped[float | None] = mapped_column(Float, nullable=True)
      memories_scanned: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
      traits_created: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
      traits_updated: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
      traits_dissolved: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
      started_at: Mapped[datetime] = mapped_column(
          DateTime(timezone=True), nullable=False, server_default=func.now()
      )
      completed_at: Mapped[datetime | None] = mapped_column(
          DateTime(timezone=True), nullable=True
      )
      status: Mapped[str] = mapped_column(
          String(20), default="running", server_default="'running'"
      )
      error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

      __table_args__ = (
          Index("idx_reflection_user", "user_id", "started_at"),
      )
  ```

- **VALIDATE**：`uv run python -c "from neuromem.models.reflection_cycle import ReflectionCycle; print('OK')"`

### 任务 5: CREATE `neuromem/models/memory_source.py`

- **IMPLEMENT**：

  ```python
  """Memory source model - links memories to conversation sessions."""

  from __future__ import annotations

  import uuid
  from datetime import datetime

  from sqlalchemy import DateTime, Index, func
  from sqlalchemy.dialects.postgresql import UUID
  from sqlalchemy.orm import Mapped, mapped_column

  from neuromem.models.base import Base


  class MemorySource(Base):
      __tablename__ = "memory_sources"

      memory_id: Mapped[uuid.UUID] = mapped_column(
          UUID(as_uuid=True), primary_key=True
      )
      session_id: Mapped[uuid.UUID] = mapped_column(
          UUID(as_uuid=True), primary_key=True
      )
      conversation_id: Mapped[uuid.UUID | None] = mapped_column(
          UUID(as_uuid=True), nullable=True
      )
      created_at: Mapped[datetime] = mapped_column(
          DateTime(timezone=True), server_default=func.now()
      )

      __table_args__ = (
          Index("idx_sources_session", "session_id"),
      )
  ```

- **VALIDATE**：`uv run python -c "from neuromem.models.memory_source import MemorySource; print('OK')"`

### 任务 6: UPDATE `neuromem/models/__init__.py` — 更新模型导出

- **IMPLEMENT**：
  1. 更新 `from neuromem.models.memory import Embedding` 为 `from neuromem.models.memory import Memory, Embedding`
  2. 添加新模型导入：
     ```python
     from neuromem.models.trait_evidence import TraitEvidence
     from neuromem.models.memory_history import MemoryHistory
     from neuromem.models.reflection_cycle import ReflectionCycle
     from neuromem.models.memory_source import MemorySource
     ```
  3. 更新 `__all__` 列表，添加 `"Memory"`, `"TraitEvidence"`, `"MemoryHistory"`, `"ReflectionCycle"`, `"MemorySource"`
  4. 保留 `"Embedding"` 在 `__all__` 中（向后兼容）

- **VALIDATE**：`uv run python -c "from neuromem.models import Memory, Embedding, TraitEvidence, MemoryHistory, ReflectionCycle, MemorySource; print('OK')"`

### 任务 7: UPDATE `neuromem/db.py` — 实现完整迁移逻辑

- **IMPLEMENT**：重写 `Database.init()` 方法，实现以下迁移步骤：

  **Step 1：创建扩展**
  ```python
  await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
  ```

  **Step 2：检测表状态 + 改名**
  ```python
  has_embeddings = (await conn.execute(
      text("SELECT to_regclass('embeddings') IS NOT NULL")
  )).scalar()
  has_memories = (await conn.execute(
      text("SELECT to_regclass('memories') IS NOT NULL")
  )).scalar()

  if has_embeddings and not has_memories:
      await conn.execute(text("ALTER TABLE embeddings RENAME TO memories"))
      logger.info("Renamed table 'embeddings' to 'memories'")
  elif has_embeddings and has_memories:
      raise RuntimeError("Both 'embeddings' and 'memories' tables exist")
  ```

  **Step 3：create_all（创建新表 + 缺失的表）**
  ```python
  await conn.run_sync(Base.metadata.create_all)
  ```

  **Step 4：ADD COLUMN IF NOT EXISTS（幂等加列）**
  对 `memories` 表执行所有新列的 ADD COLUMN：
  ```python
  migration_columns = [
      # 双时间线
      "ALTER TABLE memories ADD COLUMN IF NOT EXISTS valid_at TIMESTAMPTZ",
      "ALTER TABLE memories ADD COLUMN IF NOT EXISTS invalid_at TIMESTAMPTZ",
      "ALTER TABLE memories ADD COLUMN IF NOT EXISTS expired_at TIMESTAMPTZ",
      # content_hash
      "ALTER TABLE memories ADD COLUMN IF NOT EXISTS content_hash VARCHAR(32)",
      # importance（可能已存在）
      "ALTER TABLE memories ADD COLUMN IF NOT EXISTS importance REAL DEFAULT 0.5",
      # trait 专用列（12 列）
      "ALTER TABLE memories ADD COLUMN IF NOT EXISTS trait_subtype VARCHAR(20)",
      "ALTER TABLE memories ADD COLUMN IF NOT EXISTS trait_stage VARCHAR(20)",
      "ALTER TABLE memories ADD COLUMN IF NOT EXISTS trait_confidence REAL",
      "ALTER TABLE memories ADD COLUMN IF NOT EXISTS trait_context VARCHAR(20)",
      "ALTER TABLE memories ADD COLUMN IF NOT EXISTS trait_parent_id UUID",
      "ALTER TABLE memories ADD COLUMN IF NOT EXISTS trait_reinforcement_count INTEGER DEFAULT 0",
      "ALTER TABLE memories ADD COLUMN IF NOT EXISTS trait_contradiction_count INTEGER DEFAULT 0",
      "ALTER TABLE memories ADD COLUMN IF NOT EXISTS trait_last_reinforced TIMESTAMPTZ",
      "ALTER TABLE memories ADD COLUMN IF NOT EXISTS trait_first_observed TIMESTAMPTZ",
      "ALTER TABLE memories ADD COLUMN IF NOT EXISTS trait_window_start TIMESTAMPTZ",
      "ALTER TABLE memories ADD COLUMN IF NOT EXISTS trait_window_end TIMESTAMPTZ",
      "ALTER TABLE memories ADD COLUMN IF NOT EXISTS trait_derived_from VARCHAR(20)",
      # 实体关联
      "ALTER TABLE memories ADD COLUMN IF NOT EXISTS subject_entity_id UUID",
      "ALTER TABLE memories ADD COLUMN IF NOT EXISTS object_entity_id UUID",
      # 对话溯源
      "ALTER TABLE memories ADD COLUMN IF NOT EXISTS source_episode_ids UUID[]",
      # 旧迁移兼容（保留现有 db.init 的逻辑）
      "ALTER TABLE memories ADD COLUMN IF NOT EXISTS valid_from TIMESTAMPTZ",
      "ALTER TABLE memories ADD COLUMN IF NOT EXISTS valid_until TIMESTAMPTZ",
      "ALTER TABLE memories ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1",
      "ALTER TABLE memories ADD COLUMN IF NOT EXISTS superseded_by UUID",
  ]
  for col_sql in migration_columns:
      await conn.execute(text(col_sql))
  ```

  **Step 5：conversation_sessions 加列**
  ```python
  await conn.execute(text(
      "ALTER TABLE conversation_sessions ADD COLUMN IF NOT EXISTS last_reflected_at TIMESTAMPTZ"
  ))
  ```

  **Step 6：数据回填（幂等）**
  ```python
  # general -> fact
  await conn.execute(text(
      "UPDATE memories SET memory_type = 'fact' WHERE memory_type = 'general'"
  ))
  # insight -> trait(trend)
  await conn.execute(text("""
      UPDATE memories SET
          memory_type = 'trait',
          trait_stage = 'trend',
          trait_window_start = created_at,
          trait_window_end = created_at + interval '30 days'
      WHERE memory_type = 'insight'
  """))
  # trait metadata -> 专用列
  await conn.execute(text("""
      UPDATE memories SET
          trait_subtype = metadata->>'trait_subtype',
          trait_stage = COALESCE(trait_stage, metadata->>'trait_stage'),
          trait_confidence = (metadata->>'confidence')::float,
          trait_context = metadata->>'context',
          trait_reinforcement_count = COALESCE((metadata->>'reinforcement_count')::int, 0),
          trait_contradiction_count = COALESCE((metadata->>'contradiction_count')::int, 0),
          trait_derived_from = metadata->>'derived_from'
      WHERE memory_type = 'trait' AND trait_subtype IS NULL
        AND metadata->>'trait_subtype' IS NOT NULL
  """))
  # content_hash 回填
  await conn.execute(text(
      "UPDATE memories SET content_hash = MD5(content) WHERE content_hash IS NULL"
  ))
  # valid_at 回填
  await conn.execute(text(
      "UPDATE memories SET valid_at = COALESCE(valid_from, created_at) WHERE valid_at IS NULL"
  ))
  ```

  **Step 7：halfvec 迁移**
  ```python
  # 检测 pgvector 扩展版本
  pgvector_version = (await conn.execute(text(
      "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
  ))).scalar()

  can_halfvec = False
  if pgvector_version:
      major, minor = pgvector_version.split('.')[:2]
      can_halfvec = (int(major), int(minor)) >= (0, 7)

  if can_halfvec:
      # 检测当前列类型
      col_type = (await conn.execute(text("""
          SELECT udt_name FROM information_schema.columns
          WHERE table_name = 'memories' AND column_name = 'embedding'
      """))).scalar()

      if col_type == 'vector':
          dims = _models._embedding_dims
          await conn.execute(text(
              f"ALTER TABLE memories ALTER COLUMN embedding "
              f"TYPE halfvec({dims}) USING embedding::halfvec({dims})"
          ))
          logger.info(f"Migrated embedding column to halfvec({dims})")
  ```

  **Step 8：索引更新**
  ```python
  index_sqls = [
      # Trait 专用索引
      """CREATE INDEX IF NOT EXISTS idx_trait_stage_confidence
         ON memories (user_id, trait_stage, trait_confidence DESC)
         WHERE trait_stage NOT IN ('dissolved', 'trend')""",
      """CREATE INDEX IF NOT EXISTS idx_trait_parent
         ON memories (trait_parent_id) WHERE trait_parent_id IS NOT NULL""",
      """CREATE INDEX IF NOT EXISTS idx_trait_context
         ON memories (user_id, trait_context) WHERE trait_context IS NOT NULL""",
      """CREATE INDEX IF NOT EXISTS idx_trait_window
         ON memories (trait_window_end)
         WHERE trait_stage = 'trend' AND trait_window_end IS NOT NULL""",
      # 去重索引
      """CREATE INDEX IF NOT EXISTS idx_content_hash
         ON memories (user_id, memory_type, content_hash)
         WHERE content_hash IS NOT NULL""",
      # valid_at 索引
      """CREATE INDEX IF NOT EXISTS ix_mem_user_valid_at
         ON memories (user_id, valid_at, invalid_at)""",
  ]
  for idx_sql in index_sqls:
      await conn.execute(text(idx_sql))
  ```

  **Step 9：向量索引重建（halfvec 迁移后）**
  如果完成了 halfvec 迁移，需要 DROP 旧向量索引并创建新的：
  ```python
  if can_halfvec and col_type == 'vector':
      # 查找并删除旧的 vector 索引
      old_indexes = (await conn.execute(text("""
          SELECT indexname FROM pg_indexes
          WHERE tablename = 'memories'
            AND indexdef LIKE '%vector_cosine_ops%'
      """))).fetchall()
      for idx in old_indexes:
          await conn.execute(text(f"DROP INDEX IF EXISTS {idx.indexname}"))

      # 创建新 halfvec HNSW 索引
      await conn.execute(text(f"""
          CREATE INDEX IF NOT EXISTS idx_memories_hnsw
          ON memories USING hnsw (embedding halfvec_cosine_ops)
          WITH (m = 16, ef_construction = 64)
      """))
  ```

  **Step 10：保留现有迁移逻辑**
  - 保留 conversations 表的 extraction_status 相关迁移代码
  - 更新 BM25 索引创建（表名 embeddings -> memories）

- **PATTERN**：现有 db.py 第 59-91 行的幂等迁移模式
- **IMPORTS**：添加 `import neuromem.models.trait_evidence`、`import neuromem.models.memory_history` 等 noqa 导入
- **GOTCHA**：
  - 表改名必须在 `create_all` 之前执行，否则 create_all 会创建一个新的空 `memories` 表
  - halfvec 迁移需要在 create_all 之后执行（因为 create_all 会根据 ORM 模型创建 halfvec 列，但旧数据库中列类型是 vector）
  - `_models._embedding_dims` 的维度修正逻辑需要更新，将 `Vector` 改为 `HALFVEC`
  - BM25 索引表名需要从 embeddings 改为 memories

- **VALIDATE**：`cd D:/CODE/NeuroMem && uv run python -c "from neuromem.db import Database; print('OK')"`

### 任务 8: UPDATE `neuromem/services/search.py` — 更新表名 + 引用 + hash 去重

- **IMPLEMENT**：
  1. 将 `from neuromem.models.memory import Embedding` 改为 `from neuromem.models.memory import Memory, Embedding`（或直接用 Memory）
  2. 将所有 SQL 字符串中的 `embeddings` 替换为 `memories`（约 8 处）：
     - `search()` 方法中的 vector_ranked CTE：`FROM embeddings` -> `FROM memories`
     - `search()` 方法中的 bm25_ranked CTE：`FROM embeddings` -> `FROM memories`（pg_search 和 tsvector 两个分支）
     - `scored_search()` 方法中同样的位置（约 6 处 SQL）
     - `_update_access_tracking()` 方法中的 UPDATE SQL
  3. `add_memory()` 方法：
     - 在创建 `Embedding()` 实例处改为 `Memory()`
     - 在创建实例前添加 content_hash 计算和去重：
     ```python
     import hashlib
     content_hash = hashlib.md5(content.encode()).hexdigest()

     # Hash-based dedup check
     dup_check = await self.db.execute(
         text("SELECT 1 FROM memories WHERE user_id = :uid AND memory_type = :mtype AND content_hash = :hash LIMIT 1"),
         {"uid": user_id, "mtype": memory_type, "hash": content_hash},
     )
     if dup_check.fetchone():
         logger.debug("Skipping duplicate memory (hash match): %s", content[:80])
         return None  # 或返回现有记忆
     ```
     - 在创建 Memory 实例时添加 `content_hash=content_hash` 和 `valid_at=valid_from or datetime.now(timezone.utc)`
  4. 更新 `add_memory` 返回类型标注：`Embedding` -> `Memory`（返回可能为 None，改为 `Optional[Memory]`）

- **GOTCHA**：
  - `add_memory` 返回类型变更可能影响调用方，但 _core.py 中检查的是 attribute 不是类型
  - SQL 中仍使用 `vector` 类型字面量（`'{vector_str}'::vector`）—— halfvec 迁移后需要改为 `::halfvec`。但要考虑混合场景：新安装直接是 halfvec，旧安装可能还是 vector。建议：根据列类型动态选择 cast 类型，或者统一用 `embedding <=> '{vector_str}'` 不带 cast（PG 自动匹配）
  - 最安全的做法：去掉 `::vector` cast，让 PG 自动推断类型

- **VALIDATE**：`uv run python -c "from neuromem.services.search import SearchService; print('OK')"`

### 任务 9: UPDATE `neuromem/services/memory.py` — 更新 Embedding 引用

- **IMPLEMENT**：
  1. 将 `from neuromem.models.memory import Embedding` 改为 `from neuromem.models.memory import Memory`
  2. 将文件中所有 `Embedding.` 引用改为 `Memory.`（约 20 处）
  3. 将类型标注中的 `Embedding` 改为 `Memory`（如 `list[Embedding]` -> `list[Memory]`）
  4. 将 `select(Embedding)` 改为 `select(Memory)`
  5. 将 `select(func.count()).select_from(Embedding)` 改为 `select(func.count()).select_from(Memory)`

- **GOTCHA**：注意不要改到 `EmbeddingProvider` 的引用
- **VALIDATE**：`uv run python -c "from neuromem.services.memory import MemoryService; print('OK')"`

### 任务 10: UPDATE `neuromem/services/memory_extraction.py` — 更新引用 + SQL

- **IMPLEMENT**：
  1. 将 `from neuromem.models.memory import Embedding` 改为 `from neuromem.models.memory import Memory`
  2. `_store_facts()` 方法（第 690 行附近）：
     - 去重 SQL 中 `FROM embeddings` -> `FROM memories`
     - `embedding_obj = Embedding(...)` -> `embedding_obj = Memory(...)`
     - 添加 `content_hash` 到创建参数：
       ```python
       import hashlib
       content_hash = hashlib.md5(content.encode()).hexdigest()
       ```
     - 在 Memory 实例化时添加 `content_hash=content_hash`、`valid_at=datetime.now(timezone.utc)`
  3. `_store_episodes()` 方法（第 780 行附近）：同样的更改
  4. 考虑将去重方式从向量相似度（cosine > 0.95）改为 hash 去重 + 向量二次确认：
     - 先查 content_hash 是否存在
     - 存在则跳过（NOOP）
     - 不存在再做向量去重（保留现有逻辑作为安全网）

- **GOTCHA**：
  - 去重 SQL 中的 `::vector` cast 同任务 8 的处理
  - `valid_from` 参数在 Memory 实例化中保留（旧字段兼容）
- **VALIDATE**：`uv run python -c "from neuromem.services.memory_extraction import MemoryExtractionService; print('OK')"`

### 任务 11: UPDATE `neuromem/services/reflection.py` — 更新引用

- **IMPLEMENT**：
  1. 将 `from neuromem.models.memory import Embedding` 改为 `from neuromem.models.memory import Memory`
  2. `embedding_obj = Embedding(...)` 改为 `embedding_obj = Memory(...)`（第 111 行附近）

- **VALIDATE**：`uv run python -c "from neuromem.services.reflection import ReflectionService; print('OK')"`

### 任务 12: UPDATE `neuromem/_core.py` — 更新所有硬编码表名

- **IMPLEMENT**：
  1. 全面搜索替换所有 raw SQL 中的 `embeddings` -> `memories`（约 20+ 处）：
     - `delete_user_data()`（第 1724 行）：`("embeddings", "user_id")` -> `("memories", "user_id")`
     - `_recall_memories()`（第 1410 行附近）：`FROM embeddings` -> `FROM memories`
     - `_supersede_memory()`（第 1429、1444 行附近）：`UPDATE embeddings` -> `UPDATE memories`
     - `digest()`（第 1511、1527、1556 行附近）：`FROM embeddings` -> `FROM memories`
     - `_invalidate_memory()` / `_restore_memory()`（第 1650、1668、1678 行附近）
     - `_export_user_data()`（第 1769 行附近）
     - `_get_user_stats()` / `_get_user_memories()`（第 1909、1917、1928 行附近）
     - `debug_recall()`（第 1986、2037 行附近）
  2. 更新 docstring 中的 `embeddings` 引用（第 1715-1719 行）
  3. 如果有 `from neuromem.models.memory import Embedding` 导入，更新为 `Memory`（检查实际 import）

- **GOTCHA**：
  - `_core.py` 中的 SQL 很多使用 `f"..."` 格式字符串，注意不要改到变量名
  - `delete_user_data` 中新增 4 张辅助表的清理：
    ```python
    tables = [
        ("memories", "user_id"),
        ("trait_evidence", None),  # 需要 JOIN 或子查询
        ("memory_history", None),  # 同上
        ("memory_sources", None),  # 同上
        ("reflection_cycles", "user_id"),
        ...
    ]
    ```
    但 trait_evidence / memory_history / memory_sources 没有 user_id 列，需要通过 memory_id 关联删除。建议：暂时不在 delete_user_data 中清理辅助表（RPIV-1 不写入这些表），留到 RPIV-2 补充。

- **VALIDATE**：`uv run python -c "from neuromem._core import NeuroMemory; print('OK')"`

### 任务 13: UPDATE `neuromem/_core.py` — 更新 SQL 中的 vector cast

- **IMPLEMENT**：
  在所有 raw SQL 中，将 `'{vector_str}'::vector` 中的显式 `::vector` cast 去掉，直接使用 `'{vector_str}'`，让 PG 根据列类型自动推断。或者保留 cast 但动态选择类型。

  推荐方案：在 _core.py 和 search.py 中统一去掉 `::vector` 后缀。PG 在比较 `embedding <=> '{...}'` 时会根据 embedding 列的实际类型（vector 或 halfvec）自动 cast 字面量。

  需要搜索所有 `::vector` 并替换：
  - `search.py` 中约 4 处
  - `_core.py` 中的 recall 相关 SQL

- **GOTCHA**：确认 PG 在 halfvec 列上做 `<=>` 操作时，文本字面量是否需要显式 cast。如果需要，则使用动态 cast：
  ```python
  # 在 Database 类或配置中存储当前向量类型
  vec_type = "halfvec" if can_halfvec else "vector"
  # SQL 中使用 f"'{vector_str}'::{vec_type}(N)"
  ```

- **VALIDATE**：运行现有测试确认搜索功能正常

### 任务 14: UPDATE `tests/conftest.py` — 更新导入

- **IMPLEMENT**：
  1. 如果有 `from neuromem.models.memory import Embedding` 的导入，更新为包含 Memory
  2. 确保新模型被导入以注册到 Base.metadata：
     ```python
     import neuromem.models.trait_evidence  # noqa: F401
     import neuromem.models.memory_history  # noqa: F401
     import neuromem.models.reflection_cycle  # noqa: F401
     import neuromem.models.memory_source  # noqa: F401
     ```

- **GOTCHA**：conftest.py 中的 `db_session` fixture 使用 `Base.metadata.drop_all` + `create_all`，新模型的表会自动创建/删除
- **VALIDATE**：`cd D:/CODE/NeuroMem && uv run pytest tests/test_search.py -x -v --timeout=30 2>&1 | head -30`

### 任务 15: UPDATE 测试文件 — 更新 `embeddings` 表名引用

- **IMPLEMENT**：
  1. 搜索所有测试文件中对 `embeddings` 的引用（主要是 raw SQL 断言）
  2. 搜索所有测试文件中对 `from neuromem.models.memory import Embedding` 的导入
  3. 更新为 `memories` 和 `Memory`（保留 Embedding 别名也可以，但测试中最好直接用新名）

  受影响文件（12 个）：
  - `test_search.py`
  - `test_recall.py`
  - `test_recall_emotion.py`
  - `test_reflection.py`
  - `test_memory_time.py`
  - `test_memory_analytics.py`
  - `test_memory_extraction.py`
  - `test_temporal_memory.py`
  - `test_time_travel.py`
  - `test_transaction_consistency.py`
  - `test_data_lifecycle.py`
  - `test_conversation_recall.py`

- **GOTCHA**：测试中可能有 `SELECT * FROM embeddings` 之类的 raw SQL，需要全部更新
- **VALIDATE**：`cd D:/CODE/NeuroMem && uv run pytest tests/ -x --timeout=60 2>&1 | tail -20`

---

## 测试策略

### 单元测试

现有测试应全部通过，无需新增测试文件（RPIV-1 不新增功能逻辑，只做 schema 改造）。

测试覆盖的场景：
- `test_search.py`: add_memory + search/scored_search
- `test_recall.py`: recall 端到端
- `test_memory_extraction.py`: 记忆提取 + 去重
- `test_reflection.py`: digest/反思
- `test_time_travel.py`: 时间旅行查询
- `test_data_lifecycle.py`: 数据生命周期

### 集成测试

在全部代码更新完成后，运行完整测试套件验证无回归：
```bash
cd D:/CODE/NeuroMem && uv run pytest tests/ -v --timeout=120
```

### 边缘情况

1. **全新数据库**：`db.init()` 在空数据库上直接创建 memories 表 + 辅助表
2. **已有 embeddings 表**：`db.init()` 自动 RENAME + 加列 + 回填
3. **已迁移数据库**：`db.init()` 幂等执行，无副作用
4. **halfvec 不支持**：pgvector < 0.7.0 时跳过 halfvec 迁移，保持 vector 类型
5. **空表回填**：没有数据时回填 SQL 影响 0 行，不报错

---

## 验证命令

### 级别 1：语法检查

```bash
cd D:/CODE/NeuroMem && uv run python -c "
from neuromem.models import Memory, Embedding, TraitEvidence, MemoryHistory, ReflectionCycle, MemorySource
from neuromem.db import Database
from neuromem.services.search import SearchService
from neuromem.services.memory import MemoryService
from neuromem.services.memory_extraction import MemoryExtractionService
from neuromem.services.reflection import ReflectionService
from neuromem._core import NeuroMemory
print('All imports OK')
"
```

### 级别 2：单元测试（快速子集）

```bash
cd D:/CODE/NeuroMem && uv run pytest tests/test_search.py -x -v --timeout=30
cd D:/CODE/NeuroMem && uv run pytest tests/test_recall.py -x -v --timeout=30
```

### 级别 3：完整测试套件

```bash
cd D:/CODE/NeuroMem && uv run pytest tests/ -v --timeout=120
```

### 级别 4：手动验证

```bash
# 验证 db.init() 在全新数据库上的行为
cd D:/CODE/NeuroMem && uv run python -c "
import asyncio
from neuromem import NeuroMemory
from tests.conftest import MockEmbeddingProvider, MockLLMProvider

async def test():
    nm = NeuroMemory(
        database_url='postgresql+asyncpg://neuromem:neuromem@localhost:5436/neuromem',
        embedding=MockEmbeddingProvider(),
        llm=MockLLMProvider(),
    )
    await nm.init()
    # 验证基本操作
    await nm.ingest(user_id='test_v2', role='user', content='Hello V2')
    result = await nm.recall(user_id='test_v2', query='V2')
    print(f'Recall results: {len(result.get(\"memories\", []))} memories')
    await nm.close()
    print('Manual verification passed')

asyncio.run(test())
"
```

---

## 验收标准

- [ ] `db.init()` 在全新数据库上创建 `memories` 表 + 4 张辅助表
- [ ] `db.init()` 在已有 `embeddings` 表的数据库上完成 RENAME + 加列 + 回填
- [ ] `db.init()` 可重复执行（幂等），第二次无副作用
- [ ] `general` -> `fact`、`insight` -> `trait(trend)` 回填正确
- [ ] `content_hash` 和 `valid_at` 回填正确
- [ ] ORM 模型可正常 import 和使用
- [ ] 所有现有测试通过（`pytest tests/ -v` 全绿）
- [ ] 公共 API（ingest/recall/digest）行为不变
- [ ] 代码中无 `embeddings` 表名硬编码（除了向后兼容别名注释）
- [ ] halfvec 迁移在 pgvector >= 0.7.0 时正确执行

---

## 完成检查清单

- [ ] 所有 15 个任务按顺序完成
- [ ] 每个任务的 VALIDATE 命令通过
- [ ] 完整测试套件通过
- [ ] 手动验证 db.init() + ingest/recall 正常
- [ ] 无 lint 或类型错误
- [ ] 所有验收标准满足

---

## 备注

### 设计决策

1. **保留 Embedding 别名**：在 `memory.py` 中 `Embedding = Memory`，避免破坏外部依赖（如 neuromem-cloud）的导入
2. **不引入 Alembic**：保持现有 `db.init()` 幂等迁移模式，降低复杂度
3. **content_hash 在 Python 侧计算**：使用 `hashlib.md5` 而非 PG `MD5()` 函数，减少 DB 交互
4. **halfvec 迁移检测**：先检测 pgvector 版本，不满足则跳过，保证向后兼容
5. **去掉 SQL 中的显式 ::vector cast**：让 PG 自动推断类型，兼容 vector 和 halfvec 两种部署
6. **辅助表暂不在 delete_user_data 中清理**：RPIV-1 不写入辅助表，留到 RPIV-2 补充
7. **content_hash 去重索引改为复合索引**（user_id + memory_type + content_hash）：去重是同用户同类型内的去重

### 执行顺序依赖

```
任务 1 (Memory 模型) → 任务 6 (__init__.py) → 任务 7 (db.py)
任务 2-5 (辅助模型) → 任务 6 (__init__.py)
任务 7 (db.py) → 任务 8-13 (services + _core.py)
任务 8-13 → 任务 14-15 (测试更新)
```

### 信心评分：8/10

高信心理由：
- 技术调研已验证所有关键点（HALFVEC、RENAME、UUID[]）
- 变更范围清晰（schema + ORM + 引用替换）
- 幂等迁移模式成熟

风险因素：
- `_core.py` 中 raw SQL 数量多（约 20 处），遗漏替换可能导致运行时错误
- halfvec 迁移对 PG 端扩展版本有硬性要求
- SQL 中 `::vector` cast 的移除需要确认 PG 在 halfvec 列上的自动推断行为
