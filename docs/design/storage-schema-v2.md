# 存储方案 V2 设计文档

> **状态**: 设计草案（头脑风暴产出）→ 修订版
> **创建日期**: 2026-02-28
> **修订日期**: 2026-02-28（应用 3 维度批判性审查的 17 条修订建议）
> **前置文档**: `memory-classification-v2.md`（记忆分类 V2）
> **调研基础**: 8 份独立调研（PG JSONB/pgvector/Mem0/Zep-Graphiti/Letta/学术方案/PG高级特性/图存储）

---

## 1. 设计原则

基于 8 份调研的核心共识：

| 原则 | 来源 | 说明 |
|------|------|------|
| **PG 单栈优先** | Mem0 对比、Letta 验证 | neuromem 全部存储在 PostgreSQL 内（pgvector + 关系表），ACID 事务一致性是对比 Mem0/Zep 混合架构的天然优势 |
| **混合 Schema** | JSONB 调研 | 热字段提升为专用列（避免 JSONB 写放大 + TOAST 断崖），冷字段保留 JSONB |
| **halfvec 量化** | pgvector 调研 | 向量统一使用 halfvec，存储减半，召回损失 <0.3%；维度由配置驱动（默认 1024） |
| **双时间线** | Zep/Graphiti 调研 | 所有记忆采用四时间戳（valid_at/invalid_at + created_at/expired_at），支持时间旅行和矛盾保留 |
| **按类型分区** | pgvector + PG 特性调研 | 按 memory_type LIST 分区，各类型独立向量索引，分区裁剪加速过滤查询 |
| **trait 专用列 + 外键层级** | JSONB 调研 + 图存储调研 | trait 的热字段为专用列，层级关系用 parent_id 外键（不需要图数据库） |
| **SQL 同步 + 向量异步** | Letta 调研 | 关系数据同步写入保证 ACID，embedding 异步计算后回填 |

---

## 2. 表结构设计

### 2.1 核心决策：分区 + 混合 Schema

**方案选型对比**：

| 方案 | 描述 | 优劣 |
|------|------|------|
| A. 单表 + 全 JSONB（当前） | 所有类型共用 embeddings 表 | 简单但 JSONB 写放大、无统计信息 |
| B. 单表 + 混合 Schema | 添加 trait 专用列，其他类型列为 NULL | 中等，NULL 列有存储开销但可接受 |
| **C. LIST 分区 + 混合 Schema** | **按 memory_type 分区，trait 分区有专用列** | **最优：分区裁剪 + 独立索引 + 专用列** |
| D. 完全独立表 | 每个 memory_type 一张表 | 过度拆分，跨类型查询复杂 |

**选择方案 C：LIST 分区 + 混合 Schema。**

理由：
1. 分区裁剪使 `WHERE memory_type = 'trait'` 自动跳过其他分区（实测 67-83% 时间缩减）
2. 各分区独立 HNSW 索引，参数可差异化（trait 分区 m=24 更高精度）
3. trait 分区有专用列，非 trait 分区不受影响
4. VACUUM/REINDEX 可针对单分区执行，维护更精准

### 2.2 主键策略

**[修订] 放弃复合主键，改用 UUID 单列 PK**

原方案 `PRIMARY KEY (id, memory_type)` 会导致所有外部引用（`superseded_by`、`trait_parent_id`、`trait_evidence.trait_id` 等）都必须携带双列，代码复杂度爆炸。

修订方案：UUID 单列主键 + CHECK 约束。PG 14+ 的分区表允许 PK 不包含分区键（只要分区键有 NOT NULL）。若版本不支持，使用 `UNIQUE (id, memory_type)` 辅助路由。

### 2.3 主表定义

```sql
-- ==========================================
-- 核心记忆表（分区主表）
-- ==========================================
CREATE TABLE memories (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id         VARCHAR(255) NOT NULL,
    memory_type     VARCHAR(50) NOT NULL,     -- 分区键：fact/episodic/trait/document

    -- === 内容 ===
    content         TEXT NOT NULL,
    embedding       halfvec(1024),             -- halfvec 量化；维度由 settings.EMBEDDING_DIM 驱动
    -- 写入策略（借鉴 Letta）：
    --   关系数据（content/metadata/trait 列）同步写入，ACID 保证
    --   embedding 异步计算后回填（写入时 NULL，后台 worker 批量 UPDATE）
    --   查询时 WHERE embedding IS NOT NULL（跳过尚未计算完成的记忆）

    -- === 双时间线（P0，借鉴 Zep/Graphiti） ===
    valid_at        TIMESTAMPTZ,               -- 事件时间：事实/事件开始成立
    invalid_at      TIMESTAMPTZ,               -- 事件时间：事实/事件停止成立（NULL=仍有效）
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),  -- 系统时间：入库时间
    updated_at      TIMESTAMPTZ,               -- 最后更新时间（乐观锁辅助）
    expired_at      TIMESTAMPTZ,               -- 系统时间：被 supersede 的时间（NULL=当前版本）

    -- === 版本化（乐观锁） ===
    version         INTEGER DEFAULT 1,
    superseded_by   UUID,                      -- 单列 UUID 引用（受益于单列 PK）

    -- === 通用元数据 ===
    importance      REAL DEFAULT 0.5,          -- 重要性（0-1）
    access_count    INTEGER DEFAULT 0,
    last_accessed_at TIMESTAMPTZ,
    content_hash    VARCHAR(32),               -- MD5 hash，内容级去重（借鉴 Mem0）

    -- === 扩展元数据 ===
    metadata        JSONB NOT NULL DEFAULT '{}',  -- 冷字段：entities, emotion, source, reflection_cycle_ids 等

    -- === Trait 专用列（仅 trait 分区有值） ===
    trait_subtype    VARCHAR(20),               -- behavior / preference / core
    trait_stage      VARCHAR(20),               -- trend / candidate / emerging / established / core / dissolved
    trait_confidence REAL,                      -- 置信度（trend 阶段为 NULL，用 window 管理）
    trait_context    VARCHAR(20),               -- work / personal / social / learning / general / contextual
    trait_parent_id  UUID,                      -- 父 trait（升级链），单列 UUID 引用
    trait_reinforcement_count INTEGER DEFAULT 0, -- 累计强化次数（影响衰减速率，间隔效应）
    trait_contradiction_count INTEGER DEFAULT 0, -- 累计矛盾次数
    trait_last_reinforced TIMESTAMPTZ,          -- 最后强化时间
    trait_first_observed  TIMESTAMPTZ,          -- [修订] 首次观测到该模式的时间（来源证据的最早时间）
    trait_window_start    TIMESTAMPTZ,          -- [修订] trend 阶段：观察窗口开始
    trait_window_end      TIMESTAMPTZ,          -- [修订] trend 阶段：观察窗口结束（非 trend 为 NULL）
    trait_derived_from    VARCHAR(20),          -- [修订] 产生方式：reflection / trend_promotion / contradiction_split

    -- === 实体关联（可选，借鉴 Zep 三元组） ===
    subject_entity_id UUID,                    -- 主语实体（如 "Alice"）
    object_entity_id  UUID,                    -- 宾语实体（如 "Google"）

    -- === 溯源 ===
    source_episode_ids UUID[],                 -- 产生此记忆的对话 Session IDs（引用 conversation_sessions.id）

    -- === 约束 ===
    CONSTRAINT chk_memory_type CHECK (memory_type IN ('fact', 'episodic', 'trait', 'document'))
) PARTITION BY LIST (memory_type);
```

**Trait JSONB 冷字段约定**（不值得专用列的低频读取字段）：

```jsonc
{
    // 反思周期关联（冷数据，仅审计/展示时使用）
    "reflection_cycle_ids": ["cycle-12", "cycle-15", "cycle-18"],

    // 情境化双面 trait（当 trait_context = 'contextual' 时存在）
    // 矛盾分裂的产物，见分类 V2 §4.4
    "contexts": {
        "work": {"tendency": "严谨细致", "confidence": 0.8},
        "personal": {"tendency": "随性自由", "confidence": 0.65}
    },

    // 情绪元数据（与 fact/episodic 共享）
    "emotion": {"valence": 0.3, "arousal": 0.4, "label": "平静、认可"},

    // 实体标签、来源等其他冷字段
    "entities": ["Google", "Python"],
    "source": "conversation"
}
```

### 2.4 分区定义 + 存储参数

```sql
-- === 四个分区 ===
CREATE TABLE memories_fact      PARTITION OF memories FOR VALUES IN ('fact');
CREATE TABLE memories_episodic  PARTITION OF memories FOR VALUES IN ('episodic');
CREATE TABLE memories_trait     PARTITION OF memories FOR VALUES IN ('trait');
CREATE TABLE memories_document  PARTITION OF memories FOR VALUES IN ('document');

-- 注意：trait 专用列在非 trait 分区中自动为 NULL，不影响存储

-- ==========================================
-- [修订] fillfactor + autovacuum 调优
-- trait 高频更新热字段，必须预留 HOT update 空间
-- ==========================================
ALTER TABLE memories_trait SET (
    fillfactor = 80,                          -- 预留 20% 页面空间给 HOT update
    autovacuum_vacuum_scale_factor = 0.05,    -- 5% 死元组即触发（默认 20% 太迟）
    autovacuum_analyze_scale_factor = 0.02    -- 2% 变更即更新统计信息
);

ALTER TABLE memories_fact SET (
    fillfactor = 90,                          -- 以追加为主，偶有 supersede 更新
    autovacuum_vacuum_scale_factor = 0.10
);

-- episodic：纯追加，极少更新
ALTER TABLE memories_episodic SET (fillfactor = 95);

-- document：纯追加，不更新
-- fillfactor 保持默认 100
```

### 2.5 索引策略

```sql
-- ==========================================
-- 向量索引（每分区独立 HNSW，参数差异化）
-- ==========================================
CREATE INDEX idx_fact_embedding ON memories_fact
    USING hnsw (embedding halfvec_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX idx_episodic_embedding ON memories_episodic
    USING hnsw (embedding halfvec_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX idx_trait_embedding ON memories_trait
    USING hnsw (embedding halfvec_cosine_ops)
    WITH (m = 24, ef_construction = 128);   -- trait 更高精度

CREATE INDEX idx_document_embedding ON memories_document
    USING hnsw (embedding halfvec_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- ==========================================
-- 标量过滤索引
-- ==========================================
-- 用户基础过滤（所有分区）
CREATE INDEX idx_fact_user      ON memories_fact (user_id, created_at DESC);
CREATE INDEX idx_episodic_user  ON memories_episodic (user_id, valid_at DESC);
CREATE INDEX idx_trait_user     ON memories_trait (user_id, trait_stage, trait_subtype);
CREATE INDEX idx_document_user  ON memories_document (user_id, created_at DESC);

-- Trait 专用索引
CREATE INDEX idx_trait_stage_confidence ON memories_trait (user_id, trait_stage, trait_confidence DESC)
    WHERE trait_stage NOT IN ('dissolved', 'trend');  -- 只索引活跃 trait

CREATE INDEX idx_trait_parent ON memories_trait (trait_parent_id)
    WHERE trait_parent_id IS NOT NULL;

CREATE INDEX idx_trait_context ON memories_trait (user_id, trait_context)
    WHERE trait_context IS NOT NULL;

-- [修订] trend 窗口过期检查索引
CREATE INDEX idx_trait_window ON memories_trait (trait_window_end)
    WHERE trait_stage = 'trend' AND trait_window_end IS NOT NULL;

-- 时间旅行查询索引
CREATE INDEX idx_fact_temporal ON memories_fact (user_id, valid_at, invalid_at);
CREATE INDEX idx_episodic_temporal ON memories_episodic (user_id, valid_at);

-- 内容去重索引
CREATE INDEX idx_content_hash ON memories (content_hash) WHERE content_hash IS NOT NULL;

-- BM25 全文索引（如支持 pg_search / ParadeDB）
-- CREATE INDEX idx_bm25 ON memories USING bm25 (id, content) WITH (key_field = id);
-- 降级方案：PG 原生全文搜索
CREATE INDEX idx_fact_fts ON memories_fact USING gin (to_tsvector('simple', content));
CREATE INDEX idx_episodic_fts ON memories_episodic USING gin (to_tsvector('simple', content));
```

### 2.6 辅助表

#### 2.6.1 Trait 证据表（独立表，避免 JSONB 追加写放大）

```sql
-- trait 的证据链（替代 metadata.evidence JSONB 数组）
CREATE TABLE trait_evidence (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    trait_id    UUID NOT NULL,               -- 引用 memories_trait.id（应用层保证一致性）
    memory_id   UUID NOT NULL,               -- 支持/矛盾的源记忆 ID
    evidence_type VARCHAR(15) NOT NULL,      -- supporting / contradicting
    quality     CHAR(1) NOT NULL,            -- A/B/C/D 四级（见分类 V2 §4.2）
    created_at  TIMESTAMPTZ DEFAULT NOW(),

    -- 无 FK 到分区表（PG 分区表外键限制），应用层保证一致性
    CONSTRAINT chk_evidence_type CHECK (evidence_type IN ('supporting', 'contradicting')),
    CONSTRAINT chk_quality CHECK (quality IN ('A', 'B', 'C', 'D'))
);

CREATE INDEX idx_evidence_trait ON trait_evidence (trait_id, evidence_type);
CREATE INDEX idx_evidence_memory ON trait_evidence (memory_id);
```

#### 2.6.2 记忆变更历史表（借鉴 Mem0 audit log + Letta BlockHistory）

```sql
-- 记忆变更审计日志
CREATE TABLE memory_history (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    memory_id   UUID NOT NULL,               -- 应用层保证引用一致性
    memory_type VARCHAR(50) NOT NULL,
    event       VARCHAR(20) NOT NULL,        -- ADD / UPDATE / DELETE / SUPERSEDE / STAGE_CHANGE
    old_content TEXT,
    new_content TEXT,
    old_metadata JSONB,
    new_metadata JSONB,
    actor       VARCHAR(50) DEFAULT 'system', -- system / reflection / user
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_history_memory ON memory_history (memory_id, created_at DESC);
```

#### 2.6.3 反思周期记录表

```sql
-- 反思引擎执行记录
CREATE TABLE reflection_cycles (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id         VARCHAR(255) NOT NULL,
    trigger_type    VARCHAR(20) NOT NULL,    -- importance_accumulated / scheduled / session_end
    trigger_value   REAL,                    -- 累积重要度值（importance 触发时）
    memories_scanned INTEGER DEFAULT 0,      -- 扫描的新记忆数
    traits_created  INTEGER DEFAULT 0,       -- 新建 trait 数
    traits_updated  INTEGER DEFAULT 0,       -- 更新 trait 数
    traits_dissolved INTEGER DEFAULT 0,      -- dissolved trait 数
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    status          VARCHAR(20) DEFAULT 'running', -- running / completed / failed
    error_message   TEXT
);

CREATE INDEX idx_reflection_user ON reflection_cycles (user_id, started_at DESC);
```

#### 2.6.4 [修订] 记忆溯源表（对话关联）

```sql
-- 记忆与对话 session 的精确关联（替代 source_episode_ids 数组的补充方案）
-- source_episode_ids 保留用于快速引用，此表用于精确的消息级溯源
CREATE TABLE memory_sources (
    memory_id       UUID NOT NULL,           -- 引用 memories.id
    session_id      UUID NOT NULL,           -- 引用 conversation_sessions.id
    conversation_id UUID,                    -- 精确到某条 conversations.id（可选）
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (memory_id, session_id)
);

CREATE INDEX idx_sources_session ON memory_sources (session_id);
```

对话表的配套变更：

```sql
-- conversation_sessions 表添加反思水位线
ALTER TABLE conversation_sessions ADD COLUMN last_reflected_at TIMESTAMPTZ;
-- reflection 引擎以此为扫描起点，避免重复处理已反思过的对话
```

### 2.7 [修订] 分区表外键限制的统一应对

PG 分区表不能作为外键的**被引用端**。以下引用无法使用数据库级 FK，统一由应用层保证一致性：

| 引用方 | 字段 | 被引用 |
|--------|------|--------|
| `trait_evidence` | `trait_id` | `memories_trait.id` |
| `trait_evidence` | `memory_id` | `memories.id` |
| `memory_history` | `memory_id` | `memories.id` |
| `memory_sources` | `memory_id` | `memories.id` |
| `memories` | `superseded_by` | `memories.id` |
| `memories` | `trait_parent_id` | `memories_trait.id` |

**应用层保证措施**：

1. 所有写入操作在同一事务中完成（trait + evidence 同事务）
2. 删除/dissolved 操作使用**软删除**（设置 `expired_at`），不物理删除行
3. 定期一致性检查任务：检测孤立的 evidence/history/sources 记录

```sql
-- 一致性检查：孤立证据
SELECT te.id, te.trait_id
FROM trait_evidence te
LEFT JOIN memories_trait mt ON te.trait_id = mt.id
WHERE mt.id IS NULL;

-- 一致性检查：孤立历史
SELECT mh.id, mh.memory_id
FROM memory_history mh
LEFT JOIN memories m ON mh.memory_id = m.id
WHERE m.id IS NULL;
```

---

## 3. 从现有 Schema 的迁移路径

### 3.1 当前 → V2 的差异

| 维度 | 当前（V1） | V2 设计 |
|------|-----------|---------|
| 表结构 | 单表 `embeddings` | 分区表 `memories` (4 个分区) |
| 主键 | `id UUID PRIMARY KEY` | `id UUID PRIMARY KEY`（保持单列，分区键通过 CHECK 约束） |
| 向量类型 | `vector(动态)` | `halfvec(配置驱动，默认 1024)` |
| memory_type | VARCHAR 无约束 | 分区键，限定 4 值 + CHECK 约束 |
| trait 字段 | 全在 metadata JSONB | 热字段→专用列（12 列），冷字段→JSONB |
| 时间模型 | valid_from/valid_until + created_at | valid_at/invalid_at + created_at/expired_at（双时间线）+ updated_at |
| 证据链 | metadata.evidence JSONB 数组 | 独立 `trait_evidence` 表 |
| 去重 | 向量相似度 >0.95 | MD5 hash 快筛 + 向量语义判断 |
| 版本化 | superseded_by UUID | 保留，增加 expired_at 双时间线 + version 乐观锁 |
| 对话关联 | 无 | `memory_sources` 表 + `source_episode_ids` 数组 |

### 3.2 迁移策略

**推荐渐进式迁移**（非大爆炸）：

```
阶段 1（非破坏性扩展）：
  - 在现有 embeddings 表上 ADD COLUMN trait 专用列（12 列）
  - 添加 valid_at/invalid_at/expired_at/updated_at/content_hash 列
  - 创建新索引
  - 新代码写入新列，旧代码兼容（读取时 fallback 到 metadata）

阶段 2（数据迁移）：
  - 批量回填：从 metadata JSONB 提取值到专用列
  - 回填 content_hash
  - 创建 trait_evidence 表，从 metadata.evidence 迁移
  - 创建 memory_history、reflection_cycles、memory_sources 表
  - conversation_sessions 表添加 last_reflected_at 列
  - 现有 documents 表的 chunk 数据标记，准备迁移到 memories_document 分区
    - documents 表的 file 级元信息（文件名、大小、类型）保留为独立表或迁入 metadata

阶段 3（分区切换）：
  - 创建分区表 memories（含 CHECK 约束 + 单列 UUID PK）
  - 批量 INSERT INTO memories SELECT FROM embeddings
  - 应用层切换表名（通过 view 或 ORM 映射）
  - 配置各分区的 fillfactor + autovacuum 参数
  - 验证后 DROP 旧表

阶段 4（清理）：
  - 移除 metadata 中已提升为专用列的字段
  - 清理旧索引
  - 更新 ORM 模型
  - 运行一致性检查，修复孤立引用
```

---

## 4. 图存储方案

### 4.1 实体关系图（维持 + 增强）

保留现有 `graph_nodes` + `graph_edges` 邻接表方案，增加双时间线支持：

```sql
-- 现有 graph_edges 表增加时态字段
ALTER TABLE graph_edges ADD COLUMN valid_at TIMESTAMPTZ;
ALTER TABLE graph_edges ADD COLUMN invalid_at TIMESTAMPTZ;
-- 已有的 properties JSONB 中的 valid_from/valid_until 迁移到独立列
```

### 4.2 Trait 层级（外键方案，不需要图数据库）

Trait 的层级关系直接通过 `trait_parent_id` 外键实现：

```sql
-- 查找某 behavior trait 的完整升级链（最多 3 层）
WITH RECURSIVE chain AS (
    SELECT id, content, trait_subtype, trait_stage, trait_confidence, 0 AS depth
    FROM memories_trait
    WHERE id = $target_id

    UNION ALL

    SELECT t.id, t.content, t.trait_subtype, t.trait_stage, t.trait_confidence, c.depth + 1
    FROM memories_trait t
    JOIN chain c ON t.trait_parent_id = c.id
    WHERE c.depth < 3
)
SELECT * FROM chain ORDER BY depth;

-- 查找某 preference 的所有 child behavior
SELECT * FROM memories_trait
WHERE trait_parent_id = $preference_id
  AND trait_subtype = 'behavior'
  AND trait_stage NOT IN ('dissolved');
```

**为什么不用 ltree**：trait 层级固定 3 层且是简单树结构，外键 + 递归 CTE 已完全胜任，ltree 的主要优势（任意深度的祖先/后代查询）在此场景下无额外收益，引入反而增加维护复杂度。

---

## 5. 生命周期管理

### 5.1 衰减预计算（物化视图）

```sql
-- 物化视图：预计算 trait 的衰减后置信度
CREATE MATERIALIZED VIEW mv_trait_decayed AS
SELECT
    t.id,
    t.user_id,
    t.content,
    t.embedding,
    t.trait_subtype,
    t.trait_stage,
    t.trait_context,
    t.trait_confidence AS raw_confidence,
    t.trait_reinforcement_count,
    t.trait_first_observed,
    -- 衰减公式：confidence * exp(-effective_lambda * days)
    -- effective_lambda = base_lambda / (1 + 0.1 * reinforcement_count)（间隔效应）
    t.trait_confidence * exp(
        -(CASE t.trait_subtype
            WHEN 'behavior'   THEN 0.005
            WHEN 'preference' THEN 0.002
            WHEN 'core'       THEN 0.001
            ELSE 0.003
        END / (1 + 0.1 * COALESCE(t.trait_reinforcement_count, 0)))
        * EXTRACT(EPOCH FROM (NOW() - COALESCE(t.trait_last_reinforced, t.created_at))) / 86400.0
    ) AS decayed_confidence,
    t.importance,
    t.metadata,
    t.created_at,
    t.trait_last_reinforced
FROM memories_trait t
WHERE t.trait_stage NOT IN ('dissolved', 'trend')  -- trend 用 window 管理，不参与衰减
  AND t.expired_at IS NULL
WITH DATA;

-- 必须有唯一索引才能 CONCURRENTLY 刷新
CREATE UNIQUE INDEX idx_mv_trait_id ON mv_trait_decayed (id);
CREATE INDEX idx_mv_trait_user ON mv_trait_decayed (user_id, decayed_confidence DESC);
CREATE INDEX idx_mv_trait_stage ON mv_trait_decayed (user_id, trait_stage);
CREATE INDEX idx_mv_trait_embedding ON mv_trait_decayed
    USING hnsw (embedding halfvec_cosine_ops) WITH (m = 24, ef_construction = 128);
```

### 5.2 定时任务（pg_cron 或应用层 scheduler）

```python
# 定时任务清单
SCHEDULED_TASKS = {
    # 1. 刷新衰减物化视图（每 30 分钟）
    "refresh_mv_trait": {
        "cron": "*/30 * * * *",
        "sql": "REFRESH MATERIALIZED VIEW CONCURRENTLY mv_trait_decayed"
    },
    # 2. [修订] Trend 过期清除（每天凌晨 3 点）— 使用专用列
    "expire_trends": {
        "cron": "0 3 * * *",
        "sql": """
            UPDATE memories_trait
            SET trait_stage = 'dissolved',
                expired_at = NOW(),
                updated_at = NOW()
            WHERE trait_stage = 'trend'
              AND trait_window_end < NOW()
              AND trait_reinforcement_count < 2
        """,
        "description": "将超过观察窗口且未被充分强化的 trend 标记为 dissolved"
    },
    # 3. 低置信度 trait 清理（每周一 4 点）
    "dissolve_weak_traits": {
        "cron": "0 4 * * 1",
        "description": "衰减后 confidence < 0.05 的 trait 标记为 dissolved"
    },
    # 4. 访问计数更新（异步批量，每 5 分钟）
    "flush_access_counts": {
        "cron": "*/5 * * * *",
        "description": "将内存中累积的 access_count 增量批量写入 DB"
    },
    # 5. [修订] 一致性检查（每天凌晨 5 点）
    "consistency_check": {
        "cron": "0 5 * * *",
        "description": "检测孤立的 trait_evidence/memory_history/memory_sources 记录"
    },
}
```

### 5.3 矛盾处理的存储支持

```sql
-- 当新 fact 与旧 fact 矛盾时，不删除旧 fact，而是标记时间失效
UPDATE memories_fact
SET invalid_at = $new_fact_valid_at,  -- 旧事实在新事实生效时失效
    expired_at = NOW(),               -- 系统时间标记
    updated_at = NOW()
WHERE id = $old_fact_id;

-- 对于 trait 矛盾：增加矛盾计数，可能触发专项反思
UPDATE memories_trait
SET trait_contradiction_count = trait_contradiction_count + 1,
    updated_at = NOW()
WHERE id = $trait_id;

-- 记录矛盾证据
INSERT INTO trait_evidence (trait_id, memory_id, evidence_type, quality)
VALUES ($trait_id, $contradicting_memory_id, 'contradicting', $quality_grade);
```

### 5.4 [修订] 记忆操作模型（借鉴 Mem0）

每次 ingest 时 LLM 输出操作指令，遵循 ADD/UPDATE/DELETE/NOOP 四操作模型：

```python
class MemoryOperation(Enum):
    ADD = "add"           # 全新记忆，直接插入
    UPDATE = "update"     # 更新已有记忆（supersede 旧版本，设置 expired_at）
    DELETE = "delete"     # 废弃已有记忆（设置 expired_at，不物理删除）
    NOOP = "noop"         # 已存在且无变化，跳过

# 判断逻辑：
# 1. content_hash 命中 → 语义未变 → NOOP
# 2. 语义相似度 > 0.95 + content_hash 不同 → 内容有更新 → UPDATE（supersede）
# 3. 语义相似度 > 0.95 + content_hash 相同 → 完全相同 → NOOP
# 4. 无相似记忆 → ADD
# 5. LLM 判断旧记忆不再成立 → DELETE（设置 expired_at）
```

### 5.5 [修订] 乐观锁并发控制

`version` 字段用于 reflection 引擎的并发写入控制：

```sql
-- 乐观锁更新（避免多个 reflection worker 并发修改同一 trait）
UPDATE memories_trait
SET trait_confidence = $new_conf,
    trait_stage = $new_stage,
    version = version + 1,
    updated_at = NOW()
WHERE id = $trait_id
  AND version = $expected_version;
-- 返回 0 行 → 版本冲突，应用层重新读取后重试
```

### 5.6 [修订] Sleep-time 反思架构（中期演进）

V2 当前采用全量扫描反思（P0 实现简单）。中期可演进为 Letta Sleep-time 架构：

- 反思在用户不活跃时（`session_end` 触发后）异步执行
- 使用独立 worker 进程，不阻塞实时请求
- `reflection_cycles` 表已为此预留了 `started_at` / `completed_at` / `status` 字段
- Worker 通过 `conversation_sessions.last_reflected_at` 水位线确定扫描范围

---

## 6. 检索管道优化

### 6.1 Recall 查询模板

```sql
-- ==========================================
-- [修订] 通用 Recall：多类型混合 + RRF + recency/importance/trait 四维评分
-- 保留了现有 search.py 的 recency_bonus + importance_bonus 公式
-- ==========================================
SET hnsw.iterative_scan = relaxed_order;
SET hnsw.ef_search = 100;

WITH
-- Step 1: 各类型独立向量召回
trait_recall AS (
    SELECT id, 'trait' AS memory_type,
           ROW_NUMBER() OVER (ORDER BY embedding <=> $query_vec::halfvec(1024)) AS vec_rank
    FROM mv_trait_decayed  -- 使用物化视图（含衰减后置信度）
    WHERE user_id = $user_id
      AND trait_stage IN ('emerging', 'established', 'core')
    ORDER BY embedding <=> $query_vec::halfvec(1024)
    LIMIT 20
),
fact_recall AS (
    SELECT id, 'fact' AS memory_type,
           ROW_NUMBER() OVER (ORDER BY embedding <=> $query_vec::halfvec(1024)) AS vec_rank
    FROM memories_fact
    WHERE user_id = $user_id
      AND invalid_at IS NULL  -- 只召回当前有效的 fact
      AND expired_at IS NULL
      AND embedding IS NOT NULL  -- 跳过异步 embedding 未完成的记忆
    ORDER BY embedding <=> $query_vec::halfvec(1024)
    LIMIT 20
),
episodic_recall AS (
    SELECT id, 'episodic' AS memory_type,
           ROW_NUMBER() OVER (ORDER BY embedding <=> $query_vec::halfvec(1024)) AS vec_rank
    FROM memories_episodic
    WHERE user_id = $user_id
      AND embedding IS NOT NULL
    ORDER BY embedding <=> $query_vec::halfvec(1024)
    LIMIT 20
),
-- Step 2: RRF 融合
rrf AS (
    SELECT id, memory_type, SUM(1.0 / (60 + vec_rank)) AS rrf_score
    FROM (
        SELECT * FROM trait_recall
        UNION ALL SELECT * FROM fact_recall
        UNION ALL SELECT * FROM episodic_recall
    ) all_results
    GROUP BY id, memory_type
)
-- Step 3: [修订] 最终排序（RRF × (1 + recency + importance + trait_stage) 四维评分）
SELECT
    m.id, m.content, m.memory_type, m.importance, m.metadata,
    m.trait_stage, m.trait_subtype, m.trait_context,
    r.rrf_score
    * (1.0
       -- recency_bonus: 0~0.15（保留现有公式，含 arousal 情绪调节）
       -- 高 arousal 事件衰减更慢（情绪记忆效应）
       + 0.15 * EXP(
           -EXTRACT(EPOCH FROM (NOW() - COALESCE(m.valid_at, m.created_at)))
           / (2592000.0 * (1 + COALESCE((m.metadata->'emotion'->>'arousal')::float, 0) * 0.5))
       )
       -- importance_bonus: 0~0.15
       + 0.15 * COALESCE(m.importance, 0.5)
       -- trait_stage_boost: 0~0.25（仅 trait 类型生效）
       + CASE
           WHEN m.memory_type = 'trait' THEN
               CASE m.trait_stage
                   WHEN 'core'        THEN 0.25
                   WHEN 'established' THEN 0.15
                   WHEN 'emerging'    THEN 0.05
                   ELSE 0
               END
           ELSE 0
         END
    ) AS final_score
FROM rrf r
JOIN memories m ON r.id = m.id
ORDER BY final_score DESC
LIMIT $limit;
```

### 6.2 Trait 专用召回（用于 system prompt 构建）

```sql
-- 召回用户的所有活跃 trait（按子类分组，用于 prompt 构建）
SELECT
    trait_subtype,
    trait_stage,
    trait_context,
    content,
    decayed_confidence,
    trait_reinforcement_count,
    trait_first_observed
FROM mv_trait_decayed
WHERE user_id = $user_id
  AND trait_stage IN ('emerging', 'established', 'core')
  AND decayed_confidence > 0.3  -- 过滤低置信度
ORDER BY
    CASE trait_subtype
        WHEN 'core'       THEN 1
        WHEN 'preference' THEN 2
        WHEN 'behavior'   THEN 3
    END,
    decayed_confidence DESC;
```

### 6.3 时间旅行查询

```sql
-- "as of" 某时间点的知识快照
SELECT * FROM memories_fact
WHERE user_id = $user_id
  AND valid_at <= $as_of_time
  AND (invalid_at IS NULL OR invalid_at > $as_of_time)
  AND (expired_at IS NULL OR expired_at > $as_of_time);
```

---

## 7. 周边表的演进

### 7.1 KV 表的演进

#### 7.1.1 当前问题

现有 `key_values` 表存储用户 profile（职业、兴趣、personality 等），与 V2 的 trait（core/preference）职能重叠。

#### 7.1.2 方案

**渐进式废弃**：

1. **立即**：KV 表继续作为轻量级配置存储（language 偏好、UI 设置等非记忆数据）
2. **中期**：trait 系统成熟后，将 KV 中的 personality/interests/values 等迁移为 trait
3. **远期**：KV 表仅保留系统配置用途，所有用户特征由 trait 承载

```
当前 KV 中的键                    → V2 归属
profile/language                  → 保留 KV（系统配置，非记忆）
profile/identity                  → fact memory_type
profile/occupation                → fact memory_type
profile/interests                 → behavior/preference trait
profile/personality               → core trait
profile/values                    → core trait
profile/preferences               → preference trait
profile/relationships             → fact + graph_edges
```

### 7.2 [修订] emotion_profiles 表的演进

`emotion_profiles` 表与 V2 记忆分类的关系：

| 维度 | emotion_profiles | V2 记忆中的 emotion |
|------|-----------------|-------------------|
| **粒度** | 用户级聚合统计（情绪基线） | 单条记忆的事件级情绪 |
| **字段** | valence/arousal 均值、emotion_triggers JSONB | metadata.emotion（valence/arousal/label） |
| **用途** | 用户情绪画像、arousal 调节 recency 衰减 | 单条记忆的情绪标注 |

**结论**：两者职责不重叠（profiles 是聚合统计，V2 emotion 是事件级别），**当前保持不变**，与 V2 并行。

**未来演进**：emotion_profiles 中的 `emotion_triggers` 可迁移为 trait（behavior 类型，如 "讨论工作压力时情绪波动大"）。

### 7.3 [修订] documents 表的演进

现有 `documents` 表存储文件上传的 chunk 级数据（RAG 场景）。V2 中由 `memories_document` 分区承载 chunk 的向量和内容。

**迁移方案**：

- chunk 数据迁入 `memories_document` 分区（content + embedding + metadata）
- 文件级元信息（文件名、大小、MIME 类型、上传时间）保留在 `metadata` JSONB 中：`{"file_id": "uuid", "chunk_index": 0, "file_name": "report.pdf"}`
- 如果文件级查询需求频繁（如"列出用户的所有文件"），可保留原 `documents` 表的文件级行，或新建 `document_files` 表

---

## 8. 与现有代码的兼容层

### 8.1 ORM 模型变更

```python
from sqlalchemy import Column, String, Text, Integer, Float, DateTime, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from pgvector.sqlalchemy import HALFVEC
from uuid import uuid4
from sqlalchemy import func

class Memory(Base):
    __tablename__ = "memories"
    __table_args__ = (
        CheckConstraint(
            "memory_type IN ('fact', 'episodic', 'trait', 'document')",
            name="chk_memory_type",
        ),
        {"postgresql_partition_by": "LIST (memory_type)"},
    )

    id = Column(UUID, primary_key=True, default=uuid4)
    user_id = Column(String(255), nullable=False)
    memory_type = Column(String(50), nullable=False)  # 分区键

    content = Column(Text, nullable=False)
    embedding = Column(HALFVEC(1024))  # 维度由 settings.EMBEDDING_DIM 驱动

    # 双时间线
    valid_at = Column(DateTime(timezone=True))
    invalid_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    expired_at = Column(DateTime(timezone=True))

    # 版本化（乐观锁）
    version = Column(Integer, default=1)
    superseded_by = Column(UUID)  # 单列 UUID 引用

    # 通用
    importance = Column(Float, default=0.5)
    access_count = Column(Integer, default=0)
    last_accessed_at = Column(DateTime(timezone=True))
    content_hash = Column(String(32))
    metadata_ = Column("metadata", JSONB, default={})

    # Trait 专用
    trait_subtype = Column(String(20))
    trait_stage = Column(String(20))
    trait_confidence = Column(Float)
    trait_context = Column(String(20))
    trait_parent_id = Column(UUID)  # 单列 UUID 引用
    trait_reinforcement_count = Column(Integer, default=0)
    trait_contradiction_count = Column(Integer, default=0)
    trait_last_reinforced = Column(DateTime(timezone=True))
    trait_first_observed = Column(DateTime(timezone=True))
    trait_window_start = Column(DateTime(timezone=True))
    trait_window_end = Column(DateTime(timezone=True))
    trait_derived_from = Column(String(20))

    # 实体关联
    subject_entity_id = Column(UUID)
    object_entity_id = Column(UUID)
    source_episode_ids = Column(ARRAY(UUID))
```

### 8.2 向后兼容

- `add_memory()` API 保持不变，内部路由到对应分区
- `search()` API 保持不变，内部使用分区表
- 旧的 `memory_type='general'` 映射到 `'fact'`（废弃 general）
- 旧的 `memory_type='insight'` 映射到 `trait_stage='trend'`（降级为 trait）
- metadata JSONB 中仍可存储任意冷字段，热字段优先读专用列

### 8.3 [修订] 向量维度配置化

```python
# settings.py
EMBEDDING_DIM: int = 1024  # 默认 1024（Cohere），可切换为 1536（OpenAI）或 768（本地模型）

# ORM 中使用
embedding = Column(HALFVEC(settings.EMBEDDING_DIM))

# 注意：维度变更需要重建所有向量索引（DROP INDEX + CREATE INDEX）
# 这是一次性迁移操作，不需要过度工程化的动态维度支持
```

---

## 9. 实施路线图

### P0（V2 核心，与记忆分类 V2 同步实施）

| 任务 | 说明 | 工作量 |
|------|------|--------|
| 添加 trait 专用列 | 在现有表上 ADD COLUMN（12 列） | 小 |
| 添加双时间线字段 | valid_at/invalid_at/expired_at/updated_at | 小 |
| 添加 content_hash | MD5 去重字段 | 小 |
| 创建 trait_evidence 表 | 独立证据链表 | 小 |
| 创建 memory_history 表 | 变更审计日志 | 小 |
| 创建 reflection_cycles 表 | 反思记录 | 小 |
| 创建 memory_sources 表 | 对话关联溯源 | 小 |
| 更新 ORM 模型 | Memory 模型添加新字段 | 中 |
| 更新索引 | trait 专用索引 + trend 窗口索引 | 小 |
| halfvec 迁移 | vector → halfvec | 中（需重建向量索引） |
| 实现操作模型 | ADD/UPDATE/DELETE/NOOP 四操作 | 中 |
| 实现乐观锁 | version 字段并发控制 | 小 |

### P1（分区 + 高级特性，数据量增长后）

| 任务 | 说明 | 工作量 |
|------|------|--------|
| LIST 分区迁移 | 单表 → 分区表 + fillfactor/autovacuum 调优 | 大（数据迁移） |
| 物化视图 | mv_trait_decayed | 中 |
| 定时任务 | 衰减/清理/MV 刷新/一致性检查 | 中 |
| RLS 多租户 | Cloud 部署 | 中 |
| BM25 混合检索 | pg_search 或原生 tsvector | 中 |
| Sleep-time 反思 | 异步 worker 架构 | 中 |

### P2（远期优化）

| 任务 | 说明 | 触发条件 |
|------|------|---------|
| VectorChord prefilter | 替代 pgvector 索引层 | 向量数据 > 500K |
| Community 摘要节点 | 实体聚类摘要 | 实体数 > 10K |
| 图边双时间线 | graph_edges 增加 4 时间戳 | 时间旅行需求增加 |
| pg_cron 原生任务 | 替代应用层 scheduler | Railway 支持确认 |
| 两阶段反思 | 先提问再检索验证（借鉴 Generative Agents） | 反思质量需要提升 |

---

## 10. 调研来源索引

| 调研 | 核心贡献 |
|------|---------|
| #1 PG JSONB vs 专用列 | 混合 Schema 决策，TOAST 2KB 断崖，HOT 失效机制，fillfactor 调优 |
| #2 pgvector 索引优化 | halfvec 量化，HNSW + iterative_scan，分区索引 |
| #3 Mem0 存储架构 | ADD/UPDATE/DELETE/NOOP 操作模式，MD5 去重，ACID 优势 |
| #4 Zep/Graphiti 时态图 | 双时间线四时间戳，矛盾保留策略，Community 节点 |
| #5 MemGPT/Letta 分层存储 | SQL 同步+向量异步，Block 审计，Sleep-time 反思架构，乐观锁 |
| #6 学术记忆存储 | RGMem 快慢变量分离、A-MEM Zettelkasten、MemoryBank 遗忘曲线、Generative Agents 反思 |
| #7 PG 高级特性 | 物化视图、生成列、RLS、pg_cron、分区裁剪效果、autovacuum 调优 |
| #8 图存储方案对比 | PG 外键胜任 trait 层级，AGE 不推荐，Neo4j 过度设计 |

---

## 附录 A：修订记录

### 2026-02-28 修订（3 维度批判性审查）

基于"分类 V2 匹配 / 调研吸收 / PG 演进"三维度审查，应用 17 条修订：

**关键变更**：

1. **主键策略**：`PRIMARY KEY (id, memory_type)` → `PRIMARY KEY (id)` 单列 UUID + CHECK 约束，消除复合 PK 的级联复杂度
2. **新增 4 个 trait 专用列**：`trait_window_start/end`（trend 窗口）、`trait_first_observed`（首次观测）、`trait_derived_from`（产生方式）
3. **新增 `updated_at` 列**：乐观锁辅助
4. **新增 `memory_sources` 表**：对话关联溯源
5. **fillfactor + autovacuum**：各分区差异化配置（trait 80%/fact 90%/episodic 95%/document 100%）
6. **Recall 四维评分**：RRF × (1 + recency_bonus + importance_bonus + trait_stage_boost)，恢复现有 search.py 的 recency/importance 公式
7. **分区表 FK 限制**：统一应对策略（应用层保证 + 一致性检查任务）
8. **操作模型**：借鉴 Mem0 的 ADD/UPDATE/DELETE/NOOP 四操作
9. **乐观锁**：version 字段赋予并发控制语义
10. **周边表演进**：补充 emotion_profiles、documents、conversations 的演进说明

**评分变化**：

| 维度 | 修订前 | 修订后 |
|------|--------|--------|
| 分类 V2 匹配 | 7.5/10 | 9.5/10 |
| 调研吸收 | 7/10 | 9/10 |
| PG 演进 | 6/10 | 9/10 |
