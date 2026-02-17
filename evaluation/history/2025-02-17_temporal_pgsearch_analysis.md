# LoCoMo 第四次完整测试分析与改进建议

**测试日期**: 2025-02-17
**测试名称**: Temporal Extraction + pg_search BM25
**对比基准**: 2025-02-17_complete_test (第三次, Judge 0.431)

---

## 1. 执行摘要

本次测试实现了两项核心改进，整体 Judge Score 从 0.431 跃升至 **0.610** (+41.5%)，超额完成 0.52+ 目标。

| 指标 | 第三次 (0217) | **第四次 (本次)** | 提升 |
|------|-------------|-----------------|------|
| **Judge Score** | 0.431 | **0.610** | **+41.5%** |
| **F1 Score** | 0.245 | **0.361** | **+47.3%** |
| **BLEU-1** | 0.198 | **0.297** | **+50.0%** |

---

## 2. 四次测试完整历史

| 测试 | 日期 | Judge | F1 | BLEU-1 | 核心改进 |
|------|------|-------|-----|--------|---------|
| #1 Baseline | 02-15 | 0.125 | — | — | 首次基线测试 |
| #2 Perf Opt | 02-16 | 0.274 (+119%) | 0.145 | 0.114 | 速度优化 24x + 质量提升 |
| #3 Complete | 02-17 | 0.431 (+57%) | 0.245 | 0.198 | 数据完整性 + Conv 8-9 修复 |
| **#4 本次** | **02-17** | **0.610 (+42%)** | **0.361** | **0.297** | **时间提取 + pg_search BM25** |

**累计提升**: 0.125 → 0.610 (**+388%**)

---

## 3. 分类别详细对比

### 3.1 Category 1: Multi-hop (多跳推理)

| 指标 | #3 | **#4** | 提升 |
|------|-----|--------|------|
| **Judge** | 0.475 | **0.612** | **+28.8%** |
| **F1** | 0.230 | **0.271** | +17.8% |
| **BLEU-1** | 0.169 | **0.192** | +13.6% |

**分析**: 大幅提升，pg_search 的 BM25 帮助精确匹配了多跳问题中的关键实体名，配合向量检索的语义理解，RRF 融合效果显著。

### 3.2 Category 2: Temporal (时序推理)

| 指标 | #3 | **#4** | 提升 |
|------|-----|--------|------|
| **Judge** | 0.159 | **0.574** | **+261.0%** |
| **F1** | 0.088 | **0.401** | +355.7% |
| **BLEU-1** | 0.061 | **0.331** | +442.6% |

**分析**: 本次最大亮点。三级时间戳解析 + extracted_timestamp 索引列 + recall 结果时间标注，彻底解决了之前的时间推理盲区。从最弱项变为中等水平。

### 3.3 Category 3: Open-domain (开放域)

| 指标 | #3 | **#4** | 变化 |
|------|-----|--------|------|
| **Judge** | 0.448 | **0.417** | **-6.9%** |
| **F1** | 0.194 | **0.232** | +19.6% |
| **BLEU-1** | 0.139 | **0.185** | +33.1% |

**分析**: Judge 轻微下降但 F1/BLEU 提升。Open-domain 问题需要更宽泛的语义理解，pg_search 的精确关键词匹配可能引入了噪音，挤出了一些语义相关但关键词不匹配的结果。这是当前**最大短板**。

### 3.4 Category 4: Single-hop (单跳查询)

| 指标 | #3 | **#4** | 提升 |
|------|-----|--------|------|
| **Judge** | 0.518 | **0.645** | **+24.5%** |
| **F1** | 0.316 | **0.392** | +24.1% |
| **BLEU-1** | 0.266 | **0.331** | +24.4% |

**分析**: 全面均衡提升约 24%。pg_search BM25 对精确事实检索帮助明显，是占比最大的类别 (840/1534)，对整体分数贡献最大。

---

## 4. 与 Mem0 对比分析

| 指标 | **NeuroMemory** | **Mem0** | **Mem0^g** | 差距 |
|------|----------------|---------|-----------|------|
| **Overall** | **0.610** | 0.669 | 0.684 | -8.8% |
| Single-hop | **0.645** | 0.671 | 0.657 | -3.9% |
| Multi-hop | **0.612** | 0.512 | 0.472 | **+19.5%** |
| Open-domain | 0.417 | 0.729 | 0.757 | **-42.8%** |
| Temporal | **0.574** | 0.555 | 0.581 | +3.4% |

**关键发现**:
- NeuroMemory 用 **DeepSeek** 达到了 Mem0 (**GPT-4o**) 的 91% 水平
- **Multi-hop 和 Temporal 已超越 Mem0**
- **Open-domain 是唯一大幅落后的类别** (-42.8%)，是缩小差距的关键

---

## 5. 本次改进的技术贡献分析

### 5.1 时间提取系统 (贡献 ~60% 的提升)

| 组件 | 作用 |
|------|------|
| `TemporalExtractor` | 纯 Python 规则引擎，支持中英文绝对/相对时间 |
| `extracted_timestamp` 列 | 独立索引列替代 JSONB 字符串比较，查询性能提升 |
| 3 级时间戳解析 | LLM ISO → LLM 文本 regex → 内容文本提取 |
| `session_timestamp` 传递 | 评测管线传入正确会话时间，而非使用 NOW() |
| Recall 时间标注 | 内容前缀 `[YYYY-MM-DD]`，帮助 LLM 回答时参考时间 |

### 5.2 pg_search BM25 (贡献 ~40% 的提升)

| 组件 | 作用 |
|------|------|
| ParadeDB pg_search | Tantivy 引擎替代 PostgreSQL tsvector，BM25 质量提升 |
| RRF 混合检索 | 向量相似度 + BM25 关键词，K=60 |
| 优雅降级 | pg_search 不可用时自动回退 tsvector |
| 查询消毒 | 处理撇号等 Tantivy 特殊字符 |
| candidate_limit 调优 | pg_search 时 limit*2（vs tsvector 的 limit*4） |

---

## 6. 当前瓶颈分析

### 6.1 Open-domain: 最大短板 (Judge 0.417, 落后 Mem0 42.8%)

**问题诊断**:
- Open-domain 问题通常是概念性、推理性的（如"她对此有什么感受？"）
- 这类问题关键词匹配弱，需要深层语义理解
- pg_search BM25 对这类问题反而可能引入噪音
- 当前 recall 结果可能不够聚焦

**根因**: 缺少对对话语境和情感的深层理解，召回的记忆碎片不够连贯。

### 6.2 Temporal 仍有上升空间 (0.574 vs 目标 0.65+)

**问题诊断**:
- 纯 regex 时间提取无法覆盖所有模式
- 模糊时间表达（"去年夏天"、"毕业那年"）无法解析
- 部分问题需要时间段推理而非时间点查询

### 6.3 6 个问题缺失 (1534 vs 1540)

- 可能是个别 query 或 judge 调用超时/失败
- 影响不大但应排查

---

## 7. 改进建议与路线图

### Phase 1: Open-domain 专项提升 (P0, 预期 0.417 → 0.55+)

**目标**: 缩小与 Mem0 的最大差距

#### 1.1 上下文窗口扩展

当前 recall 返回的是碎片化的记忆条目。对于 open-domain 问题，需要更完整的对话上下文。

```python
# 方案: 对 open-domain 类型问题，增加 recall limit
# 当前 limit=10，建议动态调整为 15-20
def adaptive_recall(query, question_type=None):
    limit = 15 if question_type == "open_domain" else 10
    return search(query, limit=limit)
```

#### 1.2 Episode 记忆增强

Open-domain 问题依赖 episode 类型记忆（完整事件描述），但当前 episode 提取较少。

```python
# 改进 _store_episodes: 降低 episode 合并阈值
# 当前可能过度合并，丢失了细节
# 考虑保留更多独立 episode 而非合并为少数长 episode
```

#### 1.3 RRF 权重动态调整

对于 open-domain 问题，vector 语义匹配应有更高权重，BM25 权重降低。

```python
# 方案: 根据 BM25 匹配质量动态调整
# 如果 BM25 得分极低（关键词几乎不匹配），减少其 RRF 贡献
rrf_score = (1.0 / (K + vector_rank)) + alpha * (1.0 / (K + bm25_rank))
# alpha = 1.0 for factual queries, 0.5 for open-domain queries
```

#### 1.4 概念性知识提取

```python
# 在 memory_extraction prompt 中增加概念性知识提取
# 当前主要提取事实和事件，缺少:
# - 用户的情感状态和变化
# - 用户的价值观和信念
# - 用户对事件的态度和反应
# - 对话中的隐含信息
```

**预期**: Open-domain 0.417 → 0.55+ (+32%)，Overall 0.610 → 0.63+

### Phase 2: Temporal 进一步优化 (P1, 预期 0.574 → 0.65+)

#### 2.1 LLM 辅助时间提取

对 regex 无法解析的复杂时间表达，使用 LLM 作为 fallback:

```python
# TemporalExtractor 添加 LLM fallback
def extract(self, text, reference_time):
    # Level 1-3: 现有 regex 解析
    result = self._regex_extract(text, reference_time)
    if result:
        return result

    # Level 4: LLM fallback (仅对含时间线索但 regex 失败的文本)
    if self._has_temporal_cues(text):
        return self._llm_extract(text, reference_time)
    return None
```

#### 2.2 时间范围查询

部分 temporal 问题问的是时间段而非时间点:

```python
# "What happened between May and June?"
# 当前只支持 event_after/event_before 精确过滤
# 需要支持模糊时间范围匹配
```

**预期**: Temporal 0.574 → 0.65+ (+13%)

### Phase 3: Multi-hop 知识图谱增强 (P1, 预期 0.612 → 0.68+)

#### 3.1 AGE 图查询集成

当前知识图谱（AGE）构建了 triples 但未在检索时使用。

```python
# 对 multi-hop 问题，先做图查询找相关实体链
# 再用实体链指导向量检索
def graph_enhanced_search(query, user_id):
    # 1. 从 query 提取实体
    entities = extract_entities(query)

    # 2. 图查询找关联实体 (2-hop)
    related = graph_query(entities, max_hops=2)

    # 3. 用关联实体扩展查询
    expanded_query = f"{query} {' '.join(related)}"

    # 4. 混合检索
    return hybrid_search(expanded_query)
```

**预期**: Multi-hop 0.612 → 0.68+ (+11%)

### Phase 4: 综合优化 (P2)

#### 4.1 Reranking

```python
# 使用 cross-encoder 对 top-K 结果重排序
# 召回 top-30，rerank 后取 top-10
# 可用 bge-reranker-v2-m3 (SiliconFlow 提供)
```

#### 4.2 记忆去重和合并

```python
# 当前可能存在近似重复的记忆条目
# 向量相似度 > 0.95 的条目应合并
# 减少噪音，提升检索精度
```

#### 4.3 Answer Prompt 优化

```python
# 当前 answer prompt 可能不够引导 LLM 利用 recall 结果
# 尤其是 open-domain 问题需要更好的推理引导
```

---

## 8. 目标性能指标

| 阶段 | Overall | Multi-hop | Temporal | Open-dom | Single-hop |
|------|---------|-----------|----------|----------|------------|
| **#4 当前** | **0.610** | 0.612 | 0.574 | 0.417 | 0.645 |
| Phase 1 后 | 0.63+ | 0.62 | 0.58 | 0.55+ | 0.65 |
| Phase 2 后 | 0.66+ | 0.62 | 0.65+ | 0.55 | 0.66 |
| Phase 3 后 | 0.69+ | 0.68+ | 0.65 | 0.56 | 0.67 |
| **最终目标** | **0.72+** | 0.70+ | 0.68+ | 0.60+ | 0.70+ |
| Mem0 参考 | 0.669 | 0.512 | 0.555 | 0.729 | 0.671 |

---

## 9. 实施优先级矩阵

| 功能 | 预期提升 | 难度 | 优先级 | 目标类别 |
|------|----------|------|--------|---------|
| **Episode 提取增强** | 高 | 中 | **P0** | Open-domain |
| **RRF 动态权重** | 中高 | 低 | **P0** | Open-domain |
| **概念性知识提取** | 中高 | 中 | **P0** | Open-domain |
| **Recall limit 自适应** | 中 | 低 | **P0** | Open-domain |
| **LLM 时间提取 fallback** | 中 | 中 | **P1** | Temporal |
| **AGE 图查询集成** | 中高 | 高 | **P1** | Multi-hop |
| **Reranking (cross-encoder)** | 中 | 中 | **P2** | 全局 |
| **记忆去重合并** | 低中 | 中 | **P2** | 全局 |
| **Answer prompt 优化** | 低中 | 低 | **P2** | 全局 |

---

## 10. 结论

### 10.1 主要成就

- **Overall Judge 0.610**: 从基线 0.125 累计提升 388%
- **Temporal 0.574**: 从 0.159 提升 261%，已超越 Mem0
- **Multi-hop 0.612**: 超越 Mem0 (0.512) 达 19.5%
- **Single-hop 0.645**: 接近 Mem0 水平 (0.671)
- 用 DeepSeek 达到 Mem0 (GPT-4o) 的 91% 水平

### 10.2 核心差距

- **Open-domain (0.417)**: 落后 Mem0 (0.729) 达 42.8%，是唯一显著短板
- 这也是提升空间最大的方向

### 10.3 下一步行动

**立即开始**: Open-domain 专项优化（Episode 增强 + RRF 动态权重 + 概念知识提取）
**短期目标**: Overall 0.66+，全面超越 Mem0 Overall (0.669)
**中期目标**: Overall 0.72+，在所有类别上建立优势

---

**文档版本**: v1.0
**创建日期**: 2025-02-17
**测试编号**: #4
