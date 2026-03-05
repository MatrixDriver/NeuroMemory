---
description: "交付报告: context-aware-recall-v2"
status: completed
created_at: 2026-03-05T17:30:00
updated_at: 2026-03-05T17:30:00
archived_at: null
related_files:
  - rpiv/requirements/prd-context-aware-recall-v2.md
  - rpiv/plans/plan-context-aware-recall-v2.md
  - rpiv/validation/code-review-context-aware-recall-v2.md
  - rpiv/validation/test-strategy-context-aware-recall-v2.md
  - rpiv/research-context-aware-recall-v2.md
---

# 交付报告: context-aware-recall-v2

## 完成摘要

### 过程文件
- PRD: `rpiv/requirements/prd-context-aware-recall-v2.md`
- 技术调研: `rpiv/research-context-aware-recall-v2.md`
- 实施计划: `rpiv/plans/plan-context-aware-recall-v2.md`
- 测试策略: `rpiv/validation/test-strategy-context-aware-recall-v2.md`
- 代码审查: `rpiv/validation/code-review-context-aware-recall-v2.md`

### 代码变更

**修改的文件:**
- `neuromem/services/memory_extraction.py` — extraction prompt 增加 context 字段(中/英双语) + _store_facts/_store_episodes 写入 trait_context + _validate_context() 公共验证函数
- `neuromem/services/search.py` — context_bonus_sql 去掉 memory_type='trait' 限制, 引用 ContextService 参数常量
- `neuromem/services/context.py` — 参数更新为 medium 组(MARGIN_THRESHOLD=0.03, MAX_CONTEXT_BOOST=0.15, GENERAL_CONTEXT_BOOST=0.10)

**新建的文件:**
- `scripts/backfill_context.py` — 历史 fact/episodic context 回填脚本(embedding 相似度, 零 LLM 消耗)
- `scripts/eval_context_params.py` — 参数 A/B 评估脚本(MRR@3/MRR@5)

**测试文件:**
- `tests/test_recall_context_match.py` — 扩展: fact/episodic context boost 测试 + NULL 不惩罚测试
- `tests/test_memory_extraction.py` — 新增: prompt 内容 + context 写入 + 降级测试
- `tests/test_parameter_tuning.py` — 新建: MRR 计算 + 参数组验证(15 用例)
- `tests/test_context_extraction.py` — 新建: 提取标注 + 白名单 + 降级(16 用例)
- `tests/test_context_backfill.py` — 新建: 回填逻辑 + DB 集成(12 用例)
- `tests/test_recall_memory_context_boost.py` — 新建: 记忆级 context boost + 排序(9 用例)

### 测试覆盖
- 单元测试: 60/60 通过
- 集成测试: 需要 PostgreSQL 5436, 本次未运行(Docker 未启动)
- 代码审查: 0 CRITICAL, 0 HIGH, 2 MEDIUM(已修复), 3 LOW(已修复)

### 实现对齐
- Architect 对比 10/10 个 Plan Task: **全部对齐, 无偏离无遗漏**

## 关键决策记录

1. **参数暂用 medium 组**: MARGIN_THRESHOLD=0.03, MAX_CONTEXT_BOOST=0.15。评估脚本已就绪, 待手动标注数据集后可运行 A/B 实验确认最优参数
2. **复用 trait_context 列**: 零 DDL 变更, 在 Memory model 注释中说明该列用于所有记忆类型
3. **context 验证提取为公共函数**: _validate_context() 避免 _store_facts/_store_episodes 重复代码
4. **search.py import 移到顶部**: 消除函数内 import, 保持代码风格一致

## 遗留问题

1. **评估数据集待标注**: 需要用户手动标注 10-20 个查询的 expected top-3 记忆, 才能运行 eval_context_params.py 确认最优参数组
2. **集成测试未运行**: 需要启动 Docker (PostgreSQL 5436) 后运行 `uv run pytest tests/ -v` 完成集成测试验证
3. **历史数据回填待执行**: backfill_context.py 脚本已就绪, 需在目标数据库上运行一次
4. **Cloud 端需升级 SDK**: 代码合入发布后, neuromem-cloud 的 pyproject.toml 需更新 neuromem 版本约束

## 建议后续步骤

1. 启动 Docker, 运行全量测试确认集成测试通过
2. 手动标注评估数据集 -> 运行 eval_context_params.py -> 确认参数
3. 发布 SDK 新版本 (0.9.14)
4. 在 jackylk space 运行 backfill_context.py 回填历史数据
5. neuromem-cloud 升级 SDK 版本并部署
6. 线上验证 recall context boost 效果
