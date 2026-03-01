# 记忆分类 V2 — 演进改进项

> **状态**: V2 核心已全部实现（2026-03-01 确认），以下为待实施的 P1/P2 演进功能
> **跟踪文件**: `rpiv/todo/feature-memory-v2-p1.md`（P1）、`rpiv/todo/feature-memory-v2-p2.md`（P2）
> 来源：2026-02-28 全球调研（5 份报告）
> 设计文档：`memory-classification-v2.md`
> 调研报告：`research/01~05`

---

## P1 — 强烈建议（中期实施）

### P1-1 召回即强化（测试效应）
- **来源**：Generative Agents 调研 #02
- **内容**：recall 命中 trait 时微弱强化置信度（+0.02），模拟心理学"测试效应"（Testing Effect）
- **理由**：被频繁召回的 trait 说明它在用户交互中持续相关，应自然获得巩固
- **实施点**：`recall()` 方法返回结果后，对命中的 trait 执行 `confidence += 0.02`
- **风险**：高频 recall 可能导致某些 trait 置信度虚高 → 需设单日强化上限（如每 trait 每日最多 +0.04）

### P1-2 Trait Transparency（用户可见性）
- **来源**：Personal AI 调研 #05
- **内容**：用户可查看"系统认为你是什么样的人" + 完整证据链 + 编辑/删除权
- **理由**：可解释性是信任的基础；用户应有权纠正错误的特质推断
- **实施点**：
  - SDK 层：新增 `get_user_traits(user_id)` API，返回所有 trait 及其证据链
  - 应用层（Me2）：前端展示 trait 卡片，支持用户确认/否定/删除
  - 用户确认 → 相当于 A 级证据强化；用户否定 → 直接 dissolved

### P1-3 敏感特质保护
- **来源**：Personal AI 调研 #05（参考 Google Gemini 实践）
- **内容**：心理健康、政治倾向、宗教信仰、性取向等类别不进行 trait 推断
- **理由**：隐私和伦理边界；误判这些类别的风险远大于收益
- **实施点**：reflection 引擎的 trait 生成 prompt 中增加敏感类别黑名单

### P1-4 工作记忆提交接口
- **来源**：MemGPT/Letta 调研 #03
- **内容**：SDK 层提供 `commit_working_memory(messages)` 方法，让应用层在对话过程中或结束时显式提交工作记忆
- **理由**：解耦应用层对话管理和 SDK 记忆提取，避免生命周期错位（Gemini 讨论中的核心质疑）
- **实施点**：与现有 `ingest()` 互补，`commit_working_memory` 接受完整对话上下文而非逐条消息

### P1-5 core 拆分为 personality + value
- **来源**：原始设计预留
- **内容**：当数据量足够区分 personality 和 value 时，拆分 core 子类
- **前置条件**：需要足够多用户的 core trait 数据来验证拆分的价值
- **实施点**：`trait_subtype` 增加 `personality` 和 `value` 两个值，`core` 作为向后兼容保留

---

## P2 — 可考虑（远期实施）

### P2-1 记忆间横向关联（Zettelkasten）
- **来源**：Generative Agents #02 + MemGPT #03（A-MEM NeurIPS 2025）
- **内容**：metadata 预留 `related_memories` 字段，支持 fact↔fact、episodic↔episodic、trait↔trait 的横向链接
- **价值**：recall 时可通过关联网络扩散激活，提升上下文丰富度

### P2-2 两阶段反思
- **来源**：Generative Agents #02
- **内容**：反思时先生成"关于该用户的关键问题"，再针对性检索验证，而非全量扫描
- **价值**：提高反思质量和效率，减少 token 消耗

### P2-3 Zep 双时间线
- **来源**：商业系统 #04
- **内容**：fact 区分事件时间（event_time）vs 系统时间（system_time）
- **价值**：回溯分析时更精确（"用户说上周去了北京" → event_time 是上周，system_time 是今天）
- **备注**：当前 episodic 已有 `extracted_timestamp`，fact 尚未区分

### P2-4 程序性记忆
- **来源**：认知心理学 #01
- **内容**：用户的工作流程和交互模式（"总是先画架构图再写代码"）
- **讨论**：见 memory-classification-v2.md §1.5 遗漏维度讨论（待确定处理方案）

### P2-5 前瞻记忆
- **来源**：认知心理学 #01
- **内容**：用户的未来意图和目标（"计划明年学 Rust"、"下个月要搬家"）
- **讨论**：见 memory-classification-v2.md §1.5 遗漏维度讨论（待确定处理方案）

### P2-6 实体摘要
- **来源**：Generative Agents #02（Hindsight 的 Entity Summaries）
- **内容**：为高频出现的实体（人物、组织、项目）自动生成摘要
- **价值**：recall 时提供实体级别的上下文概览

### P2-7 recall 情绪因子
- **来源**：认知心理学 #01
- **内容**：recall 评分中增加情绪匹配因子（当前对话情绪与记忆情绪的一致性加成）
- **价值**：模拟杏仁核介导的情绪记忆增强效应，在用户情绪低落时更容易召回相关情绪记忆

### P2-8 程序性记忆（behavior_kind 区分）
- **来源**：认知心理学 #01
- **内容**：在 behavior trait 内部增加 `behavior_kind` 字段，区分统计规律型（pattern："深夜活跃"）和操作流程型（procedural："先画架构图再写代码"）
- **理由**：两者生命周期和升级路径一致，无需独立 memory_type，但内容结构有差异
- **实施点**：`metadata.behavior_kind = "pattern" | "procedural"`

### P2-9 前瞻记忆（fact_temporality 区分）
- **来源**：认知心理学 #01
- **内容**：为 fact 增加 `fact_temporality` 字段，区分 current（当前事实）、prospective（未来意图）、historical（已过时）
- **理由**：前瞻意图本质是"关于未来的事实陈述"，无需独立 memory_type
- **实施点**：`metadata.fact_temporality = "current" | "prospective" | "historical"`；reflection 在前瞻事实过期时自动检查：已实现→转 current/episodic，未实现→标记 expired
