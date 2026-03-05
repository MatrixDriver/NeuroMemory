---
description: "需求摘要: context-aware-recall-v2"
status: pending
created_at: 2026-03-05T16:30:00
updated_at: 2026-03-05T16:30:00
archived_at: null
---

# 需求摘要: context-aware-recall-v2

## 产品愿景
- **核心问题**: context-aware recall v1 的 margin 阈值(0.05)过高导致大多数查询被判为 general, context boost 力度(0.10)不足以显著影响排序
- **价值主张**: 通过参数调优 + 记忆级 context 标注, 让召回结果更精准地匹配用户当前语境
- **目标用户**: neuromem SDK/Cloud 的所有用户(开发者通过 API 集成)
- **产品形态**: SDK 内部优化 + 提取流程增强, 无新 API 接口

## 核心场景(按优先级排序)
1. **P0 参数调优**: 通过 A/B 实验找到最优 margin 阈值和 boost 力度组合
2. **P1 提取时标注**: fact + episodic 记忆在 LLM 提取时附带 context 标签
3. **P1 历史回填**: 用 embedding 相似度一次性回填已有 fact/episodic 的 context
4. **P1 召回 boost 增强**: 利用记忆级 context 标签做更精准的 boost

## 产品边界

### MVP 范围内
- 3 组参数 A/B 对比: baseline(0.05/0.10) vs medium(0.03/0.15) vs aggressive(0.02/0.20)
- 手动标注 10-20 个查询的 ground truth, MRR(Mean Reciprocal Rank) 评估
- fact + episodic 提取时增加 context 字段(复用 trait_context 列)
- LLM 标注失败降级为 general
- embedding 相似度回填历史数据(零 LLM 消耗)
- 标签体系: work / personal / social / learning / general (5 类, 不扩展)

### 明确不做
- 不扩展标签体系(不加 health/finance)
- 不支持用户自定义 context 类别
- 不改变 API 接口(context 信息已在 recall response 中)

### 后续版本考虑
- 可配置标签体系
- 基于用户反馈的自适应参数调整

## 已知约束
- 不消耗用户 LLM API(回填用 embedding, 提取标注复用已有 LLM 调用)
- 复用 trait_context 列(已有索引, 无 DDL 变更)
- 线上真实数据(jackylk space, ~110 条记忆)做评估
- trait 已在之前回填过 context, 本次仅需回填 fact + episodic

## 各场景功能要点

### 场景 1: P0 参数调优
- **功能点**: 构造评估数据集 -> 3 组参数各跑一遍 recall -> 计算 MRR -> 选最优
- **关键交互**: 用户手动标注 10-20 个查询的 expected top-3, 脚本自动计算 MRR
- **异常处理**: 三组 MRR 无显著差异 -> 保留当前参数, 记录结论
- **参数组**:
  - baseline: MARGIN_THRESHOLD=0.05, MAX_CONTEXT_BOOST=0.10
  - medium: MARGIN_THRESHOLD=0.03, MAX_CONTEXT_BOOST=0.15
  - aggressive: MARGIN_THRESHOLD=0.02, MAX_CONTEXT_BOOST=0.20

### 场景 2: P1 提取时标注
- **功能点**: 修改 extraction prompt, 要求 LLM 在提取 fact/episodic 时同时输出 context 标签
- **字段**: 复用 trait_context 列(fact/episodic 表均已有此列或可共用)
- **标签白名单**: work, personal, social, learning, general
- **关键交互**: extraction prompt 增加 context 字段说明 + 示例
- **异常处理**: LLM 返回无效/缺失 context -> 降级为 general

### 场景 3: P1 历史回填
- **功能点**: 迁移脚本读取所有 fact/episodic 的 embedding, 与 4 个 context prototype 计算余弦相似度, 取最高分标注
- **关键交互**: 一次性运行, 幂等可重跑
- **异常处理**: 相似度最高分低于阈值 -> 标 general
- **前置条件**: context prototype 向量已在 ContextService 中定义

### 场景 4: P1 召回 boost 增强
- **功能点**: recall 时不仅用 query 的 inferred context boost, 还与每条记忆自身的 context 标签做匹配加分
- **逻辑**: query context == memory context -> 额外 boost; 不匹配 -> 不惩罚
- **异常处理**: memory context 为 general 或 NULL -> 不参与 boost(既不加分也不减分)
