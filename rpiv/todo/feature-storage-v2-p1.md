---
title: "存储方案 V2 待实施优化（P1）"
type: feature
status: open
priority: low
created_at: 2026-03-01T20:30:00
updated_at: 2026-03-01T20:30:00
---

# 存储方案 V2 待实施优化（P1）

## 动机与背景

storage-schema-v2.md 的 P0 存储任务已基本完成（表结构、辅助表、索引、halfvec、双时间线、RRF 搜索等），但 P1 优化层尚未实施。这些优化在数据量增长后将变得必要。

来源：`docs/design/storage-schema-v2.md` §9 P1

## 功能清单

### 1. LIST 分区迁移

- **描述**：将单表 `memories` 按 `memory_type` 拆分为 4 个 LIST 分区（fact/episodic/trait/document）
- **收益**：分区裁剪（67-83% 时间缩减）、独立 HNSW 索引参数、独立 VACUUM/REINDEX
- **涉及文件**：`db.py`（分区表 DDL）、需要数据迁移脚本
- **触发条件**：memories 表行数 > 100K 或 trait 查询延迟明显
- **工作量**：大（数据迁移 + 测试）
- **附带**：fillfactor/autovacuum 各分区差异化配置（trait 80%/fact 90%/episodic 95%）

### 2. 物化视图 mv_trait_decayed

- **描述**：预计算 trait 的衰减后置信度，避免每次 recall 实时计算
- **当前方案**：`trait_engine.apply_decay()` 每次反思时实时计算，recall 时通过 `search.py` 的 Python 代码计算
- **收益**：recall SQL 可直接使用衰减后置信度排序
- **涉及文件**：`db.py`（CREATE MATERIALIZED VIEW）、定时刷新任务
- **触发条件**：trait 数量 > 1000 或 recall 延迟 > 200ms

### 3. 定时任务体系

- **描述**：建立系统化的定时任务（衰减/清理/MV 刷新/一致性检查）
- **设计方案**（storage-schema-v2.md §5.2）：
  - 每 30 分钟：刷新物化视图
  - 每天凌晨 3 点：trend 过期清除
  - 每周一 4 点：低置信度 trait dissolved
  - 每 5 分钟：access_count 批量写入
  - 每天凌晨 5 点：一致性检查（孤立 evidence/history/sources）
- **涉及文件**：新增 scheduler 模块或使用 pg_cron

### 4. ~~乐观锁启用~~ ✓ 已实现 2026-03-03

- **描述**：trait_engine 中使用 `version` 字段进行并发控制
- **当前状态**：已在 TraitEngine 所有 8 个修改方法中添加 `_bump_version()` 调用
- **涉及文件**：`services/trait_engine.py`（所有 trait 更新操作递增 version）
- **工作量**：小

### 5. 四操作模型泛化

- **描述**：将 ADD/UPDATE/DELETE/NOOP 四操作模型从 Graph 模块泛化到 Memory 表
- **当前状态**：仅 `graph_memory.py` 实现了此模型，Memory 表使用 supersede 机制
- **涉及文件**：`services/memory_extraction.py`、`_core.py`
- **工作量**：中

### 6. Sleep-time 反思守护进程

- **描述**：独立 worker 守护进程，定期扫描待反思用户
- **当前状态**：反思在消息提交后/会话结束时触发（事件驱动），无独立后台 daemon
- **涉及文件**：新增 worker 模块
- **工作量**：中

## 用户场景

1. **场景 A**：用户积累了 50K+ 条记忆，trait 查询从 50ms 劣化到 500ms → 分区迁移后恢复
2. **场景 B**：两个反思任务并发修改同一 trait → 乐观锁防止置信度被覆盖

## MVP 定义

按优先级分批实施：
1. 乐观锁启用（最小改动，防并发风险）
2. 定时任务体系（数据清理基础设施）
3. LIST 分区迁移（数据量增长后）
4. 物化视图（分区完成后）

## 备选方案

无

## 参考

- 设计文档：`docs/design/storage-schema-v2.md` §9 P1、§5 生命周期管理
