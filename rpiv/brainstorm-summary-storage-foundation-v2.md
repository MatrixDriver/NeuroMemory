---
description: "需求摘要: RPIV-1 存储基座（Schema + ORM + 迁移）"
status: pending
created_at: 2026-02-28T22:00:00
updated_at: 2026-02-28T22:00:00
archived_at: null
---

# 需求摘要：RPIV-1 存储基座（Schema + ORM + 迁移）

## 产品愿景
- **核心问题**：当前 embeddings 单表 + 全 JSONB 架构无法支撑记忆分类 V2 的 trait 专用字段、双时间线、证据链等需求
- **价值主张**：为 V2 记忆分类铺设存储基座——新 schema 就位，现有功能无感知升级
- **目标用户**：neuromem SDK 使用方（neuromem-cloud、Me2、未来第三方）
- **产品形态**：Python SDK 内部改造（schema + ORM + 迁移），公共 API 不变

## 设计文档依赖

- **记忆分类 V2 设计**：`docs/design/memory-classification-v2.md`
- **存储方案 V2 设计**：`docs/design/storage-schema-v2.md`（含修订版 17 条改进）

## 核心场景（按优先级排序）

1. **表改名 + 新增列**：embeddings → memories，新增 12 个 trait 专用列 + 双时间线 + updated_at + content_hash
2. **辅助表创建**：trait_evidence、memory_history、reflection_cycles、memory_sources 四张新表
3. **ORM 模型重写**：Memory 类新增全部字段，新增 4 个辅助表 ORM 模型
4. **数据回填**：metadata JSONB → 专用列，general → fact，insight → trait(trend)
5. **halfvec 迁移**：vector → halfvec（维度保持可配置）
6. **写入路径更新**：新写入同时填充专用列 + content_hash 计算 + NOOP 检测
7. **读取兼容**：专用列优先，fallback 到 JSONB
8. **对话表扩展**：conversation_sessions 加 last_reflected_at
9. **索引更新**：trait 专用索引 + trend 窗口索引 + 去重索引

## 产品边界

### MVP 范围内
- 上述 9 个场景全部完成
- 所有现有测试通过
- 公共 API（add_memory、search）行为不变

### 明确不做
- LIST 分区（P1 阶段）
- Reflection 引擎（RPIV-2）
- Trait 生命周期管理（RPIV-2）
- LLM 操作判断 ADD/UPDATE/DELETE（RPIV-2）
- 召回公式改造（RPIV-2）
- 物化视图 mv_trait_decayed（P1）
- 周边表改动（graph_nodes/edges、key_values、emotion_profiles）
- fillfactor/autovacuum 调优（P1，需分区）
- neuromem-cloud 部署

### 后续版本
- RPIV-2：分类逻辑（reflection + 生命周期 + 召回）
- P1：分区 + 高级特性

## 已知约束

- **迁移方式**：不引入 Alembic，保持现有 `create_all` + 幂等 `ALTER TABLE ADD COLUMN IF NOT EXISTS` 模式（在 `db.py` 初始化中执行）
- **向后兼容**：add_memory/search API 行为不变
- **仅改 SDK**：neuromem-cloud 部署另行安排
- **测试要求**：所有现有测试必须通过

## 各场景功能要点

### 场景1：表改名 + 新增列

**功能点**：
- 检测旧表 `embeddings` 存在 → `ALTER TABLE embeddings RENAME TO memories`
- 新安装则直接 `create_all` 创建 `memories`
- 已是 `memories` → 跳过改名

**新增列**（全部幂等 ADD COLUMN IF NOT EXISTS）：

Trait 专用列（12 列）：
- trait_subtype VARCHAR(20)
- trait_stage VARCHAR(20)
- trait_confidence REAL
- trait_context VARCHAR(20)
- trait_parent_id UUID
- trait_reinforcement_count INTEGER DEFAULT 0
- trait_contradiction_count INTEGER DEFAULT 0
- trait_last_reinforced TIMESTAMPTZ
- trait_first_observed TIMESTAMPTZ
- trait_window_start TIMESTAMPTZ
- trait_window_end TIMESTAMPTZ
- trait_derived_from VARCHAR(20)

其他新列：
- valid_at TIMESTAMPTZ（双时间线：事件开始成立时间）
- invalid_at TIMESTAMPTZ（双时间线：事件停止成立时间）
- expired_at TIMESTAMPTZ（双时间线：被 supersede 的系统时间）
- updated_at TIMESTAMPTZ（乐观锁辅助）
- content_hash VARCHAR(32)（MD5 去重）
- subject_entity_id UUID（实体关联）
- object_entity_id UUID（实体关联）
- source_episode_ids UUID[]（对话溯源）

**异常处理**：全部幂等操作，重复执行无副作用

### 场景2：辅助表创建

**功能点**：4 张新表通过 ORM 模型 + `create_all` 自动创建

- **trait_evidence**：trait 证据链（id, trait_id, memory_id, evidence_type, quality, created_at）
- **memory_history**：记忆变更审计日志（id, memory_id, memory_type, event, old/new_content, old/new_metadata, actor, created_at）
- **reflection_cycles**：反思周期记录（id, user_id, trigger_type, trigger_value, stats, status, timestamps）
- **memory_sources**：记忆与对话关联（memory_id + session_id 复合主键，conversation_id 可选）

**异常处理**：`create_all` 天然幂等

### 场景3：ORM 模型重写

**功能点**：
- Memory 类：`__tablename__ = "memories"`，所有新字段对应 ORM 列定义
- 新增 TraitEvidence、MemoryHistory、ReflectionCycle、MemorySource 四个 ORM 模型
- 全面搜索并更新代码中引用旧表名 `embeddings` 的地方

**关键交互**：ORM 字段类型需匹配 DDL（如 halfvec 需要 pgvector 的 HALFVEC 类型）

### 场景4：数据回填

**功能点**（在 db.py 初始化中幂等执行）：

1. trait metadata → 专用列：
   ```sql
   UPDATE memories SET
       trait_subtype = metadata->>'trait_subtype',
       trait_stage = metadata->>'trait_stage',
       trait_confidence = (metadata->>'confidence')::float,
       -- ... 其他字段
   WHERE memory_type = 'trait' AND trait_subtype IS NULL
   ```

2. 旧类型迁移：
   ```sql
   UPDATE memories SET memory_type = 'fact' WHERE memory_type = 'general';
   UPDATE memories SET
       memory_type = 'trait',
       trait_stage = 'trend',
       trait_window_start = created_at,
       trait_window_end = created_at + interval '30 days'
   WHERE memory_type = 'insight';
   ```

3. content_hash 回填：
   ```sql
   UPDATE memories SET content_hash = MD5(content) WHERE content_hash IS NULL;
   ```

4. valid_at 回填：
   ```sql
   UPDATE memories SET valid_at = COALESCE(valid_from, created_at) WHERE valid_at IS NULL;
   ```

**异常处理**：WHERE 条件保证幂等（只更新未填充的行）

### 场景5：halfvec 迁移

**功能点**：
- 检测当前列类型是否为 vector → 改为 halfvec
- `ALTER COLUMN embedding TYPE halfvec(N) USING embedding::halfvec(N)`（N 从 settings.EMBEDDING_DIM 读取）
- DROP 旧向量索引 + CREATE 新 HNSW 索引（halfvec_cosine_ops）
- 已经是 halfvec → 跳过

**异常处理**：类型检测避免重复执行

### 场景6：写入路径更新

**功能点**：
- add_memory 写入时计算 `content_hash = MD5(content)`
- 写入前检查 hash 是否已存在（同 user_id + 同 memory_type）→ 存在则 NOOP
- trait 类型记忆写入时填充 trait_* 专用列（从传入的 metadata 提取）
- supersede 操作时：旧记忆 `expired_at = NOW()`，新记忆 `version = old_version + 1`
- 所有写入同时写 metadata JSONB（向后兼容读取）

**异常处理**：hash 冲突但内容不同（MD5 碰撞极低概率）→ 向量语义相似度二次确认

### 场景7：读取兼容

**功能点**：
- 搜索结果返回时优先读专用列
- 专用列为 NULL 时 fallback 到 metadata JSONB（兼容回填前的旧数据）
- 现有 search API 返回格式不变

### 场景8：对话表扩展

**功能点**：
- `ALTER TABLE conversation_sessions ADD COLUMN IF NOT EXISTS last_reflected_at TIMESTAMPTZ`
- RPIV-1 只添加字段，不使用（RPIV-2 的 reflection 引擎会使用）

### 场景9：索引更新

**功能点**：
- 表改名后旧索引名自动跟随（PG RENAME TABLE 会保留索引）
- 新增 trait 专用索引：stage+confidence、parent、context、window
- 新增 content_hash 去重索引
- halfvec 迁移后重建向量索引（HNSW + halfvec_cosine_ops）

**具体索引**：
- `idx_trait_stage_confidence ON memories (user_id, trait_stage, trait_confidence DESC) WHERE trait_stage NOT IN ('dissolved', 'trend')`
- `idx_trait_parent ON memories (trait_parent_id) WHERE trait_parent_id IS NOT NULL`
- `idx_trait_context ON memories (user_id, trait_context) WHERE trait_context IS NOT NULL`
- `idx_trait_window ON memories (trait_window_end) WHERE trait_stage = 'trend' AND trait_window_end IS NOT NULL`
- `idx_content_hash ON memories (content_hash) WHERE content_hash IS NOT NULL`
