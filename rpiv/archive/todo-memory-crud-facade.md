---
title: "NeuroMemory Facade 暴露记忆 CRUD 公共 API"
type: todo
status: archived
priority: medium
created_at: 2026-03-03T12:00:00
updated_at: 2026-03-03T18:30:00
archived_at: 2026-03-03T18:30:00
---

# NeuroMemory Facade 暴露记忆 CRUD 公共 API

## 背景

`MemoryService` 已实现 `list_all_memories()`、`update_memory()`、`delete_memory()`，但 `NeuroMemory` Facade 未暴露这些方法。Cloud 和 Me2 目前只能通过 `nm._db.session()` + `MemoryService` 间接调用，不属于公共 API。

## 待办

1. `NeuroMemory` 新增 `list_memories()`、`update_memory()`、`delete_memory()` 公共方法
2. 委托到 `MemoryService` 对应方法
3. 删除时增加级联清理：同步删除 `memory_history`、`trait_evidence` 等关联记录
4. 修复 Cloud MCP `delete_memory` 工具 docstring 与实现不符的问题（声称清理关联数据但实际未执行）

## 来源

从 `neuromem-cloud/rpiv/todo/feature-memory-edit-management.md`（已完成）的遗留问题拆出。
