# 特性开发文档目录

本目录用于存放 neuromem 项目的特性开发文档（Feature Development Plans）。

## 目录说明

特性开发文档是基于设计文档（如 `docs/SESSION_MEMORY_DESIGN.md`）创建的详细实施计划，包含：

- 功能描述和用户故事
- 问题陈述和解决方案
- 详细的实施步骤
- 测试策略和验证命令
- 验收标准

## 文档列表

- [session-memory-management.md](./session-memory-management.md) - Session 记忆管理系统

## 文档命名规范

特性开发文档使用 kebab-case 命名，例如：
- `session-memory-management.md`
- `user-authentication.md`
- `distributed-session.md`

## 文档结构

每个特性开发文档应包含以下部分：

1. **功能描述** - 功能概述和核心特性
2. **用户故事** - 从用户角度描述需求
3. **问题陈述** - 要解决的具体问题
4. **解决方案陈述** - 提议的解决方案
5. **上下文参考** - 相关代码文件和文档
6. **实施计划** - 分阶段的实施步骤
7. **逐步任务** - 详细的任务清单
8. **测试策略** - 测试方法和边缘情况
9. **验证命令** - 各层级的验证步骤
10. **验收标准** - 完成标准检查清单

## 使用方式

1. 阅读对应的设计文档（如 `docs/SESSION_MEMORY_DESIGN.md`）
2. 查看特性开发文档了解实施细节
3. 按照文档中的步骤逐步实施
4. 完成每个任务后执行验证命令
5. 满足所有验收标准后标记为完成

## 相关文档

- [工程推进流程指南](../ENGINEERING_WORKFLOW.md) — core_piv_loop、validation、create-prd 等命令的用法与顺序
- [主架构文档](../ARCHITECTURE.md)
- [主架构文档](../ARCHITECTURE.md)
- [Session 记忆管理设计文档](../SESSION_MEMORY_DESIGN.md)
