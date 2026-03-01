---
description: "测试策略: RPIV-2 分类逻辑（Reflection 引擎 + Trait 生命周期 + 召回改造）"
status: archived
created_at: 2026-03-01T02:00:00
updated_at: 2026-03-02T00:05:00
archived_at: 2026-03-02T00:05:00
---

# 测试策略：RPIV-2 分类逻辑

## 1. 测试范围

本测试策略覆盖 RPIV-2 的 8 个核心场景，按模块划分为 4 个测试文件：

| 测试文件 | 覆盖场景 | 主要被测模块 |
|----------|----------|-------------|
| `test_reflection_v2.py` | S1 触发系统 + S2 执行引擎 + S6 矛盾处理 | `services/reflection.py` |
| `test_trait_engine.py` | S3 Trait 生成 + S4 升级链 + S5 置信度模型 | `services/trait_engine.py`（新建） |
| `test_recall_v2.py` | S7 召回公式改造 | `services/search.py` |
| `test_trait_api.py` | S8 Trait 画像查询 API | `NeuroMemory` facade |

## 2. 测试类型

### 2.1 单元测试（纯逻辑，无 DB）

- 置信度计算公式（强化 / 矛盾 / 衰减）
- 阶段自动流转逻辑（confidence→stage 映射）
- trait_boost 权重映射
- LLM 返回结果的 JSON 解析与错误处理

### 2.2 集成测试（Mock LLM + 真实 DB）

- Reflection 触发条件检查（查 DB 累积 importance）
- Reflection 9 步执行流程端到端
- Trait 生成写入 DB（含 trait_evidence、memory_sources）
- Trait 升级链全链路（trend→candidate→emerging→established→core）
- 矛盾检测→专项反思→修正/废弃
- 召回 SQL 过滤（排除 trend/candidate/dissolved）
- get_user_traits() 查询与过滤

## 3. Mock 策略

### 3.1 LLM Mock（强制）

所有测试中 LLM 调用必须 mock，不依赖真实 LLM。使用方式与现有 `test_reflection.py` 保持一致：

```python
class MockReflectionLLM(LLMProvider):
    """返回预定义的 reflection 结构化 JSON 结果。"""

    def __init__(self, main_response: str = "", contradiction_response: str = ""):
        self._main_response = main_response
        self._contradiction_response = contradiction_response
        self._call_count = 0

    async def chat(self, messages, temperature=0.1, max_tokens=2048) -> str:
        self._call_count += 1
        if self._call_count == 1:
            return self._main_response
        return self._contradiction_response
```

**关键点**：
- 主调用返回 `new_trends` / `new_behaviors` / `reinforcements` / `contradictions` / `upgrades` 结构
- 矛盾专项反思调用返回 `action` + `new_content` + `reasoning`
- 模拟 JSON 格式错误用于异常路径测试

### 3.2 Embedding Mock（复用现有）

复用 `conftest.py` 中的 `MockEmbeddingProvider`（基于 hash 的确定性向量）。

### 3.3 数据库（真实）

使用 `localhost:5436` 的测试 PostgreSQL，复用 `conftest.py` 的 `db_session` fixture（每个测试函数独立事务 + rollback）。

## 4. 测试场景详细映射

### S1: Reflection 触发系统

| 测试用例 | 类型 | 描述 |
|----------|------|------|
| `test_should_reflect_importance_threshold` | 集成 | 新记忆 importance 累积 >= 30 时返回 True |
| `test_should_reflect_below_threshold` | 集成 | 累积 < 30 返回 False |
| `test_should_reflect_time_trigger` | 集成 | last_reflected_at 超过 24h 返回 True |
| `test_should_reflect_session_ended` | 集成 | session_ended=True 触发 |
| `test_should_reflect_first_time` | 集成 | last_reflected_at 为 NULL 视为首次反思 |
| `test_reflect_force_skips_conditions` | 集成 | force=True 跳过条件检查 |
| `test_reflect_no_new_memories_skips_llm` | 集成 | 无新记忆时跳过 LLM 调用，仅执行衰减 |
| `test_reflect_idempotent` | 集成 | 并发调用幂等性（last_reflected_at 刚更新则跳过） |

### S2: Reflection 执行引擎

| 测试用例 | 类型 | 描述 |
|----------|------|------|
| `test_reflection_nine_step_flow` | 集成 | 完整 9 步流程端到端验证 |
| `test_reflection_llm_single_call` | 集成 | 验证步骤 2/4/5/6/7 合并为 1 次 LLM 调用 |
| `test_reflection_llm_input_format` | 单元 | LLM 输入包含新记忆列表 + 已有 trait 摘要 |
| `test_reflection_llm_output_parsing` | 单元 | 解析结构化 JSON 输出（5 种操作） |
| `test_reflection_llm_invalid_json` | 单元 | JSON 解析失败时 fallback 跳过本轮 |
| `test_reflection_llm_call_failure` | 集成 | LLM 调用异常不影响已有数据 |
| `test_reflection_cycle_recorded` | 集成 | reflection_cycles 表正确写入统计 |
| `test_reflection_updates_last_reflected_at` | 集成 | 步骤 9 更新水位线 |

### S3: Trait 生成

| 测试用例 | 类型 | 描述 |
|----------|------|------|
| `test_create_trend` | 集成 | LLM 识别趋势 → 写入 trait(stage=trend, window) |
| `test_create_behavior` | 集成 | LLM 识别行为模式 → 写入 trait(stage=candidate, subtype=behavior) |
| `test_trait_evidence_written` | 集成 | trait_evidence 表正确关联证据 + quality 分级 |
| `test_memory_sources_written` | 集成 | memory_sources 表关联 conversation_session |
| `test_trait_dedup_hash` | 集成 | content_hash 重复 → 强化而非新建 |
| `test_trait_dedup_vector_similarity` | 集成 | 向量相似度 > 0.95 → 强化而非新建 |
| `test_trait_context_inferred` | 集成 | trait_context 由 LLM 推断正确赋值 |
| `test_trend_window_defaults` | 单元 | 默认 30 天窗口，LLM 可建议 14 天 |

### S4: Trait 升级链

| 测试用例 | 类型 | 描述 |
|----------|------|------|
| `test_trend_to_candidate` | 集成 | 窗口内 >= 2 个 cycle 强化 → 升级 candidate |
| `test_trend_expired_dissolved` | 集成 | 窗口结束 + 强化 < 2 → dissolved |
| `test_behavior_to_preference` | 集成 | >= 2 behavior(conf>=0.5) 同倾向 → preference |
| `test_preference_to_core` | 集成 | >= 2 preference(conf>=0.6) 同维度 → core |
| `test_upgrade_confidence_calculation` | 单元 | MAX(子trait conf) + 0.1 |
| `test_upgrade_parent_id_set` | 集成 | trait_parent_id 正确关联 |
| `test_upgrade_evidence_inherited` | 集成 | 证据继承到升级产物 |
| `test_upgrade_stage_starts_emerging` | 集成 | 升级产物 stage=emerging |
| `test_circular_reference_prevention` | 单元 | parent_id 不能指向自身或后代 |
| `test_behavior_upgrade_blocked_low_conf` | 集成 | behavior confidence < 0.5 时不升级 |

### S5: 置信度模型

| 测试用例 | 类型 | 描述 |
|----------|------|------|
| `test_reinforce_grade_a` | 单元 | A 级跨情境：factor=0.25 |
| `test_reinforce_grade_b` | 单元 | B 级显式陈述：factor=0.20 |
| `test_reinforce_grade_c` | 单元 | C 级跨对话：factor=0.15 |
| `test_reinforce_grade_d` | 单元 | D 级同对话：factor=0.05 |
| `test_contradiction_single` | 单元 | 单条矛盾：factor=0.2 |
| `test_contradiction_strong` | 单元 | 强矛盾：factor=0.4 |
| `test_decay_behavior` | 单元 | behavior lambda=0.005 衰减 |
| `test_decay_preference` | 单元 | preference lambda=0.002 衰减 |
| `test_decay_core` | 单元 | core lambda=0.001 衰减 |
| `test_decay_spacing_effect` | 单元 | 强化次数越多衰减越慢 |
| `test_confidence_clamp` | 单元 | confidence 始终 clamp 在 [0, 1] |
| `test_dissolved_threshold` | 单元 | confidence < 0.1 → dissolved |
| `test_stage_auto_transition` | 单元 | confidence 区间 → 自动阶段流转 |
| `test_reinforce_updates_fields` | 集成 | 更新 reinforcement_count, last_reinforced, confidence |

### S6: 矛盾处理

| 测试用例 | 类型 | 描述 |
|----------|------|------|
| `test_contradiction_count_increment` | 集成 | 矛盾计数 +1 + evidence 写入 |
| `test_contradiction_below_threshold` | 集成 | ratio <= 0.3 时不触发专项反思 |
| `test_contradiction_triggers_reflection` | 集成 | ratio > 0.3 触发第 2 次 LLM 调用 |
| `test_contradiction_modify_trait` | 集成 | LLM 决定修正 → content + confidence 更新 |
| `test_contradiction_dissolve_trait` | 集成 | LLM 决定废弃 → stage=dissolved |
| `test_contradiction_audit_trail` | 集成 | memory_history 表记录 event + old/new content |
| `test_contradiction_llm_failure_safe` | 集成 | 专项反思 LLM 失败 → 保持现状 |
| `test_first_contradiction_no_reflection` | 集成 | 首次矛盾仅计数不触发反思 |

### S7: 召回公式改造

| 测试用例 | 类型 | 描述 |
|----------|------|------|
| `test_trait_boost_weights` | 单元 | 各阶段 boost 值验证 |
| `test_recall_score_with_trait_boost` | 集成 | base_score * (1 + recency + importance + trait_boost) |
| `test_recall_filters_trend` | 集成 | trait(stage=trend) 不出现在结果中 |
| `test_recall_filters_candidate` | 集成 | trait(stage=candidate) 不出现在结果中 |
| `test_recall_filters_dissolved` | 集成 | trait(stage=dissolved) 不出现在结果中 |
| `test_recall_includes_emerging` | 集成 | trait(stage=emerging) 正常返回 |
| `test_recall_null_stage_compat` | 集成 | trait_stage=NULL → boost=0（向后兼容） |
| `test_recall_non_trait_no_boost` | 集成 | fact/episodic 不受 trait_boost 影响 |

### S8: Trait 画像查询 API

| 测试用例 | 类型 | 描述 |
|----------|------|------|
| `test_get_user_traits_basic` | 集成 | 返回活跃 trait 列表 |
| `test_get_user_traits_excludes_dissolved` | 集成 | 排除 dissolved trait |
| `test_get_user_traits_min_stage_filter` | 集成 | min_stage 过滤（默认 emerging） |
| `test_get_user_traits_subtype_filter` | 集成 | subtype 过滤 |
| `test_get_user_traits_context_filter` | 集成 | context 过滤 |
| `test_get_user_traits_ordering` | 集成 | 按 stage 降序 + confidence 降序 |
| `test_get_user_traits_empty_user` | 集成 | 无 trait 用户返回空列表 |
| `test_get_user_traits_invalid_params` | 集成 | 无效参数忽略过滤条件 |

## 5. 回归要求

- 现有 353 个测试必须全部通过
- RPIV-2 新增测试全部通过
- 运行命令：`cd D:/CODE/NeuroMem && uv run python -m pytest tests/ -v --tb=short`

**重点回归关注**：
- `test_reflection.py`：现有 reflection/digest 行为不变
- `test_search.py`：现有搜索评分不受 trait_boost 副作用影响
- `test_recall.py` / `test_conversation_recall.py`：recall 管道兼容
- `test_storage_v2_*.py`：存储层兼容

## 6. 测试数据准备策略

### 6.1 Fixtures（conftest.py 扩展）

在 `conftest.py` 中新增以下 fixtures：

```python
@pytest_asyncio.fixture
async def sample_memories(db_session, mock_embedding):
    """预插入一批 fact/episodic 记忆，供 reflection 测试使用。"""
    svc = SearchService(db_session, mock_embedding)
    memories = []
    for i in range(5):
        m = await svc.add_memory(
            user_id="test_user",
            content=f"测试事实 {i}",
            memory_type="fact",
            metadata={"importance": 7},
        )
        memories.append(m)
    await db_session.commit()
    return memories

@pytest_asyncio.fixture
async def sample_traits(db_session, mock_embedding):
    """预插入各阶段的 trait，供升级/召回测试使用。"""
    ...
```

### 6.2 测试数据原则

1. **不硬编码 UUID**：使用 `uuid.uuid4()` 动态生成
2. **中文内容优先**：与实际使用场景一致
3. **覆盖边界值**：confidence=0.0, 0.1, 0.3, 0.5, 0.6, 0.85, 1.0
4. **时间可控**：使用 `freezegun` 或手动设置 `created_at` 控制时间相关逻辑

### 6.3 辅助函数

```python
async def create_trait(db_session, mock_embedding, **kwargs):
    """快速创建 trait 记忆的辅助函数。"""
    defaults = {
        "user_id": "test_user",
        "content": "测试 trait",
        "memory_type": "trait",
        "trait_subtype": "behavior",
        "trait_stage": "candidate",
        "trait_confidence": 0.4,
        "trait_context": "general",
    }
    defaults.update(kwargs)
    ...
```

## 7. 测试依赖

| 依赖 | 用途 | 现有/新增 |
|------|------|----------|
| pytest | 测试框架 | 现有 |
| pytest-asyncio | 异步测试 | 现有 |
| sqlalchemy + asyncpg | 数据库操作 | 现有 |
| pgvector | 向量检索 | 现有 |
| freezegun（可选） | 时间冻结（衰减测试） | 视需要新增 |

## 8. 测试执行计划

1. **阶段 1**（T7 编写测试代码）：编写全部测试用例，部分预期失败（实现未完成）
2. **阶段 2**（T8 运行测试）：实现完成后全量运行
3. **问题分类**：
   - A 类（测试代码 bug）→ QA 自行修复
   - B 类（实现 bug）→ 通知 dev-1
   - C 类（设计问题）→ 升级到 team leader

## 9. 验收标准

- 全部新增测试用例通过
- 全部 353 个现有测试通过
- 测试覆盖所有 8 个场景的正常路径 + 异常路径 + 边界条件
- LLM 调用全部 mock，测试可离线运行
- 测试运行时间 < 60 秒（不含 DB 初始化）

## 10. PRD 细化后的测试规格补充

基于 PRD `rpiv/requirements/prd-classification-logic-v2.md` 的细化，以下是对原始测试策略的补充和修正：

### 10.1 向后兼容性测试（新增关注点）

PRD 明确 `digest()` 接口保持不变，内部调用新的 reflect 逻辑 + 保留 emotion_profile 更新。需新增：

| 测试用例 | 文件 | 描述 |
|----------|------|------|
| `test_digest_backward_compat` | test_reflection_v2.py | digest() 返回结构不变：含 insights, emotion_profile, insights_generated |
| `test_digest_still_updates_emotion` | test_reflection_v2.py | digest() 调用后 emotion_profiles 表仍被更新 |
| `test_reflect_returns_expected_format` | test_reflection_v2.py | reflect() 返回 {triggered, trigger_type, memories_scanned, traits_created, traits_updated, traits_dissolved, cycle_id} |

### 10.2 矛盾处理规则修正

PRD 明确矛盾专项反思的触发条件为 **双重门槛**：
```python
should_trigger = contradiction_ratio > 0.3 and contradiction_count >= 2
```

更新 S6 测试用例：

| 测试用例 | 修正内容 |
|----------|----------|
| `test_first_contradiction_no_reflection` | 确认 contradiction_count=1 时即使 ratio>0.3 也不触发 |
| `test_contradiction_triggers_reflection` | 需同时满足 ratio>0.3 AND count>=2 |

### 10.3 阶段流转约束

PRD 明确阶段"只能向上流转或降级为 dissolved"，新增：

| 测试用例 | 文件 | 描述 |
|----------|------|------|
| `test_stage_no_skip` | test_trait_engine.py | candidate(conf=0.7) 流转到 established 而非 core stage |
| `test_stage_only_upward_or_dissolved` | test_trait_engine.py | 阶段不能从 established 降到 emerging（除非 dissolved） |

### 10.4 并发幂等性

PRD 明确幂等检查条件为 `last_reflected_at 间隔 < 60s 则跳过`：

| 测试用例 | 文件 | 描述 |
|----------|------|------|
| `test_reflect_idempotent_60s_window` | test_reflection_v2.py | last_reflected_at 在 60s 内时 reflect() 返回 triggered=False |

### 10.5 LLM 调用失败时不更新水位线

PRD 明确：LLM 调用失败时 **不更新 last_reflected_at**（下次可重试）

| 测试用例 | 文件 | 描述 |
|----------|------|------|
| `test_llm_failure_no_watermark_update` | test_reflection_v2.py | LLM 异常时 last_reflected_at 不变 |

### 10.6 Behavior 创建的 confidence 约束

PRD 明确 behavior 初始 confidence 由 LLM 建议但 clamp 在 [0.3, 0.5]：

| 测试用例 | 文件 | 描述 |
|----------|------|------|
| `test_behavior_confidence_clamped` | test_trait_engine.py | LLM 建议 0.8 时 clamp 到 0.5；建议 0.1 时 clamp 到 0.3 |

### 10.7 ConversationSession ORM 补全

PRD 标注 RPIV-1 遗留 #3：ConversationSession 需补充 `last_reflected_at` mapped_column。需验证：

| 测试用例 | 文件 | 描述 |
|----------|------|------|
| `test_conversation_session_has_last_reflected_at` | test_reflection_v2.py | ORM 模型包含 last_reflected_at 字段 |

### 10.8 完整测试用例计数

| 测试文件 | 原始用例数 | PRD 补充用例数 | 总计 |
|----------|-----------|---------------|------|
| test_reflection_v2.py | 16 | 6 | 22 |
| test_trait_engine.py | 24 | 3 | 27 |
| test_recall_v2.py | 8 | 0 | 8 |
| test_trait_api.py | 8 | 0 | 8 |
| **总计** | **56** | **9** | **65** |
