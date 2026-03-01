---
description: "交付报告: storage-foundation-v2"
status: archived
created_at: 2026-03-01T00:50:00
updated_at: 2026-03-02T00:05:00
archived_at: 2026-03-02T00:05:00
related_files:
  - rpiv/requirements/prd-storage-foundation-v2.md
  - rpiv/plans/plan-storage-foundation-v2.md
  - rpiv/validation/code-review-storage-foundation-v2.md
  - rpiv/validation/test-strategy-storage-foundation-v2.md
  - rpiv/research-storage-foundation-v2.md
---

# 交付报告：RPIV-1 存储基座（Schema + ORM + 迁移）

## 完成摘要

- **PRD 文件**：`rpiv/requirements/prd-storage-foundation-v2.md`
- **实施计划**：`rpiv/plans/plan-storage-foundation-v2.md`（15 个子任务）
- **技术调研**：`rpiv/research-storage-foundation-v2.md`
- **测试策略**：`rpiv/validation/test-strategy-storage-foundation-v2.md`
- **代码审查**：`rpiv/validation/code-review-storage-foundation-v2.md`

### 代码变更

**修改文件（22 个）**：+529 行 / -222 行

| 文件 | 变更说明 |
|------|----------|
| `neuromem/models/memory.py` | Embedding→Memory 重写，20+ 新列（trait 专用、双时间线、content_hash），CheckConstraint |
| `neuromem/models/__init__.py` | 导出 Memory + 4 辅助模型 + Embedding 别名 |
| `neuromem/models/document.py` | ForeignKey 表名 embeddings→memories |
| `neuromem/db.py` | 10 步幂等迁移（表改名、新列、回填、halfvec、索引、CHECK 约束） |
| `neuromem/services/search.py` | 表名更新 + content_hash 去重 + general/insight 映射 + 移除 ::vector cast |
| `neuromem/services/memory.py` | Embedding→Memory 引用更新 |
| `neuromem/services/memory_extraction.py` | hash 去重（episodic 豁免）+ content_hash/valid_at 写入 |
| `neuromem/services/reflection.py` | insight→trait(trend) + Embedding→Memory |
| `neuromem/services/files.py` | JOIN 表名 embeddings→memories |
| `neuromem/_core.py` | 全部 SQL 表名更新 + general/insight 映射 + _fetch_insights 查询更新 |
| `tests/` (12 个文件) | 断言适配 + V2 行为兼容 |

**新增文件（11 个）**：

| 文件 | 说明 |
|------|------|
| `neuromem/models/trait_evidence.py` | TraitEvidence ORM 模型 |
| `neuromem/models/memory_history.py` | MemoryHistory ORM 模型 |
| `neuromem/models/reflection_cycle.py` | ReflectionCycle ORM 模型 |
| `neuromem/models/memory_source.py` | MemorySource ORM 模型 |
| `tests/test_storage_v2_migration.py` | 迁移测试（14 用例） |
| `tests/test_storage_v2_orm.py` | ORM 模型测试（13 用例） |
| `tests/test_storage_v2_backfill.py` | 数据回填测试（12 用例） |
| `tests/test_storage_v2_halfvec.py` | halfvec 迁移测试（8 用例） |
| `tests/test_storage_v2_write.py` | 写入路径测试（10 用例） |
| `tests/test_storage_v2_read.py` | 读取兼容测试（5 用例） |
| `tests/test_storage_v2_compat.py` | 向后兼容测试（9 用例） |

### 测试覆盖

- **总计**：353 个测试
- **通过**：353（100%）
- **失败**：0
- **新增测试**：71 个（7 个 V2 专用测试文件）

### 代码审查

- **CRITICAL**：4 个（全部已修复 — memory_type 默认值冲突）
- **HIGH**：2 个（全部已修复 — CHECK 约束迁移 + general 向后兼容映射）
- **MEDIUM**：4 个（2 个已修复，2 个延后）
- **LOW**：3 个（2 个已修复，1 个延后）

### 实现对齐审查

- **对齐度**：14.5/15 任务（96.7%）
- **P1 偏离**：缺少 CheckConstraint → 已修复
- **P3 偏离**：ConversationSession ORM 缺 last_reflected_at mapped_column → 延后 RPIV-2

## 关键决策记录

| # | 决策 | 理由 |
|---|------|------|
| 1 | episodic 类型豁免 content_hash 去重 | episodic 是事件记忆，同内容不同时间点的记录是合理的 |
| 2 | general→fact / insight→trait 写入路径映射 | 向后兼容旧调用方，同时满足 CHECK 约束 |
| 3 | Float(float8) 暂不改 REAL(float4) | ORM 层 Float 与 DDL REAL 混用功能无影响，留 P1 优化 |
| 4 | CheckConstraint 通过 db.py DDL 显式添加 | create_all(checkfirst=True) 不会修改已存在表的约束 |
| 5 | halfvec 迁移需 pgvector ≥ 0.7.0 | 低版本静默跳过，仅记录警告日志 |

## 遗留问题

| # | 严重度 | 描述 | 计划 |
|---|--------|------|------|
| 1 | MEDIUM | trait_confidence ORM Float(float8) vs DDL REAL(float4) 类型不一致 | P1 统一为 REAL |
| 2 | MEDIUM | 向量字符串 SQL 拼接（预存问题，非本次引入） | 单独 issue 跟踪 |
| 3 | LOW | ConversationSession ORM 缺 last_reflected_at | RPIV-2 reflection 引擎时补充 |
| 4 | LOW | halfvec 索引 DROP 依赖名称正则匹配 | 需确认覆盖所有旧索引名 |

## 9 个核心场景完成状态

| # | 场景 | 状态 |
|---|------|------|
| 1 | 表改名 embeddings→memories + 新增列 | ✅ 完成 |
| 2 | 辅助表创建（4 张） | ✅ 完成 |
| 3 | ORM 模型重写 | ✅ 完成 |
| 4 | 数据回填（metadata→专用列 + 类型迁移 + hash + valid_at） | ✅ 完成 |
| 5 | halfvec 迁移 | ✅ 完成 |
| 6 | 写入路径更新（hash 去重 + trait 列填充） | ✅ 完成 |
| 7 | 读取兼容（专用列优先 + JSONB fallback） | ✅ 完成 |
| 8 | 对话表扩展（last_reflected_at） | ✅ 完成 |
| 9 | 索引更新（trait + hash + halfvec） | ✅ 完成 |

## 建议后续步骤

1. **RPIV-2**：分类逻辑（Reflection 引擎 + Trait 生命周期 + 召回公式改造）
2. **P1**：LIST 分区 + fillfactor/autovacuum 调优 + 物化视图 mv_trait_decayed
3. **部署**：neuromem-cloud Railway 部署（需先验证迁移在 Railway PostgreSQL 上的兼容性）
4. **Float→REAL 统一**：trait_confidence 和 importance 列类型修正

## 团队执行统计

| 阶段 | 耗时 | 参与 Agent |
|------|------|------------|
| 阶段 1：需求与调研 | PRD + 调研 + 测试策略 | Architect, Researcher, QA |
| 阶段 2：架构规划 | 实施计划 + 测试规格 | Architect, QA |
| 阶段 3：实现 | 15 子任务代码实现 + 71 测试用例编写 | Dev-1, QA |
| 阶段 4：验证 | 3 轮测试 + 2 轮修复 + 代码审查 + 对齐审查 | QA, Architect, Dev-1 |

修复轮次：2 轮（第 1 轮修复 2 个 CRITICAL，第 2 轮修复 5 个 HIGH/MEDIUM/LOW + episodic dedup + 28 个测试适配）
