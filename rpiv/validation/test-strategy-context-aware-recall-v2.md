---
description: "测试策略+规格: context-aware-recall-v2 (参数调优 + 提取标注 + 历史回填 + 召回 boost 增强)"
status: in_progress
created_at: 2026-03-05T17:00:00
updated_at: 2026-03-05T17:15:00
archived_at: null
---

# 测试策略: context-aware-recall-v2

## 1. 测试目标

本次迭代在 v1 context-aware recall 基础上做四项增强。测试策略覆盖：

1. **P0 参数调优验证**: 三组参数 (baseline/medium/aggressive) 的评估脚本正确性、MRR 计算准确性
2. **P1 提取时标注**: extraction prompt 修改后 LLM 返回 context 字段、降级为 general 的异常处理
3. **P1 历史回填**: embedding 相似度回填脚本的幂等性、阈值降级、正确写入 trait_context 列
4. **P1 召回 boost 增强**: 记忆级 context 标签与 query context 匹配时的额外 boost、不匹配不惩罚
5. **回归测试**: v1 所有现有测试无回归
6. **性能**: 回填脚本合理耗时、boost 计算不显著增加 recall 延迟

## 2. 测试范围

### 2.1 新增/修改代码（需全面测试）

| 场景 | 预期改动文件 | 测试重点 |
|------|-------------|----------|
| P0 参数调优 | 评估脚本 (scripts/ 或 benchmarks/) | MRR 计算公式正确、参数组切换逻辑、结果输出格式 |
| P1 提取标注 | `services/memory_extraction.py`, extraction prompt | context 字段解析、白名单校验、降级为 general |
| P1 历史回填 | 迁移脚本 (scripts/) | 幂等可重跑、阈值降级、正确更新 trait_context 列 |
| P1 召回 boost | `services/search.py`, `services/context.py` | 记忆级 context 匹配逻辑、boost 值计算、NULL/general 处理 |
| 核心流程集成 | `_core.py` | recall/ingest 端到端行为 |

### 2.2 不受影响（需验证无回归）

| 功能 | 验证方式 |
|------|----------|
| v1 context inference (prototype matching) | 现有 `test_context.py`, `test_context_inference.py` |
| v1 context_match bonus | 现有 `test_recall_context_match.py`, `test_recall_context_e2e.py` |
| 向量检索 + BM25 RRF 融合 | 现有 `test_search.py` |
| trait_boost / emotion_match / graph_boost | 现有 `test_recall_trait_boost.py`, `test_recall_emotion.py`, `test_graph_boost.py` |
| recency/importance bonus | 现有 `test_recall.py` |

## 3. 测试分层

### 3.1 单元测试（无数据库依赖）

#### 3.1.1 MRR 计算 (场景 1)

| ID | 测试用例 | 描述 |
|----|----------|------|
| MRR-1 | `test_mrr_perfect_rank` | ground truth 排第 1 -> MRR = 1.0 |
| MRR-2 | `test_mrr_second_rank` | ground truth 排第 2 -> MRR = 0.5 |
| MRR-3 | `test_mrr_not_in_topk` | ground truth 不在 top-k -> MRR = 0 |
| MRR-4 | `test_mrr_average_multiple_queries` | 多个查询的平均 MRR 计算正确 |
| MRR-5 | `test_mrr_empty_results` | 空结果集不抛异常, MRR = 0 |

#### 3.1.2 提取标注 (场景 2)

| ID | 测试用例 | 描述 |
|----|----------|------|
| EX-1 | `test_extract_fact_with_context` | LLM 返回 fact + context: "work" -> 正确解析 |
| EX-2 | `test_extract_episodic_with_context` | LLM 返回 episodic + context: "learning" -> 正确解析 |
| EX-3 | `test_extract_invalid_context_fallback` | LLM 返回 context: "health" (不在白名单) -> 降级为 "general" |
| EX-4 | `test_extract_missing_context_fallback` | LLM 返回无 context 字段 -> 降级为 "general" |
| EX-5 | `test_extract_context_whitelist` | 验证白名单 = {work, personal, social, learning, general} |

#### 3.1.3 回填逻辑 (场景 3)

| ID | 测试用例 | 描述 |
|----|----------|------|
| BF-1 | `test_backfill_highest_similarity_wins` | 与 work prototype 最相似 -> 标为 "work" |
| BF-2 | `test_backfill_below_threshold_general` | 最高相似度低于阈值 -> 标为 "general" |
| BF-3 | `test_backfill_idempotent` | 重复运行结果不变 |
| BF-4 | `test_backfill_skips_already_labeled` | 已有非 general 标签的记忆不被覆盖（或按设计覆盖） |

#### 3.1.4 记忆级 context boost (场景 4)

| ID | 测试用例 | 描述 |
|----|----------|------|
| MB-1 | `test_memory_context_match_boost` | query context == memory context -> 额外 boost |
| MB-2 | `test_memory_context_mismatch_no_penalty` | query context != memory context -> boost = 0, 不惩罚 |
| MB-3 | `test_memory_context_general_no_boost` | memory context = "general" -> 不参与 boost |
| MB-4 | `test_memory_context_null_no_boost` | memory context = NULL -> 不参与 boost |
| MB-5 | `test_memory_context_with_confidence` | boost 值随 query confidence 线性缩放 |
| MB-6 | `test_memory_context_confidence_zero` | confidence = 0 -> 所有 boost = 0（等效关闭） |

### 3.2 集成测试（需数据库, port 5436）

#### 3.2.1 提取 + 存储集成

| ID | 测试用例 | 描述 |
|----|----------|------|
| EI-1 | `test_ingest_stores_context_label` | ingest 后 fact 记忆的 trait_context 列有正确值 |
| EI-2 | `test_ingest_episodic_stores_context` | ingest 后 episodic 记忆同样存储 context |
| EI-3 | `test_ingest_context_general_fallback` | LLM 标注失败时 context 默认为 "general" |

#### 3.2.2 回填脚本集成

| ID | 测试用例 | 描述 |
|----|----------|------|
| BI-1 | `test_backfill_updates_trait_context_column` | 回填后数据库中 trait_context 列被正确更新 |
| BI-2 | `test_backfill_only_null_records` | 仅回填 trait_context 为 NULL 的 fact/episodic |
| BI-3 | `test_backfill_batch_processing` | 大批量数据不超时、不 OOM |

#### 3.2.3 召回 boost 集成

| ID | 测试用例 | 描述 |
|----|----------|------|
| RI-1 | `test_recall_memory_context_match_ranks_higher` | 记忆 context 匹配 query context -> 排名上升 |
| RI-2 | `test_recall_memory_context_mismatch_no_drop` | 记忆 context 不匹配 -> 排名不下降（相比 v1） |
| RI-3 | `test_recall_mixed_context_memories` | 混合 context 记忆正确排序 |
| RI-4 | `test_recall_fact_with_context_boost` | fact 记忆的 context 标签也参与 boost（v2 新增） |

### 3.3 端到端测试（需数据库）

| ID | 测试用例 | 描述 |
|----|----------|------|
| E2E-1 | `test_ingest_then_recall_context_preserved` | 完整 ingest -> recall, context 标签贯穿全流程 |
| E2E-2 | `test_recall_with_backfilled_memories` | 回填后的旧记忆在 recall 中正确参与 context boost |
| E2E-3 | `test_backward_compat_no_context_memories` | 无 context 的旧记忆在 v2 下正常 recall, 不崩溃 |
| E2E-4 | `test_parameter_change_affects_ranking` | 不同 margin/boost 参数组产生不同排名结果 |

### 3.4 性能测试

| ID | 测试用例 | 描述 |
|----|----------|------|
| PF-1 | `test_infer_context_latency_under_1ms` | 1000 次 infer_context < 1ms 均值 |
| PF-2 | `test_backfill_100_records_under_10s` | 100 条记忆回填 < 10 秒 |
| PF-3 | `test_recall_latency_no_regression` | v2 recall 延迟相比 v1 增幅 < 5% |

## 4. 关键测试场景详述

### 4.1 参数调优评估 (P0)

评估脚本需测试三组参数：

| 参数组 | MARGIN_THRESHOLD | MAX_CONTEXT_BOOST |
|--------|-----------------|-------------------|
| baseline | 0.05 | 0.10 |
| medium | 0.03 | 0.15 |
| aggressive | 0.02 | 0.20 |

**验证点**:
- 每组参数跑同一查询集, 产出 MRR 分数
- MRR 计算公式: `MRR = (1/N) * sum(1/rank_i)`, rank_i 为 ground truth 在结果中的位置
- 三组 MRR 无显著差异时保留 baseline, 记录结论
- 脚本输出格式规范（JSON 或 CSV）

### 4.2 提取时标注 (P1)

**标签白名单**: `work, personal, social, learning, general`

**extraction prompt 变更验证**:
```
输入: "我在公司用 Python 写了一个自动化脚本"
预期 LLM 输出中 fact 包含: {"content": "在公司用 Python 写自动化脚本", "context": "work", ...}
```

**降级场景**:
- LLM 返回 `"context": "health"` -> 降级为 `"general"`
- LLM 返回 `"context": ""` -> 降级为 `"general"`
- LLM 返回无 context 字段 -> 降级为 `"general"`
- LLM 返回 `"context": null` -> 降级为 `"general"`

### 4.3 历史回填 (P1)

**回填流程**:
1. 读取所有 trait_context 为 NULL 的 fact/episodic 记忆
2. 用记忆自身的 embedding 与 4 个 context prototype 计算余弦相似度
3. 取最高分, 高于阈值则标注对应 context, 否则标 "general"
4. 幂等: 重跑结果一致

**边界条件**:
- 记忆无 embedding -> 跳过
- 所有 prototype 相似度都很低 -> 标 "general"
- trait 类型已有 context (v1 已回填) -> 不重复处理

### 4.4 召回 boost 增强 (P1)

**v2 vs v1 对比**:
- v1: 仅用 query 的 inferred context 对 trait 做 boost
- v2: 额外比对每条记忆自身的 context 标签, 匹配时加分, 不匹配不惩罚

**计算逻辑** (预期):
```
if query_context == memory_context and memory_context not in (NULL, "general"):
    memory_context_boost = BOOST_VALUE * query_confidence
else:
    memory_context_boost = 0
```

**验证点**:
- fact + episodic 的 context 标签也参与 boost（v1 仅 trait）
- general/NULL 记忆不参与 boost（既不加分也不减分）
- confidence = 0 时全部 boost = 0

## 5. 测试工具和 fixture

### 5.1 复用现有 fixture

- `db_session`: 每测试函数独立 session (port 5436)
- `mock_embedding`: MockEmbeddingProvider (hash-based 确定性向量, dims=1024)
- `mock_llm`: MockLLMProvider
- `nm`: 完整 NeuroMemory 实例

### 5.2 新增 fixture/helper

| 名称 | 用途 |
|------|------|
| `mock_llm_with_context` | 返回带 context 字段的 extraction JSON |
| `_insert_memory_with_context()` | 插入带 trait_context 的 fact/episodic/trait 记忆 |
| `_run_backfill()` | 封装回填脚本调用 |
| `_compute_mrr()` | MRR 计算 helper |

### 5.3 测试数据构造策略

与 v1 一致:
1. **算法层**（单元测试）: 构造人工向量精确控制相似度
2. **集成层**（数据库测试）: 直接写入 trait_context 列, 验证 SQL boost 逻辑
3. **慢测试**（`@pytest.mark.slow`）: 使用真实 embedding provider 验证回填准确性

## 6. 测试文件组织

```
tests/
  test_context_inference.py           # (现有) 推断算法单元测试
  test_context.py                     # (现有) ContextService 集成测试
  test_recall_context_match.py        # (现有) scored_search context_match 集成测试
  test_recall_context_e2e.py          # (现有) recall() 端到端测试
  test_context_extraction.py          # (新增) 提取时标注单元/集成测试 (EX-*, EI-*)
  test_context_backfill.py            # (新增) 历史回填单元/集成测试 (BF-*, BI-*)
  test_recall_memory_context_boost.py # (新增) 记忆级 context boost (MB-*, RI-*)
  test_parameter_tuning.py            # (新增) MRR 计算和参数评估 (MRR-*)
```

## 7. 验收标准

| 编号 | 标准 | 验证方式 |
|------|------|----------|
| AC-1 | 所有新增测试通过 | `pytest tests/test_context_*.py tests/test_recall_*.py tests/test_parameter_tuning.py -v` |
| AC-2 | 所有现有测试无回归 | `pytest tests/ -v -m "not slow"` 全绿 |
| AC-3 | MRR 计算公式正确 | 手工验证 + 单元测试 |
| AC-4 | 提取标注白名单校验 | 无效 context 降级为 general |
| AC-5 | 回填脚本幂等 | 重复运行结果一致 |
| AC-6 | 记忆级 context boost 正确 | 匹配加分, 不匹配不惩罚, NULL/general 不参与 |
| AC-7 | fact/episodic 也参与 context boost | 集成测试验证 |
| AC-8 | confidence=0 时所有 boost=0 | 边界测试 |
| AC-9 | 回填仅影响 NULL 记忆 | 已有 context 的记忆不被覆盖 |
| AC-10 | 性能无显著退化 | recall 延迟增幅 < 5% |

## 8. 风险和缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| 回填脚本批量操作可能锁表 | 线上数据库阻塞 | 分批处理, 每批 100 条 + commit |
| fact/episodic context boost 与 trait boost 叠加过度 | 排序异常 | 验证 total bonus < 0.80 |
| 参数调优数据集太小 (10-20 条) | MRR 统计不显著 | 明确这是定性评估, 非统计检验 |
| LLM 提取 context 标注一致性差 | 同类 query 标注不一致 | 降级兜底 + prompt 示例充分 |
| trait_context 列被 fact/episodic 复用 | 语义混乱 | 确认列定义足够通用, 或确认已有此列 |
| MockEmbeddingProvider 无法测试回填真实效果 | 回填阈值无法校准 | @pytest.mark.slow 慢测试用真实 embedding |

---

# 测试规格: context-aware-recall-v2

> 基于 PRD `prd-context-aware-recall-v2.md` 编写。每个用例包含输入、步骤、预期输出和验收判定。

## TS-1. 参数 A/B 评估 (对应 PRD 7.1)

### TS-1.1 MRR 计算正确性

#### MRR-1: ground truth 排第 1 位
- **输入**: results = ["id_a", "id_b", "id_c"], ground_truth = "id_a"
- **步骤**: 调用 `compute_mrr(results, ground_truth)`
- **预期**: MRR = 1.0
- **验收**: assert mrr == 1.0

#### MRR-2: ground truth 排第 2 位
- **输入**: results = ["id_a", "id_b", "id_c"], ground_truth = "id_b"
- **步骤**: 调用 `compute_mrr(results, ground_truth)`
- **预期**: MRR = 0.5
- **验收**: assert mrr == 0.5

#### MRR-3: ground truth 排第 3 位
- **输入**: results = ["id_a", "id_b", "id_c"], ground_truth = "id_c"
- **步骤**: 调用 `compute_mrr(results, ground_truth)`
- **预期**: MRR = 1/3
- **验收**: assert abs(mrr - 1/3) < 1e-6

#### MRR-4: ground truth 不在 top-k
- **输入**: results = ["id_a", "id_b", "id_c"], ground_truth = "id_x"
- **步骤**: 调用 `compute_mrr(results, ground_truth)`
- **预期**: MRR = 0.0
- **验收**: assert mrr == 0.0

#### MRR-5: 多查询平均 MRR
- **输入**: queries = [{results: ["a","b"], gt: "a"}, {results: ["a","b"], gt: "b"}]
- **步骤**: 调用 `compute_mean_mrr(queries)`
- **预期**: mean_MRR = (1.0 + 0.5) / 2 = 0.75
- **验收**: assert abs(mean_mrr - 0.75) < 1e-6

#### MRR-6: 空结果集
- **输入**: results = [], ground_truth = "id_a"
- **步骤**: 调用 `compute_mrr(results, ground_truth)`
- **预期**: MRR = 0.0, 不抛异常
- **验收**: assert mrr == 0.0

### TS-1.2 参数组切换

#### PARAM-1: 三组参数均可独立执行
- **输入**: 3 组参数配置 (baseline/medium/aggressive)
- **步骤**: 依次设置 ContextService 常量并执行 recall
- **预期**: 每组返回有效的 MRR 分数
- **验收**: 0.0 <= mrr <= 1.0 for each group

#### PARAM-2: 参数组之间互不干扰
- **输入**: 同一查询, 先 baseline 再 aggressive
- **步骤**: 执行 baseline recall -> 重置 -> 执行 aggressive recall
- **预期**: 两次结果独立, 不受前次参数残留影响
- **验收**: baseline_results != aggressive_results (or equal if legitimately same)

### TS-1.3 评估脚本输出

#### EVAL-1: 输出包含所有参数组的 MRR
- **输入**: 运行 `scripts/eval_context_params.py`
- **步骤**: 检查输出 JSON/CSV
- **预期**: 包含 baseline, medium, aggressive 三行, 每行有 MRR@3 和 MRR@5
- **验收**: 解析输出, 验证结构完整

## TS-2. 提取时 Context 标注 (对应 PRD 7.2)

### TS-2.1 正常标注

#### EX-1: fact 带 work context
- **输入**: Mock LLM 返回:
  ```json
  {"facts": [{"content": "在 Google 工作", "context": "work", "confidence": 0.9}], "episodes": []}
  ```
- **步骤**: 调用 `MemoryExtractionService.extract_from_messages()`
- **预期**: 提取的 fact 记忆 trait_context = "work"
- **验收**: assert memory.trait_context == "work"

#### EX-2: episodic 带 learning context
- **输入**: Mock LLM 返回:
  ```json
  {"facts": [], "episodes": [{"content": "学了 Transformer 论文", "context": "learning"}]}
  ```
- **步骤**: 调用 `extract_from_messages()`
- **预期**: 提取的 episodic 记忆 trait_context = "learning"
- **验收**: assert memory.trait_context == "learning"

#### EX-3: personal context
- **输入**: Mock LLM 返回 fact with context: "personal"
- **步骤**: 调用 `extract_from_messages()`
- **预期**: trait_context = "personal"
- **验收**: assert memory.trait_context == "personal"

#### EX-4: social context
- **输入**: Mock LLM 返回 episodic with context: "social"
- **步骤**: 调用 `extract_from_messages()`
- **预期**: trait_context = "social"
- **验收**: assert memory.trait_context == "social"

#### EX-5: general context (显式)
- **输入**: Mock LLM 返回 fact with context: "general"
- **步骤**: 调用 `extract_from_messages()`
- **预期**: trait_context = "general"
- **验收**: assert memory.trait_context == "general"

### TS-2.2 降级场景

#### EX-6: 无效 context 值降级
- **输入**: Mock LLM 返回 context: "health" (不在白名单)
- **步骤**: 调用 `extract_from_messages()`
- **预期**: trait_context = "general"
- **验收**: assert memory.trait_context == "general"

#### EX-7: 缺失 context 字段降级
- **输入**: Mock LLM 返回 fact 无 context 字段: `{"content": "...", "confidence": 0.9}`
- **步骤**: 调用 `extract_from_messages()`
- **预期**: trait_context = "general"
- **验收**: assert memory.trait_context == "general"

#### EX-8: context 为空字符串降级
- **输入**: Mock LLM 返回 context: ""
- **步骤**: 调用 `extract_from_messages()`
- **预期**: trait_context = "general"
- **验收**: assert memory.trait_context == "general"

#### EX-9: context 为 null 降级
- **输入**: Mock LLM 返回 context: null
- **步骤**: 调用 `extract_from_messages()`
- **预期**: trait_context = "general"
- **验收**: assert memory.trait_context == "general"

### TS-2.3 白名单验证

#### EX-10: 白名单完整性
- **步骤**: 检查代码中的 VALID_CONTEXTS 常量
- **预期**: == {"work", "personal", "social", "learning", "general"}
- **验收**: 集合相等

## TS-3. 历史 Context 回填 (对应 PRD 7.3)

### TS-3.1 回填逻辑

#### BF-1: 最高相似度分类
- **输入**: memory embedding 与 work prototype 余弦相似度最高 (0.85), personal (0.30), social (0.20), learning (0.15)
- **步骤**: 执行回填逻辑
- **预期**: trait_context = "work"
- **验收**: assert result == "work"

#### BF-2: 低于阈值降级
- **输入**: 所有 prototype 相似度 < margin_threshold (如均为 0.01)
- **步骤**: 执行回填逻辑
- **预期**: trait_context = "general"
- **验收**: assert result == "general"

#### BF-3: margin 不足降级
- **输入**: work=0.50, personal=0.49 (margin=0.01 < threshold)
- **步骤**: 执行回填逻辑
- **预期**: trait_context = "general" (margin 不足)
- **验收**: assert result == "general"

#### BF-4: 幂等性
- **步骤**: 执行回填 -> 读取结果 -> 再次执行回填 -> 读取结果
- **预期**: 两次结果完全一致
- **验收**: assert first_run == second_run

### TS-3.2 回填数据库集成

#### BI-1: 更新 trait_context 列
- **前置**: 插入 3 条 fact 记忆, trait_context = NULL
- **步骤**: 执行回填脚本
- **预期**: 所有 3 条记忆的 trait_context 非 NULL
- **验收**: SELECT count(*) WHERE trait_context IS NULL AND memory_type='fact' == 0

#### BI-2: 仅处理 NULL 记忆
- **前置**: 插入 2 条 fact (trait_context=NULL) + 1 条 fact (trait_context='work')
- **步骤**: 执行回填脚本
- **预期**: 已标注 "work" 的记忆不变, NULL 的被更新
- **验收**: 'work' 记忆的 trait_context 仍为 'work'

#### BI-3: trait 类型不受影响
- **前置**: 插入 trait (trait_context='personal') + fact (trait_context=NULL)
- **步骤**: 执行回填脚本
- **预期**: trait 的 context 不变, fact 被回填
- **验收**: trait.trait_context == 'personal' (不变)

#### BI-4: 无 embedding 记忆跳过
- **前置**: 插入 fact 记忆但 embedding = NULL
- **步骤**: 执行回填脚本
- **预期**: 该记忆被跳过, 不报错
- **验收**: 不抛异常, trait_context 仍为 NULL

#### BI-5: --force 模式覆盖
- **前置**: 插入 fact (trait_context='work')
- **步骤**: 执行回填脚本 with --force
- **预期**: 重新计算并可能更新 trait_context
- **验收**: 回填逻辑被执行 (不论原值)

#### BI-6: 批量处理 (100 条)
- **前置**: 插入 100 条 fact 记忆
- **步骤**: 执行回填脚本
- **预期**: 全部处理完成, 耗时 < 10 秒
- **验收**: 100 条均有 trait_context 值

## TS-4. 召回 Context Boost 增强 (对应 PRD 7.4)

### TS-4.1 记忆级 context boost (SQL 层)

#### MB-1: 精确匹配 boost
- **前置**: 插入 fact (trait_context='work'), query context = 'work', confidence = 0.8
- **步骤**: 执行 scored_search
- **预期**: context_bonus = MAX_CONTEXT_BOOST * 0.8
- **验收**: 验证返回结果中 context bonus 值

#### MB-2: 不匹配不惩罚
- **前置**: 插入 fact (trait_context='personal'), query context = 'work', confidence = 0.8
- **步骤**: 执行 scored_search
- **预期**: context_bonus = 0 (不是负数)
- **验收**: 分数 >= 无 context 时的基础分数

#### MB-3: general 记忆小幅 boost
- **前置**: 插入 fact (trait_context='general'), query context = 'work', confidence = 0.8
- **步骤**: 执行 scored_search
- **预期**: context_bonus = GENERAL_CONTEXT_BOOST * 0.8 (小于精确匹配)
- **验收**: 0 < general_boost < exact_match_boost

#### MB-4: NULL 记忆无 boost
- **前置**: 插入 fact (trait_context=NULL), query context = 'work', confidence = 0.8
- **步骤**: 执行 scored_search
- **预期**: context_bonus = 0
- **验收**: 分数与 v1 无 context boost 时一致

#### MB-5: confidence 线性缩放
- **前置**: 插入 fact (trait_context='work'), query context = 'work'
- **步骤**: 分别用 confidence=0.5 和 confidence=1.0 执行 scored_search
- **预期**: boost(conf=1.0) = 2 * boost(conf=0.5)
- **验收**: 比较两次 context bonus 值的比例

#### MB-6: confidence = 0 全部关闭
- **前置**: 插入 fact (trait_context='work'), query context = 'work', confidence = 0.0
- **步骤**: 执行 scored_search
- **预期**: context_bonus = 0
- **验收**: 与无 context 功能时分数一致

### TS-4.2 全类型 boost 验证

#### MB-7: fact 参与 context boost
- **前置**: 插入 fact (trait_context='work'), query context = 'work'
- **步骤**: 执行 scored_search
- **预期**: fact 获得 context bonus (v1 中 fact 无 bonus)
- **验收**: fact_score(v2) > fact_score(v1_equivalent)

#### MB-8: episodic 参与 context boost
- **前置**: 插入 episodic (trait_context='learning'), query context = 'learning'
- **步骤**: 执行 scored_search
- **预期**: episodic 获得 context bonus
- **验收**: episodic 分数包含 context bonus

#### MB-9: trait 行为不变
- **前置**: 插入 trait (trait_context='work'), query context = 'work'
- **步骤**: 执行 scored_search
- **预期**: trait 仍然获得 context bonus (与 v1 一致)
- **验收**: trait 分数含 context bonus

### TS-4.3 排序效果

#### RI-1: 匹配记忆排名上升
- **前置**: 插入 fact_A (context='work', 语义相似度中等) + fact_B (context='personal', 语义相似度略高)
- **步骤**: query context='work' 执行 recall
- **预期**: fact_A 排名高于 fact_B (context boost 补偿语义差距)
- **验收**: results.index(fact_A) < results.index(fact_B)

#### RI-2: 不匹配记忆排名不下降
- **前置**: 插入 fact_A (context='personal'), 基线 recall 记录排名
- **步骤**: query context='work' 执行 recall
- **预期**: fact_A 排名与无 context 时一致 (不惩罚)
- **验收**: rank_v2 <= rank_v1 + 1 (允许微小波动)

#### RI-3: 混合类型正确排序
- **前置**: 插入 trait (context='work') + fact (context='work') + episodic (context='personal')
- **步骤**: query context='work' 执行 recall
- **预期**: work 记忆排名靠前, personal 记忆排名靠后
- **验收**: work 记忆的平均排名 < personal 记忆的平均排名

## TS-5. 端到端场景 (对应 PRD US-1 ~ US-5)

### TS-5.1 完整流程

#### E2E-1: ingest -> recall 全流程 context 贯通
- **步骤**:
  1. `nm.ingest(user_id, role="user", content="我在 Google 担任高级工程师")`
  2. 等待提取完成
  3. 验证数据库中 fact 的 trait_context = "work"
  4. `nm.recall(user_id, query="帮我写代码")`
  5. 验证 inferred_context = "work", 工作记忆排名靠前
- **预期**: context 标签从 ingest 贯穿到 recall
- **验收**: trait_context 列有值 + recall 结果排序合理

#### E2E-2: 回填后旧记忆参与 boost
- **步骤**:
  1. 插入旧 fact (trait_context=NULL)
  2. 执行回填脚本
  3. 验证 trait_context 非 NULL
  4. 执行 recall, 验证回填后的记忆获得 context boost
- **预期**: 旧记忆经回填后与新记忆同等参与 context boost
- **验收**: 回填后的记忆在相关 context 查询中排名上升

#### E2E-3: 无 context 旧记忆向后兼容
- **步骤**:
  1. 插入旧 fact (trait_context=NULL, 不回填)
  2. 执行 recall
  3. 验证不崩溃, 旧记忆仍在结果中
- **预期**: NULL context 记忆正常参与召回, 只是不获得 context bonus
- **验收**: isinstance(result, dict) and len(result["merged"]) >= 1

#### E2E-4: 用户故事 US-1 验证
- **步骤**:
  1. ingest "我在 Google 担任高级工程师" + "周末去了西湖"
  2. recall query="帮我写代码" (预期 context=work)
  3. 验证工作记忆排在生活记忆前面
- **预期**: 工作相关 fact 排名 #1
- **验收**: result["merged"][0] 包含 "Google" 或 "工程师"

#### E2E-5: 用户故事 US-2 验证 (零配置透明)
- **步骤**: 标准 ingest + recall, 不传任何 context 参数
- **预期**: context 标注和 boost 自动生效
- **验收**: recall 返回值包含 inferred_context 字段

#### E2E-6: 用户故事 US-5 验证 (零额外 LLM 消耗)
- **步骤**: 监控 LLM 调用次数, ingest 一条消息
- **预期**: LLM 调用次数与 v1 相同 (context 标注复用 extraction 调用)
- **验收**: llm_call_count_v2 == llm_call_count_v1

## TS-6. 性能基准

#### PF-1: infer_context 延迟
- **步骤**: 1000 次 `infer_context()` 调用计时
- **预期**: 平均延迟 < 1ms
- **验收**: avg_ms < 1.0

#### PF-2: 回填 100 条记忆
- **步骤**: 插入 100 条 fact, 运行回填
- **预期**: 总耗时 < 10 秒
- **验收**: elapsed < 10.0

#### PF-3: recall 延迟无退化
- **步骤**: v1 和 v2 各执行 100 次 recall, 对比平均延迟
- **预期**: v2 延迟增幅 < 5%
- **验收**: (v2_avg - v1_avg) / v1_avg < 0.05

## TS-7. 回归测试清单

执行完整测试套件前需确认以下测试文件全部通过:

| 测试文件 | 覆盖功能 | 优先级 |
|----------|----------|--------|
| `test_recall.py` | 三因子评分 + 图谱融合 | P0 |
| `test_recall_trait_boost.py` | trait boost 权重 | P0 |
| `test_recall_emotion.py` | emotion_match 加成 | P0 |
| `test_search.py` | 向量检索 + BM25 RRF | P0 |
| `test_context.py` | ContextService v1 | P0 |
| `test_context_inference.py` | 推断算法 v1 | P0 |
| `test_recall_context_match.py` | context_match bonus v1 | P0 |
| `test_recall_context_e2e.py` | recall context E2E v1 | P0 |
| `test_graph_boost.py` | 图谱 boost | P1 |
| `test_memory_extraction.py` | 记忆提取 | P0 |
| `test_memory_crud.py` | 记忆 CRUD | P1 |
| `test_conversations.py` | 会话管理 | P1 |

**回归验证命令**: `cd D:/CODE/NeuroMem && uv run pytest tests/ -v -m "not slow"`
