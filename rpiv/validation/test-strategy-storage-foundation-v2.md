---
description: "测试策略 + 测试规格: RPIV-1 存储基座（Schema + ORM + 迁移）"
status: complete
created_at: 2026-02-28T23:00:00
updated_at: 2026-02-28T23:30:00
---

# 测试策略 + 测试规格：RPIV-1 存储基座

**权威参考文档**：
- `docs/design/storage-schema-v2.md`（存储方案 V2）
- `docs/design/memory-classification-v2.md`（记忆分类 V2）
- `rpiv/requirements/prd-storage-foundation-v2.md`（PRD）

## 1. 测试范围总览

| 测试类别 | PRD 章节 | 优先级 | 测试文件 |
|----------|---------|--------|----------|
| Schema 迁移 | 7.1, 7.2, 7.8 | P0 | `test_storage_v2_migration.py` |
| ORM 模型 | 7.3 | P0 | `test_storage_v2_orm.py` |
| 数据回填 | 7.4 | P0 | `test_storage_v2_backfill.py` |
| halfvec 迁移 | 7.5 | P0 | `test_storage_v2_halfvec.py` |
| 写入路径 | 7.6 | P0 | `test_storage_v2_write.py` |
| 读取兼容 | 7.7 | P0 | `test_storage_v2_read.py` |
| 向后兼容 | 全部 | P0 | `test_storage_v2_compat.py` |

## 2. 测试框架与约定

### 2.1 技术栈

- **框架**: pytest + pytest-asyncio
- **数据库**: PostgreSQL localhost:5436（测试专用）
- **Session**: function scope，测试结束 rollback（沿用 conftest.py 模式）
- **Mock**: MockEmbeddingProvider（1024 维确定性假向量）、MockLLMProvider

### 2.2 Fixture 策略

沿用现有 fixture（db_session、nm、mock_embedding、mock_llm），新增：

```python
@pytest_asyncio.fixture
async def v1_db_session(db_engine):
    """创建 V1 schema 的数据库 session（embeddings 表 + vector 类型）。
    用于迁移测试：先建立旧 schema，再执行迁移验证。"""

@pytest_asyncio.fixture
async def v1_data(v1_db_session):
    """预填充 V1 格式数据：general/insight/episodic/fact 类型，
    metadata 含 trait_subtype/confidence 等待回填的字段。"""
```

### 2.3 用户故事-测试用例追溯矩阵

| 用户故事 | 覆盖测试 |
|----------|---------|
| US-1: db.init() 自动迁移 | migration 全部 + backfill 全部 + halfvec 全部 |
| US-2: API 行为不变 | compat 全部 + 回归测试 |
| US-3: general/insight 自动迁移 | backfill: test_backfill_general_to_fact, test_backfill_insight_to_trait_trend |
| US-4: halfvec 自动完成 | halfvec 全部 |
| US-5: ORM 覆盖新表新列 | orm 全部 |
| US-6: RPIV-2 基础设施就位 | orm: 辅助表 CRUD |

---

## 3. 测试规格

### 3.1 Schema 迁移测试 (`test_storage_v2_migration.py`)

#### TC-M01: test_rename_embeddings_to_memories
- **前置**: 数据库存在 `embeddings` 表，含 3 条数据
- **操作**: 执行 db.init() 迁移逻辑
- **验收标准**:
  - `information_schema.tables` 中 `memories` 存在，`embeddings` 不存在
  - `SELECT COUNT(*) FROM memories` == 3
  - 原数据 content/user_id/memory_type 完整保留

#### TC-M02: test_rename_idempotent
- **前置**: `memories` 表已存在（已迁移过）
- **操作**: 执行 db.init() 迁移逻辑两次
- **验收标准**: 第二次执行无异常，数据不变

#### TC-M03: test_fresh_install_creates_memories
- **前置**: 空数据库（无 embeddings 也无 memories）
- **操作**: 执行 db.init()
- **验收标准**: `memories` 表存在，`embeddings` 不存在

#### TC-M04: test_add_trait_columns
- **前置**: `memories` 表存在但无 trait 列
- **操作**: 执行 ADD COLUMN 迁移
- **验收标准**: 通过 `information_schema.columns` 验证以下 12 列存在且类型正确：

| 列名 | 期望类型（udt_name） | 期望默认值 |
|------|---------------------|-----------|
| trait_subtype | varchar | NULL |
| trait_stage | varchar | NULL |
| trait_confidence | float4 | NULL |
| trait_context | varchar | NULL |
| trait_parent_id | uuid | NULL |
| trait_reinforcement_count | int4 | 0 |
| trait_contradiction_count | int4 | 0 |
| trait_last_reinforced | timestamptz | NULL |
| trait_first_observed | timestamptz | NULL |
| trait_window_start | timestamptz | NULL |
| trait_window_end | timestamptz | NULL |
| trait_derived_from | varchar | NULL |

#### TC-M05: test_add_timeline_columns
- **验收标准**: valid_at/invalid_at/expired_at 列存在，类型 `timestamptz`，允许 NULL

#### TC-M06: test_add_content_hash_column
- **验收标准**: content_hash 列存在，类型 `varchar`，character_maximum_length = 32

#### TC-M07: test_add_entity_columns
- **验收标准**: subject_entity_id/object_entity_id 列存在，类型 `uuid`

#### TC-M08: test_add_source_episode_ids
- **验收标准**: source_episode_ids 列存在，data_type = `ARRAY`，udt_name = `_uuid`

#### TC-M09: test_add_importance_column
- **验收标准**: importance 列存在，类型 `float4`，默认值 0.5

#### TC-M10: test_add_columns_idempotent
- **操作**: 执行所有 ADD COLUMN 两次
- **验收标准**: 第二次执行无异常；已有数据的列值不被覆盖

#### TC-M11: test_conversation_sessions_last_reflected_at
- **验收标准**: conversation_sessions 表有 last_reflected_at 列，类型 `timestamptz`

#### TC-M12: test_trait_indexes_created
- **验收标准**: 通过 `pg_indexes` 验证以下索引存在：

| 索引名 | 关键列 | 部分索引条件 |
|--------|--------|-------------|
| idx_trait_stage_confidence | user_id, trait_stage, trait_confidence | WHERE trait_stage NOT IN ('dissolved','trend') |
| idx_trait_parent | trait_parent_id | WHERE trait_parent_id IS NOT NULL |
| idx_trait_context | user_id, trait_context | WHERE trait_context IS NOT NULL |
| idx_trait_window | trait_window_end | WHERE trait_stage='trend' AND trait_window_end IS NOT NULL |
| idx_content_hash | content_hash | WHERE content_hash IS NOT NULL |

#### TC-M13: test_indexes_idempotent
- **操作**: 执行 CREATE INDEX IF NOT EXISTS 两次
- **验收标准**: 第二次执行无异常

#### TC-M14: test_full_migration_three_times
- **操作**: 从 V1 schema 开始，执行 db.init() 三次
- **验收标准**: 三次均无异常，最终 schema 正确，数据完好

---

### 3.2 ORM 模型测试 (`test_storage_v2_orm.py`)

#### TC-O01: test_memory_model_tablename
- **验收标准**: `Memory.__tablename__ == "memories"`

#### TC-O02: test_embedding_alias_exists
- **验收标准**: `from neuromem.models.memory import Embedding` 不报错；`Embedding is Memory` 为 True

#### TC-O03: test_memory_model_trait_fields_roundtrip
- **操作**: 创建 Memory 实例，填充全部 12 个 trait 字段，写入数据库后读回
- **验收标准**:
  - trait_subtype == "preference"
  - trait_stage == "emerging"
  - trait_confidence == 0.75（精度 1e-6）
  - trait_context == "work"
  - trait_parent_id == 指定 UUID
  - trait_reinforcement_count == 5
  - trait_contradiction_count == 2
  - trait_last_reinforced == 指定时间
  - trait_first_observed == 指定时间
  - trait_window_start == 指定时间
  - trait_window_end == 指定时间
  - trait_derived_from == "reflection"

#### TC-O04: test_memory_model_timeline_fields_roundtrip
- **操作**: 创建 Memory，设置 valid_at/invalid_at/expired_at，写入后读回
- **验收标准**: 三个时间戳字段值一致（时区感知比较）

#### TC-O05: test_memory_model_content_hash_roundtrip
- **操作**: 设置 content_hash = "d41d8cd98f00b204e9800998ecf8427e"（32 字符 MD5）
- **验收标准**: 写入后读回值完全一致

#### TC-O06: test_memory_model_entity_fields_roundtrip
- **操作**: 设置 subject_entity_id 和 object_entity_id 为不同 UUID
- **验收标准**: 写入后读回值一致

#### TC-O07: test_memory_model_source_episode_ids
- **操作**: 设置 source_episode_ids = [uuid1, uuid2, uuid3]
- **验收标准**: 写入后读回列表长度 3，值一致

#### TC-O08: test_trait_evidence_crud
- **操作**: 创建 TraitEvidence（evidence_type='supporting', quality='A'），写入后读回
- **验收标准**:
  - trait_id, memory_id 正确
  - evidence_type == 'supporting'
  - quality == 'A'
  - created_at 自动填充
- **约束测试**: evidence_type='invalid' 应触发 CHECK 约束失败；quality='E' 应触发 CHECK 约束失败

#### TC-O09: test_memory_history_crud
- **操作**: 创建 MemoryHistory（event='ADD', actor='system'），写入后读回
- **验收标准**:
  - event == 'ADD'
  - old_content == None, new_content == "测试内容"
  - actor == 'system'
  - created_at 自动填充
- **事件类型覆盖**: 分别创建 ADD/UPDATE/DELETE/SUPERSEDE/STAGE_CHANGE 事件，全部成功

#### TC-O10: test_reflection_cycle_crud
- **操作**: 创建 ReflectionCycle（trigger_type='importance_accumulated', status='running'），写入后读回
- **验收标准**:
  - trigger_type == 'importance_accumulated'
  - trigger_value 为指定浮点值
  - memories_scanned/traits_created/traits_updated/traits_dissolved 初始为 0
  - status == 'running'
  - started_at 自动填充
  - completed_at 为 NULL
- **状态流转测试**: 更新 status='completed', completed_at=NOW()，读回正确

#### TC-O11: test_memory_source_crud
- **操作**: 创建 MemorySource（memory_id + session_id 复合 PK），写入后读回
- **验收标准**:
  - memory_id, session_id 正确
  - conversation_id 可为 NULL 或 UUID
  - created_at 自动填充

#### TC-O12: test_memory_source_composite_pk_unique
- **操作**: 插入相同 memory_id + session_id 两次
- **验收标准**: 第二次插入触发 IntegrityError

#### TC-O13: test_all_auxiliary_tables_created_by_create_all
- **操作**: 空数据库执行 Base.metadata.create_all()
- **验收标准**: trait_evidence, memory_history, reflection_cycles, memory_sources 四张表全部存在

---

### 3.3 数据回填测试 (`test_storage_v2_backfill.py`)

#### TC-B01: test_backfill_trait_metadata_to_columns
- **前置**: 插入 trait 记忆，metadata 含 `{"trait_subtype":"preference","trait_stage":"emerging","confidence":0.75,"context":"work","reinforcement_count":3,"contradiction_count":1,"derived_from":"reflection"}`
- **操作**: 执行回填 SQL
- **验收标准**:
  - trait_subtype == 'preference'
  - trait_stage == 'emerging'
  - trait_confidence == 0.75
  - trait_context == 'work'
  - trait_reinforcement_count == 3
  - trait_contradiction_count == 1
  - trait_derived_from == 'reflection'

#### TC-B02: test_backfill_skips_already_filled
- **前置**: trait 记忆已有 trait_subtype='behavior'（专用列有值）
- **操作**: 执行回填 SQL
- **验收标准**: trait_subtype 仍为 'behavior'，不被 metadata 中的值覆盖

#### TC-B03: test_backfill_general_to_fact
- **前置**: 3 条 memory_type='general' 的记忆
- **操作**: 执行回填 SQL
- **验收标准**:
  - `SELECT COUNT(*) FROM memories WHERE memory_type='general'` == 0
  - `SELECT COUNT(*) FROM memories WHERE memory_type='fact'` >= 3
  - content, user_id, embedding, metadata 等其他字段不变

#### TC-B04: test_backfill_insight_to_trait_trend
- **前置**: 2 条 memory_type='insight' 的记忆（created_at 已知）
- **操作**: 执行回填 SQL
- **验收标准**:
  - `SELECT COUNT(*) FROM memories WHERE memory_type='insight'` == 0
  - memory_type == 'trait'
  - trait_stage == 'trend'
  - trait_window_start == created_at（原始创建时间）
  - trait_window_end == created_at + 30 天

#### TC-B05: test_backfill_content_hash
- **前置**: 5 条记忆，content_hash 全部为 NULL
- **操作**: 执行回填 SQL
- **验收标准**:
  - 所有记忆的 content_hash 非 NULL
  - content_hash == hashlib.md5(content.encode()).hexdigest()（Python 端验证）

#### TC-B06: test_backfill_content_hash_skips_existing
- **前置**: 1 条记忆已有 content_hash='abc123'
- **操作**: 执行回填 SQL
- **验收标准**: 该记忆的 content_hash 仍为 'abc123'

#### TC-B07: test_backfill_valid_at
- **前置**:
  - 记忆 A: valid_from='2024-01-01', created_at='2024-01-05', valid_at=NULL
  - 记忆 B: valid_from=NULL, created_at='2024-02-01', valid_at=NULL
- **操作**: 执行回填 SQL `UPDATE memories SET valid_at = COALESCE(valid_from, created_at) WHERE valid_at IS NULL`
- **验收标准**:
  - 记忆 A: valid_at == '2024-01-01'（取 valid_from）
  - 记忆 B: valid_at == '2024-02-01'（fallback 到 created_at）

#### TC-B08: test_backfill_idempotent
- **操作**: 执行全部回填 SQL 两次
- **验收标准**: 第二次执行结果与第一次完全一致，无异常

#### TC-B09: test_backfill_preserves_metadata
- **前置**: trait 记忆 metadata 含 `{"trait_subtype":"preference","extra_field":"keep_me","emotion":{"valence":0.5}}`
- **操作**: 执行回填
- **验收标准**: 回填后 metadata 仍包含 extra_field 和 emotion（未被清除或修改）

#### TC-B10: test_backfill_null_metadata
- **前置**: 记忆 metadata 为 NULL
- **操作**: 执行回填
- **验收标准**: 不报错，专用列保持 NULL

#### TC-B11: test_backfill_empty_metadata
- **前置**: 记忆 metadata 为 `{}`
- **操作**: 执行回填
- **验收标准**: 不报错，专用列保持 NULL

#### TC-B12: test_backfill_unicode_content_hash
- **前置**: content = "用户在Google工作，喜欢Python和JavaScript"
- **操作**: 回填 content_hash
- **验收标准**: hash == hashlib.md5(content.encode('utf-8')).hexdigest()

---

### 3.4 halfvec 迁移测试 (`test_storage_v2_halfvec.py`)

#### TC-H01: test_detect_vector_type
- **前置**: embedding 列类型为 vector
- **操作**: 查询 `SELECT udt_name FROM information_schema.columns WHERE column_name='embedding'`
- **验收标准**: udt_name == 'vector'

#### TC-H02: test_convert_vector_to_halfvec
- **前置**: embedding 列为 vector(1024)，含 5 条数据
- **操作**: `ALTER TABLE memories ALTER COLUMN embedding TYPE halfvec(1024) USING embedding::halfvec(1024)`
- **验收标准**: udt_name 变为 'halfvec'

#### TC-H03: test_halfvec_preserves_data
- **前置**: vector 列含已知向量 [0.1, 0.2, ..., 0.5, ...]
- **操作**: 转换为 halfvec
- **验收标准**: 读回向量每个分量与原始值差异 < 0.01（half precision 精度范围）

#### TC-H04: test_halfvec_index_rebuild
- **前置**: 存在旧向量索引（vector_cosine_ops 或 vector_l2_ops）
- **操作**: DROP 旧索引 + CREATE 新 HNSW 索引（halfvec_cosine_ops）
- **验收标准**:
  - 旧索引不存在于 pg_indexes
  - 新索引存在，indexdef 包含 'halfvec_cosine_ops'

#### TC-H05: test_halfvec_skip_if_already
- **前置**: embedding 列已经是 halfvec
- **操作**: 执行迁移检测逻辑
- **验收标准**: 不执行任何 ALTER 语句（可通过 mock 或日志验证）

#### TC-H06: test_halfvec_dimension_matches_config
- **前置**: `_embedding_dims = 1024`
- **操作**: 执行 halfvec 迁移
- **验收标准**: `SELECT typmod FROM pg_attribute WHERE attname='embedding'` 对应维度 1024

#### TC-H07: test_search_after_halfvec_conversion
- **前置**: 5 条记忆已转换为 halfvec，HNSW 索引已建立
- **操作**: 执行 `svc.search(user_id=..., query="test", limit=5)`
- **验收标准**: 返回结果数 > 0，无 SQL 异常

#### TC-H08: test_halfvec_storage_reduction
- **前置**: 同一条记忆在 vector 和 halfvec 下的 pg_column_size
- **验收标准**: halfvec 的 pg_column_size 约为 vector 的 50%（+/- 10%）

---

### 3.5 写入路径测试 (`test_storage_v2_write.py`)

#### TC-W01: test_write_computes_content_hash
- **操作**: `svc.add_memory(user_id="u1", content="Hello World", memory_type="fact")`
- **验收标准**:
  - 返回记录的 content_hash == hashlib.md5(b"Hello World").hexdigest()
  - 即 "b10a8db164e0754105b7a99be72e3fe5"

#### TC-W02: test_write_noop_on_duplicate_hash
- **操作**:
  1. `svc.add_memory(user_id="u1", content="Same content", memory_type="fact")` -> 成功
  2. `svc.add_memory(user_id="u1", content="Same content", memory_type="fact")` -> NOOP
- **验收标准**:
  - `SELECT COUNT(*) FROM memories WHERE user_id='u1' AND content='Same content'` == 1
  - 第二次调用返回 None 或已有记录（不创建新行）

#### TC-W03: test_write_noop_scoped_by_user
- **操作**:
  1. `svc.add_memory(user_id="u1", content="Same content", memory_type="fact")`
  2. `svc.add_memory(user_id="u2", content="Same content", memory_type="fact")`
- **验收标准**: 两条记录都成功创建（不同 user_id 不触发 NOOP）

#### TC-W04: test_write_noop_scoped_by_type
- **操作**:
  1. `svc.add_memory(user_id="u1", content="Same content", memory_type="fact")`
  2. `svc.add_memory(user_id="u1", content="Same content", memory_type="episodic")`
- **验收标准**: 两条记录都成功创建（不同 memory_type 不触发 NOOP）

#### TC-W05: test_write_trait_populates_columns
- **操作**: `svc.add_memory(user_id="u1", content="用户偏好 Python", memory_type="trait", metadata={"trait_subtype":"preference","trait_stage":"emerging","confidence":0.8,"context":"work"})`
- **验收标准**:
  - trait_subtype == 'preference'
  - trait_stage == 'emerging'
  - trait_confidence == 0.8
  - trait_context == 'work'

#### TC-W06: test_write_trait_syncs_metadata_and_columns
- **操作**: 写入 trait 记忆，metadata 含 trait 字段
- **验收标准**:
  - 专用列值 == metadata 中对应字段值
  - metadata JSONB 仍包含 trait_subtype 等字段（向后兼容读取）

#### TC-W07: test_write_non_trait_leaves_columns_null
- **操作**: `svc.add_memory(user_id="u1", content="fact", memory_type="fact")`
- **验收标准**: trait_subtype/trait_stage/trait_confidence 等 12 列全部为 NULL

#### TC-W08: test_write_fills_valid_at
- **操作**: `svc.add_memory(user_id="u1", content="test")`
- **验收标准**: valid_at 非 NULL（取 valid_from 或 NOW()）

#### TC-W09: test_supersede_sets_expired_at
- **前置**: 记忆 A 已存在（version=1）
- **操作**: supersede 记忆 A，创建记忆 B
- **验收标准**:
  - 记忆 A: expired_at 非 NULL，superseded_by == B.id
  - 记忆 B: version == 2（或 A.version + 1），expired_at == NULL

#### TC-W10: test_supersede_chain
- **操作**: A -> supersede -> B -> supersede -> C
- **验收标准**:
  - A.superseded_by == B.id, A.expired_at 非 NULL
  - B.superseded_by == C.id, B.expired_at 非 NULL
  - C.superseded_by == NULL, C.expired_at == NULL

---

### 3.6 读取兼容测试 (`test_storage_v2_read.py`)

#### TC-R01: test_read_prefers_dedicated_column
- **前置**: trait 记忆专用列 trait_subtype='preference'，metadata 含 `{"trait_subtype":"behavior"}`
- **操作**: 搜索或读取该记忆
- **验收标准**: 返回的 trait_subtype == 'preference'（专用列优先）

#### TC-R02: test_read_fallback_to_jsonb
- **前置**: trait 记忆专用列 trait_subtype=NULL，metadata 含 `{"trait_subtype":"behavior"}`
- **操作**: 搜索或读取该记忆（通过 COALESCE(trait_subtype, metadata->>'trait_subtype')）
- **验收标准**: 返回的 trait_subtype == 'behavior'（JSONB fallback）

#### TC-R03: test_read_both_null_returns_none
- **前置**: 专用列 NULL，metadata 无该字段
- **操作**: 读取 trait_subtype
- **验收标准**: 返回 None

#### TC-R04: test_search_result_format_unchanged
- **操作**: 使用 V2 schema 执行 `svc.search(user_id, query, limit=5)`
- **验收标准**: 返回列表中每个 dict 包含以下 V1 已有字段：
  - `id`, `content`, `memory_type`, `metadata`, `score`（或等效字段名）
  - 不缺少任何 V1 存在的字段

#### TC-R05: test_scored_search_result_format_unchanged
- **操作**: `svc.scored_search(user_id, query, limit=5)`
- **验收标准**: 每个结果包含 `relevance`, `recency`, `importance`, `score`

---

### 3.7 向后兼容测试 (`test_storage_v2_compat.py`)

#### TC-C01: test_add_memory_api_unchanged
- **操作**: `svc.add_memory(user_id="u1", content="test", memory_type="fact", metadata={"key":"val"})`
- **验收标准**: 调用成功，返回 Memory 对象（不报 AttributeError/TypeError）

#### TC-C02: test_search_api_unchanged
- **前置**: 2 条记忆已存储
- **操作**: `svc.search(user_id="u1", query="test", limit=5)`
- **验收标准**: 返回 list，len >= 0，无异常

#### TC-C03: test_scored_search_api_unchanged
- **前置**: 2 条记忆已存储
- **操作**: `svc.scored_search(user_id="u1", query="test", limit=5)`
- **验收标准**: 返回 list，每个元素含 relevance/recency/importance/score

#### TC-C04: test_recall_api_unchanged
- **前置**: 通过 nm 写入记忆
- **操作**: `nm.recall(user_id="u1", query="test")`
- **验收标准**: 返回 dict 含 "merged" 键

#### TC-C05: test_general_type_accepted_and_mapped
- **操作**: `svc.add_memory(user_id="u1", content="test", memory_type="general")`
- **验收标准**:
  - 调用不报错
  - 数据库中存储的 memory_type == 'fact'（内部映射）

#### TC-C06: test_ingest_api_unchanged
- **操作**: `nm.ingest(user_id="u1", role="user", content="I work at Google")`
- **验收标准**: 调用成功，无异常

#### TC-C07: test_delete_user_data_includes_auxiliary_tables
- **前置**: 用户有 memories + trait_evidence + memory_history + memory_sources 数据
- **操作**: `nm.delete_user_data(user_id)`
- **验收标准**:
  - memories 表无该 user 数据
  - 相关辅助表数据也被清除（或通过 expired_at 软删除）

#### TC-C08: test_export_user_data_unchanged
- **前置**: 用户有各类数据
- **操作**: `nm.export_user_data(user_id)`
- **验收标准**: 返回 dict 包含 memories/conversations/graph/kv/profile/documents

#### TC-C09: test_embedding_import_alias
- **操作**: `from neuromem.models.memory import Embedding`
- **验收标准**: 不报 ImportError；`Embedding is Memory`

---

## 4. 回归测试

### 4.1 现有测试套件风险分析

| 测试文件 | 风险点 | 预期处理 |
|----------|--------|---------|
| test_search.py:157,178 | 硬编码 `FROM embeddings` SQL | 需更新为 `FROM memories` |
| test_transaction_consistency.py:72,103 | `from neuromem.models.memory import Embedding` | Embedding 别名保证兼容 |
| test_temporal.py | valid_from/valid_until 字段引用 | valid_from 保留为 ORM 属性或需更新 |
| test_time_travel.py | 时间旅行查询用 valid_from/valid_until | 同上 |
| test_data_lifecycle.py:46 | `result["deleted"]["embeddings"]` 键名 | 可能需更新为 "memories" |

### 4.2 回归验收标准

```bash
# 全量测试必须通过
uv run pytest tests/ -x --tb=short
# 预期结果: 全部 PASSED，0 FAILED，0 ERROR
```

---

## 5. 测试数据

### 5.1 V1 测试数据集

```python
V1_TEST_DATA = [
    {
        "content": "用户在 Google 工作",
        "memory_type": "general",
        "metadata": {"category": "work", "importance": 8},
    },
    {
        "content": "用户偏好 Python 语言",
        "memory_type": "insight",
        "metadata": {
            "trait_subtype": "preference",
            "trait_stage": "emerging",
            "confidence": 0.75,
            "context": "work",
            "reinforcement_count": 3,
        },
    },
    {
        "content": "2024-01-15 参加技术大会",
        "memory_type": "episodic",
        "metadata": {"timestamp": "2024-01-15", "importance": 6},
    },
    {
        "content": "用户性格外向",
        "memory_type": "insight",
        "metadata": {"trait_subtype": "core", "confidence": 0.9},
    },
    {
        "content": "Python 是强类型语言",
        "memory_type": "fact",
        "metadata": {"category": "tech"},
    },
]
```

### 5.2 边界值用例

| 场景 | 输入 | 期望行为 |
|------|------|---------|
| 空 content | `content=""` | content_hash = MD5("") = "d41d8cd98f00b204e9800998ecf8427e" |
| 超长 content | 10K+ 字符 | 正常写入，hash 计算正确 |
| Unicode 混合 | "用户说Hello World" | MD5 基于 UTF-8 编码 |
| NULL metadata | metadata=None | 回填不报错，专用列 NULL |
| 空 metadata | metadata={} | 回填不报错，专用列 NULL |
| metadata 含未知字段 | `{"unknown":"value"}` | 回填忽略未知字段，metadata 保留 |

---

## 6. 质量门控

### 6.1 通过标准

| 指标 | 要求 | 阻塞级别 |
|------|------|---------|
| 新增测试全部通过 | 100% | 阻塞发布 |
| 现有测试全部通过 | 100%（0 regression） | 阻塞发布 |
| 迁移幂等性 | 连续 3 次执行无异常 | 阻塞发布 |
| 回填数据完整性 | 零丢失 | 阻塞发布 |
| halfvec 搜索功能 | 转换后搜索正常 | 阻塞发布 |
| 公共 API 兼容 | 签名和返回值不变 | 阻塞发布 |

### 6.2 测试用例统计

| 类别 | 数量 |
|------|------|
| Schema 迁移 | 14 |
| ORM 模型 | 13 |
| 数据回填 | 12 |
| halfvec 迁移 | 8 |
| 写入路径 | 10 |
| 读取兼容 | 5 |
| 向后兼容 | 9 |
| **合计** | **71** |
