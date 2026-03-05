---
description: "产品需求文档: context-aware-recall-v2"
status: completed
created_at: 2026-03-05T17:00:00
updated_at: 2026-03-05T17:30:00
archived_at: null
---

# PRD: Context-Aware Recall V2 - 参数调优 + 记忆级 Context 标注

## 1. 执行摘要

Context-Aware Recall V1 引入了基于 embedding 原型向量的查询语境推断机制，但实际效果有限：margin 阈值 0.05 过高导致大多数查询被判定为 `general`，context boost 力度 0.10 不足以显著影响排序结果。V2 旨在通过两条路径解决此问题：

1. **参数调优**（P0）：通过 A/B 实验在真实数据上找到最优的 margin 阈值和 boost 力度组合，用 MRR 指标量化评估。
2. **记忆级 Context 标注**（P1）：将 context 标签从"仅在 recall 时推断查询语境"扩展到"提取时即标注每条 fact/episodic 记忆的语境"，使 recall 时可做记忆-查询双向匹配，大幅提升 context boost 精准度。

**核心价值**：让召回结果更精准地匹配用户当前语境，减少跨域干扰（如工作查询混入生活记忆），无需新增 API 接口，对用户完全透明。

**MVP 目标**：在 jackylk 的真实数据（~110 条记忆）上，通过参数调优和记忆级标注使 context-matched 查询的 MRR 提升 >=10%。

## 2. 使命

**使命声明**：让 neuromem 的记忆检索具备语境感知能力，自动将查询结果聚焦到与当前话题最相关的记忆，减少噪声干扰。

**核心原则**：
1. **零额外 LLM 消耗**：context 标注复用已有的 extraction LLM 调用，历史回填使用 embedding 相似度（零 LLM 成本）
2. **渐进增强，不破坏现有行为**：context boost 只做加分不做惩罚，未标注记忆不受影响
3. **数据驱动决策**：参数选择基于 MRR 实验结果，不凭直觉
4. **复用已有基础设施**：复用 `trait_context` 列（已有索引），复用 `ContextService` 原型向量
5. **最小改动原则**：不扩展标签体系，不改变公共 API

## 3. 目标用户

**主要用户角色**：neuromem SDK/Cloud 的开发者用户，通过 `nm.ingest()` / `nm.recall()` API 集成记忆功能到自己的 AI agent。

**技术舒适度**：中高级 Python 开发者，熟悉 async/await 和数据库操作。

**关键需求和痛点**：
- 当前 recall 对工作/生活/社交等不同语境的查询返回混杂结果
- 用户期望"问工作问题时优先返回工作相关记忆"，但 V1 的 context boost 太弱几乎无效
- 不希望为 context 功能支付额外 LLM API 费用

## 4. MVP 范围

### 范围内

**P0 参数调优**：
- ✅ 构造评估数据集：手动标注 10-20 个查询的 ground truth（expected top-3 记忆）
- ✅ 实现 3 组参数 A/B 对比评估脚本
  - baseline: `MARGIN_THRESHOLD=0.05`, `MAX_CONTEXT_BOOST=0.10`
  - medium: `MARGIN_THRESHOLD=0.03`, `MAX_CONTEXT_BOOST=0.15`
  - aggressive: `MARGIN_THRESHOLD=0.02`, `MAX_CONTEXT_BOOST=0.20`
- ✅ 计算每组参数的 MRR（Mean Reciprocal Rank）指标
- ✅ 选择最优参数组并更新 `ContextService` 类常量

**P1 提取时标注**：
- ✅ 修改 extraction prompt（中/英双语），要求 LLM 在提取 fact/episodic 时同时输出 `context` 字段
- ✅ `context` 字段白名单：`work` / `personal` / `social` / `learning` / `general`
- ✅ LLM 返回无效/缺失 context 时降级为 `general`
- ✅ 存储到 `trait_context` 列（fact/episodic 复用 trait 已有的列）

**P1 历史回填**：
- ✅ 实现迁移脚本：读取所有 fact/episodic 的 embedding，与 4 个 context prototype 计算余弦相似度
- ✅ 取最高分标注，低于阈值时标为 `general`
- ✅ 脚本幂等可重跑

**P1 召回 boost 增强**：
- ✅ recall 时对 fact/episodic 也应用 context bonus（当前仅 trait 有 context bonus）
- ✅ 逻辑：query context == memory context -> 额外 boost；不匹配 -> 不惩罚
- ✅ memory context 为 `general` 或 NULL -> 不参与 boost

### 范围外

- ❌ 不扩展标签体系（不加 health/finance 等新类别）
- ❌ 不支持用户自定义 context 类别
- ❌ 不改变公共 API 接口签名（context 信息已在 recall response metadata 中）
- ❌ 不修改 trait 的 context 处理（trait 已在 V1 中完成 context 标注和 boost）
- ❌ 不实现自适应参数调整（基于用户反馈动态调参）

## 5. 用户故事

**US-1**：作为 AI agent 开发者，我希望当用户在工作场景下提问时，recall 优先返回工作相关的记忆（如职业、项目经验），以便 agent 给出更相关的回复。

> 示例：用户之前 ingest 了"我在 Google 担任高级工程师"和"周末去了西湖"，当 query="帮我写代码" 时，应优先返回工作相关记忆。

**US-2**：作为 AI agent 开发者，我希望 context 功能对用户完全透明——无需额外配置或 API 参数，ingest 和 recall 自动处理语境信息。

**US-3**：作为 neuromem 运维者，我希望有一个一次性迁移脚本可以回填历史记忆的 context 标签，且脚本幂等可安全重跑。

**US-4**：作为 SDK 贡献者，我希望参数选择基于量化实验（MRR），而非拍脑袋决定，确保改动有可验证的效果提升。

**US-5**：作为 neuromem Cloud 运营者，我不希望 context 功能引入额外的 LLM API 调用费用——提取时标注应复用已有的 extraction LLM 调用，历史回填应使用 embedding 相似度。

## 6. 核心架构与模式

### 当前架构（V1）

```
recall(query)
  → ContextService.infer_context(query_embedding) → (context_label, confidence)
  → SearchService: 仅对 memory_type='trait' 应用 context_bonus SQL
```

### 目标架构（V2）

```
ingest(content)
  → MemoryExtractionService._classify_messages() → LLM 同时输出 context 字段
  → _store_facts() / _store_episodes() → 写入 trait_context 列

recall(query)
  → ContextService.infer_context(query_embedding) → (context_label, confidence)
  → SearchService: 对 trait + fact + episodic 均应用 context_bonus SQL

migrate_context_backfill()
  → 读取 fact/episodic embedding → cosine_similarity(embedding, prototype) → 写入 trait_context
```

### 关键设计决策

1. **复用 `trait_context` 列**：该列已存在于 `memories` 表，已有索引 `idx_trait_context`，fact/episodic 之前为 NULL，现在填充 context 标签。无需 DDL 变更。
2. **context bonus 从 trait-only 扩展到全类型**：修改 `SearchService` 的 `context_bonus_sql` 生成逻辑，去掉 `memory_type = 'trait'` 条件限制。
3. **提取时标注零额外成本**：在已有的 extraction prompt 中增加 `context` 字段说明，LLM 在同一次调用中同时输出，无额外 API 调用。

## 7. 功能规格

### 7.1 参数 A/B 评估（P0）

**评估数据集**：
- 使用 jackylk 的真实数据（~110 条记忆，PostgreSQL 5432）
- 手动标注 10-20 个查询，每个查询标注 expected top-3 记忆 ID
- 查询覆盖 4 个 context 类别 + general

**评估脚本**（`scripts/eval_context_params.py`）：
- 输入：查询数据集 JSON、参数组配置
- 对每组参数：临时修改 `ContextService` 常量 → 执行 recall → 收集 top-K 结果
- 计算 MRR@3 和 MRR@5
- 输出：对比表 + 推荐参数组

**参数组**：

| 参数组 | MARGIN_THRESHOLD | MAX_CONTEXT_BOOST | GENERAL_CONTEXT_BOOST |
|--------|-----------------|-------------------|----------------------|
| baseline | 0.05 | 0.10 | 0.07 |
| medium | 0.03 | 0.15 | 0.10 |
| aggressive | 0.02 | 0.20 | 0.14 |

### 7.2 提取时 Context 标注（P1）

**修改文件**：`neuromem/services/memory_extraction.py`

**Prompt 变更**：在 fact 和 episode 的 JSON 格式说明中增加 `context` 字段：
```
- context: 该记忆所属的语境类别（必填）
  * "work": 工作、编程、项目、会议、职业相关
  * "personal": 个人生活、家庭、健康、兴趣爱好
  * "social": 社交关系、聚会、人际交往
  * "learning": 学习、教育、理论、研究
  * "general": 无法明确归类时使用
```

**存储变更**：
- `_store_facts()`: 从 LLM 返回的 fact dict 中读取 `context` 字段，写入 `Memory.trait_context`
- `_store_episodes()`: 同上
- 无效值降级：`context not in {"work", "personal", "social", "learning", "general"}` → `"general"`

### 7.3 历史 Context 回填（P1）

**迁移脚本**（`scripts/backfill_context.py`）：

```python
# 伪代码
for memory in memories where memory_type in ('fact', 'episodic') and trait_context is NULL:
    similarities = {ctx: cosine_similarity(memory.embedding, prototype[ctx]) for ctx in prototypes}
    best_ctx, best_score = max(similarities.items(), key=lambda x: x[1])
    second_score = sorted(similarities.values(), reverse=True)[1]
    margin = best_score - second_score
    if margin >= MARGIN_THRESHOLD:
        memory.trait_context = best_ctx
    else:
        memory.trait_context = "general"
```

**关键参数**：使用 P0 阶段确定的最优 MARGIN_THRESHOLD。

**幂等性**：脚本只更新 `trait_context IS NULL` 的记忆，已标注的不覆盖。可通过 `--force` 参数强制全量重写。

### 7.4 召回 Context Boost 增强（P1）

**修改文件**：`neuromem/services/search.py`

**当前逻辑**（仅 trait）：
```sql
CASE
  WHEN memory_type = 'trait' AND trait_context = '{query_context}' THEN {0.10 * confidence}
  WHEN memory_type = 'trait' AND trait_context = 'general' THEN {0.07 * confidence}
  ELSE 0
END
```

**目标逻辑**（全类型）：
```sql
CASE
  WHEN trait_context = '{query_context}' THEN {MAX_CONTEXT_BOOST * confidence}
  WHEN trait_context = 'general' THEN {GENERAL_CONTEXT_BOOST * confidence}
  WHEN trait_context IS NULL THEN 0
  ELSE 0
END
```

变更点：去掉 `memory_type = 'trait'` 条件，使 fact/episodic 也能获得 context bonus。

## 8. 技术栈

- **语言**：Python 3.11+，类型提示
- **数据库**：PostgreSQL + pgvector + pg_search（ParadeDB BM25）
- **ORM**：SQLAlchemy 2.0 async
- **测试**：pytest + asyncio_mode="auto"
- **向量计算**：纯 Python cosine_similarity（`ContextService` 已有实现）
- **LLM**：OpenAI-compatible API（DeepSeek/SiliconFlow），通过 `LLMProvider` 抽象

无新增依赖。

## 9. 安全与配置

**安全**：无新增安全面。context 标签为内部 metadata，不暴露敏感信息。

**配置**：
- 参数通过 `ContextService` 类常量管理（`MARGIN_THRESHOLD`、`MAX_CONTEXT_BOOST`、`GENERAL_CONTEXT_BOOST`）
- P0 完成后直接更新常量值，无需运行时配置
- 回填脚本通过命令行参数配置：`--user-id`、`--database-url`、`--force`

**部署**：
- SDK 层改动，发布新版本到 PyPI
- Cloud 端升级 SDK 版本即可，无独立改动
- 回填脚本需在目标数据库上运行一次

## 10. API 规范

无新增 API。现有 `recall()` 返回值中的 `metadata.context_match` 字段已包含 context bonus 信息，无需变更。

`ingest()` 行为变更（内部，对用户透明）：
- 提取的 fact/episodic 记忆自动附带 `trait_context` 标签
- 不影响返回值结构

## 11. 成功标准

**MVP 成功定义**：
- ✅ 参数 A/B 实验完成，产出明确的参数选择和 MRR 数据
- ✅ 新 ingest 的 fact/episodic 自动携带 context 标签（覆盖率 > 95%，`general` 降级的 < 5% 为正常）
- ✅ 历史数据回填完成（jackylk space 全量记忆标注）
- ✅ recall context boost 扩展到 fact/episodic，MRR 提升 >= 10%

**质量指标**：
- ✅ 所有现有测试通过，无回归
- ✅ 新增针对 context 标注和 boost 的单元测试
- ✅ extraction prompt 变更不影响现有 fact/episodic 提取质量

**用户体验目标**：
- ✅ 用户无需任何配置变更即可享受改进
- ✅ recall 延迟无可感知增加（context boost 仅为 SQL CASE 表达式）

## 12. 实施阶段

### Phase 1: 参数 A/B 评估（P0）

**目标**：用数据驱动选择最优 context 参数。

**交付物**：
- ✅ 评估数据集 JSON（10-20 个标注查询）
- ✅ 评估脚本 `scripts/eval_context_params.py`
- ✅ 实验报告（MRR 对比 + 推荐参数）

**验证标准**：3 组参数均有 MRR 数据，选出的参数组 MRR 优于 baseline 或有明确的"无显著差异"结论。

### Phase 2: Extraction 标注 + 存储（P1）

**目标**：新 ingest 的 fact/episodic 自动携带 context 标签。

**交付物**：
- ✅ extraction prompt 增加 context 字段（中/英双语）
- ✅ `_store_facts()` / `_store_episodes()` 写入 `trait_context`
- ✅ 无效值降级逻辑
- ✅ 单元测试

**验证标准**：ingest 一条"我在 Google 工作"消息后，提取的 fact 的 `trait_context` 为 `"work"`。

### Phase 3: 历史回填 + Recall 增强（P1）

**目标**：历史记忆标注 + recall boost 扩展。

**交付物**：
- ✅ 回填脚本 `scripts/backfill_context.py`
- ✅ SearchService context bonus 扩展到全类型
- ✅ 更新 ContextService 常量为最优参数
- ✅ 集成测试

**验证标准**：回填后 recall 对 context-specific 查询的返回排序有可观察的改善。

## 13. 未来考虑

- **可配置标签体系**：允许用户定义自己的 context 类别（如 health/finance）
- **自适应参数**：基于用户反馈（点击/采纳数据）动态调整 MARGIN_THRESHOLD 和 MAX_CONTEXT_BOOST
- **多 context 标注**：一条记忆可能属于多个 context（如"在公司团建"同时是 work + social）
- **context 权重衰减**：随时间推移，context 标签可能过时（如换工作后，旧 work 记忆的 context 匹配价值降低）

## 14. 风险与缓解措施

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 三组参数 MRR 无显著差异 | 无法确定最优参数 | 保留当前参数，将注意力集中在 P1 记忆级标注（这才是核心改进） |
| LLM 对 context 字段标注不准 | 大量记忆被标为 general | 通过 prompt 中的示例和白名单约束提高准确率；回填脚本可作为 fallback |
| 评估数据集太小（10-20 条） | MRR 统计显著性不足 | 覆盖 4 个 context 类别确保多样性；后续可增加数据量 |
| trait_context 列语义扩展引起混淆 | 维护者不清楚该列含义 | 在 Memory model 注释中说明：trait_context 用于所有记忆类型的 context 标注，不仅限于 trait |
| 回填脚本在大数据量下性能差 | 超时或 OOM | 分批处理（每批 100 条），使用 SQL 批量更新而非逐条 |

## 15. 附录

### 相关文件

| 文件 | 说明 |
|------|------|
| `neuromem/services/context.py` | ContextService：原型向量 + 推断逻辑 + 参数常量 |
| `neuromem/services/search.py` | SearchService：context_bonus_sql 生成逻辑 |
| `neuromem/services/memory_extraction.py` | MemoryExtractionService：extraction prompt + 存储逻辑 |
| `neuromem/models/memory.py` | Memory model：`trait_context` 列定义 |
| `neuromem/_core.py` | NeuroMemory facade：recall 中调用 ContextService |
| `neuromem/db.py` | 数据库初始化：trait_context 列和索引的 DDL |

### V1 PRD 参考

- `rpiv/requirements/prd-context-aware-recall.md`

### Context 标签体系

| 标签 | 涵盖内容 |
|------|----------|
| `work` | 编程、项目、会议、职业、技术、部署 |
| `personal` | 生活、家庭、健康、兴趣爱好、旅行 |
| `social` | 社交关系、聚会、人际交往、约会 |
| `learning` | 学习、教育、论文、课程、理论研究 |
| `general` | 无法明确归类 / 降级默认值 |
