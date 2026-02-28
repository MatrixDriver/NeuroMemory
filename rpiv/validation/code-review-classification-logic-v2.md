---
description: "代码审查: classification-logic-v2 (Reflection 引擎 + Trait 生命周期 + 召回改造)"
status: completed
created_at: 2026-03-01T04:30:00
updated_at: 2026-03-01T04:30:00
related_files:
  - rpiv/plans/plan-classification-logic-v2.md
  - rpiv/requirements/prd-classification-logic-v2.md
---

# 代码审查: classification-logic-v2

## 审查范围

| 文件 | 变更类型 | 行数 |
|------|----------|------|
| `neuromem/services/trait_engine.py` | 新建 | ~675 行 |
| `neuromem/services/reflection.py` | 重写 | ~768 行 |
| `neuromem/services/search.py` | 修改 | 3 处改动 |
| `neuromem/_core.py` | 修改 | 3 个新方法 |
| `neuromem/models/memory_history.py` | 原有 | 审查字段约束 |

## 缺陷清单

### BUG-1: `_find_similar_trait()` SQL 格式化错误 [严重]

**位置**: `neuromem/services/trait_engine.py:596`

**问题**: ORDER BY 子句中 `'{vector_str}'` 是字面量字符串，而非 f-string 插值。第 595 行正确使用了 f-string 插值，但第 596 行遗漏了 `f` 前缀。

```python
# 第 595 行（正确）
f"AND 1 - (embedding <=> '{vector_str}') > 0.95 "
# 第 596 行（错误 — 缺少 f 前缀）
"ORDER BY embedding <=> '{vector_str}' LIMIT 1"
```

**影响**: 所有 `create_trend()` / `create_behavior()` 调用在首次创建时触发向量去重检查会报 SQL 错误 `InvalidTextRepresentationError: invalid input syntax for type halfvec`，导致 trait 创建全部失败。

**修复**: 第 596 行加 `f` 前缀：
```python
f"ORDER BY embedding <=> '{vector_str}' LIMIT 1"
```

**受影响测试**: 13 个（test_trait_engine 7 个 + test_reflection_v2 6 个）

---

### BUG-2: `memory_history.event` 列 varchar(20) 过短 [中等]

**位置**:
- `neuromem/models/memory_history.py:23` — `String(20)`
- `neuromem/services/trait_engine.py:544` — `event="contradiction_dissolve"` (22 字符)

**问题**: `contradiction_dissolve` 长度 22 超出 varchar(20) 限制，INSERT 时触发 `StringDataRightTruncationError`。

**修复方案**（二选一）:
- A: 将 `memory_history.event` 列改为 `String(30)`（推荐，需要 Alembic migration）
- B: 将事件名缩短为 `"contra_dissolve"` / `"contra_modify"`

**受影响测试**: 1 个 (test_resolve_dissolve)

---

### BUG-3: `digest()` 向后兼容性不完整 [中等]

**位置**: `neuromem/services/reflection.py:551-570`

**问题**: 重写后的 `digest()` 方法硬编码返回 `{"insights": [], ...}`，旧测试期望它调用 LLM 生成 insights。emotion_profile 返回值中 `latest_state` 字段在 MockLLM 返回无效 JSON 时回退到固定字符串 `"近期情感状态"`，与旧测试预期不符。

**具体表现**:
1. `test_reflect_generates_insights` — 期望 `len(insights) == 2`，实际返回空列表
2. `test_reflect_stores_as_insight_type` — 期望 insights 存储为 trait 类型，实际无 insights 生成
3. `test_reflect_updates_emotion_profile` — 期望 `latest_state == "近期工作压力大，情绪低落"`，实际为 `"近期情感状态"`（MockLLM 返回的 JSON 无法解析为有效 emotion summary）
4. `test_reflect_watermark_initial` — 期望 watermark 更新，新 digest() 未更新 watermark
5. `test_reflect_batch_pagination` — 期望多次 LLM 调用，新 digest() 无 batch 逻辑

**影响范围**: 5 个旧测试失败（全部是回归缺陷）

**修复方向**: 有两种策略：
- A: 让旧测试适配新实现（如果旧 digest API 不再需要保留 insights 生成功能）
- B: 在 digest() 中恢复部分旧逻辑（如果 neuromem-cloud/Me2 依赖旧行为）

---

## 代码质量评审

### 正面评价

1. **TraitEngine 结构清晰**: 每个方法职责单一，置信度计算、衰减公式、升级链逻辑与设计文档一致
2. **ReflectionService 9 步流程完整**: 从触发检查到 watermark 更新全链路覆盖
3. **CONTRADICTION_PROMPT 设计合理**: 结构化输入、明确的 JSON 输出格式要求
4. **search.py 改动最小化**: 3 处精准改动（stage filter + trait_boost + trait_stage 列传递），不影响非 trait 查询
5. **公共 API 使用独立 session**: `should_reflect()` / `reflect()` / `get_user_traits()` 每次调用开启独立 session，符合 facade 模式
6. **错误处理合理**: LLM 失败时 resolve_contradiction 安全降级返回 dissolve

### 改进建议

1. **SQL 注入风险** (`trait_engine.py:595-596`): vector_str 直接拼入 SQL，虽然值来自内部 embedding 函数（非用户输入），但建议改用参数化查询或 pgvector 的 ORM 操作符
2. **`_validate_evidence_ids` 效率**: 逐个查询 evidence_id 存在性（第 614-624 行），建议改为批量 `WHERE id = ANY(:ids)` 查询
3. **promote_trends 条件**: 第 370 行 `trait_window_end >= now` 意味着窗口未过期才能升级。结合 `expire_trends` 的 `trait_window_end < now`，两者互斥覆盖所有情况，逻辑正确。但建议添加注释说明 "window 内且强化 >= 2 次" 的语义
4. **`_parse_json` 重复**: `trait_engine.py` 和 `reflection.py` 各有一个几乎相同的 `_parse_json` / `_parse_reflection_result`，建议提取为公共 utility

### 与 PRD 对齐检查

| PRD 需求 | 实现状态 | 备注 |
|----------|----------|------|
| 反思触发三条件 | OK | importance >= 30, 24h, first_time |
| 60s 幂等窗口 | OK | should_reflect 第 161 行 |
| LLM 失败不更新 watermark | OK | _run_reflection_steps 第 321-322 行 |
| behavior confidence 钳制 [0.3, 0.5] | OK | create_behavior 第 159 行 |
| 矛盾双阈值 ratio>0.3 且 count>=2 | OK | apply_contradiction 第 253 行 |
| trait_boost 权重 core=0.25, established=0.15, emerging=0.05 | OK | search.py 第 391-394 行 |
| stage 过滤排除 trend/candidate/dissolved | OK | search.py 第 315 行 |
| 升级从 emerging 开始 | OK | try_upgrade 第 324 行 |
| 衰减间隔效应 | OK | apply_decay 第 441 行 |
| get_user_traits 排序 stage desc + confidence desc | OK | _core.py SQL ORDER BY |

## 总结

实现整体与计划/PRD 对齐良好，核心逻辑正确。需要修复 3 个 bug（BUG-1 最紧急，一行修复即可解锁 13 个测试），然后决定 BUG-3 的向后兼容策略。
