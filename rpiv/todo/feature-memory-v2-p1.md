---
title: "记忆分类 V2 中期演进功能（P1）"
type: feature
status: open
priority: medium
created_at: 2026-03-01T20:00:00
updated_at: 2026-03-01T20:00:00
---

# 记忆分类 V2 中期演进功能（P1）

## 动机与背景

V2 核心设计（4 类记忆、trait 三层子类、生命周期、reflection 引擎）已全部实现。以下 6 个 P1 功能是设计文档中规划的中期演进方向，旨在提升 trait 系统的精度、可用性和用户体验。

来源：`docs/design/memory-classification-v2.md` §8.2

## 功能清单

### 1. 召回即强化（Recall-as-Reinforcement）

- **描述**：recall 命中 trait 时微弱强化置信度（+0.02），模拟心理学"测试效应"
- **理论依据**：Generative Agents 调研 #02
- **涉及文件**：`services/search.py`（recall 流程）、`services/trait_engine.py`（reinforce_trait）
- **MVP**：recall 返回 trait 结果时，异步调用 `reinforce_trait(quality="D", factor=0.02)`

### 2. Trait Transparency（特质透明化）

- **描述**：用户可查看"系统认为你是什么样的人" + 证据链 + 编辑/删除权
- **理论依据**：Personal AI 调研 #05
- **涉及文件**：`_core.py`（新增公共 API）、可能需要新增 `services/trait_visibility.py`
- **MVP**：提供 `get_user_traits(user_id)` API，返回所有 emerging+ 阶段的 trait 及其证据链；提供 `delete_trait(trait_id)` 和 `edit_trait(trait_id, content)` API

### 3. 敏感特质保护

- **描述**：心理健康、政治倾向、宗教信仰等类别不进行 trait 推断
- **理论依据**：Personal AI 调研 #05
- **涉及文件**：`services/reflection.py`（reflection prompt 中增加排除规则）、`services/trait_engine.py`（创建前校验）
- **MVP**：定义敏感类别列表，reflection prompt 明确指示不推断此类特质；trait_engine 创建时增加分类校验拦截

### 4. 工作记忆提交接口

- **描述**：SDK 层提供 `commit_working_memory()` 方法，允许应用层将当前对话的工作记忆显式提交为长期记忆
- **理论依据**：MemGPT 调研 #03
- **涉及文件**：`_core.py`（新增公共 API）
- **MVP**：`commit_working_memory(user_id, messages: list[dict])` → 批量 ingest + 触发一次 reflection

### 5. core 拆分为 personality + value

- **描述**：当数据量支撑区分时，将 core 子类拆分为 personality（人格特质）和 value（价值观）
- **涉及文件**：`models/memory.py`（trait_subtype 约束）、`services/trait_engine.py`（升级逻辑）、`services/reflection.py`（prompt 调整）
- **MVP**：trait_subtype 增加 `personality` 和 `value`；升级路径：preference → personality 或 preference → value；保留 `core` 作为兼容别名
- **前置条件**：需要积累足够的 core 级 trait 数据来验证区分的必要性

### 6. trait 对 recall 的主动影响

- **描述**：检测到用户特质后主动影响回复策略（如：用户"偏好简洁" → 自动调整回复长度）
- **涉及文件**：`services/search.py`（recall 结果附带 trait 提示）、应用层 prompt 构建
- **MVP**：recall 结果中增加 `active_traits` 字段，包含当前用户的 established+ 级 trait，供应用层在 prompt 中使用

## 用户场景

1. **场景 A**：用户频繁查询"我的编程习惯"相关话题，系统通过召回即强化自动巩固相关 trait
2. **场景 B**：用户想了解系统对自己的画像，通过 Trait Transparency API 查看并修正不准确的推断
3. **场景 C**：用户在对话中提到政治观点，系统不将其归纳为 trait，保护隐私

## 备选方案

无

## 参考

- 设计文档：`docs/design/memory-classification-v2.md` §8.2
- 调研报告：`docs/design/research/02-generative-agents.md`、`03-memgpt-letta.md`、`05-personal-ai.md`
