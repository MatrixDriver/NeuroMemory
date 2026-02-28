---
description: "需求摘要: RPIV-2 分类逻辑（Reflection 引擎 + Trait 生命周期 + 召回改造）"
status: pending
created_at: 2026-03-01T01:30:00
updated_at: 2026-03-01T01:30:00
archived_at: null
---

# 需求摘要：RPIV-2 分类逻辑（Reflection 引擎 + Trait 生命周期 + 召回改造）

## 产品愿景
- **核心问题**：RPIV-1 铺好存储基座（trait 专用列、辅助表），但系统缺少 reflection 引擎来生成 trait、缺少生命周期管理让 trait 演化、召回公式未利用 trait 权重
- **价值主张**：让 neuromem 能从多次对话中自动归纳用户特质（behavior→preference→core），形成真正的"理解用户"能力
- **目标用户**：neuromem SDK 使用方（Me2、neuromem-cloud、第三方）
- **产品形态**：SDK 内部新增引擎 + 修改召回管道，公共 API 扩展但向后兼容

## 设计文档依赖

- **记忆分类 V2 设计**：`docs/design/memory-classification-v2.md`（权威参考）
- **存储方案 V2 设计**：`docs/design/storage-schema-v2.md`
- **RPIV-1 交付**：存储基座已就位（trait 专用列、4 张辅助表、content_hash 去重、halfvec 迁移）

## 核心场景（按优先级排序）

1. **Reflection 触发系统**：三种触发条件检查（重要度累积≥30 / 定时24h / 会话结束）
2. **Reflection 执行引擎**：9 步流程编排，1 次主 LLM 调用返回结构化操作
3. **Trait 生成**：从 fact/episodic 归纳 trend 和 behavior
4. **Trait 升级链**：behavior→preference→core 全链路
5. **置信度模型**：证据质量 4 级分级 + 间隔效应衰减
6. **矛盾处理**：检测+专项反思（修正 or 废弃，暂不做情境化分裂）
7. **召回公式改造**：trait_boost 权重 + 阶段过滤
8. **Trait 画像查询 API**：get_user_traits() 供应用层构建 prompt

## 产品边界

### MVP 范围内
- 上述 8 个场景全部完成
- 所有现有测试通过（353 个）
- reflect()/should_reflect()/get_user_traits() 公共 API
- 4 张辅助表填充（trait_evidence, reflection_cycles, memory_history, memory_sources）
- 现有 reflection.py 的 insight 生成逻辑**完全替换**为 9 步引擎

### 明确不做
- 情境化双面 trait 分裂（矛盾→contextual 复合 trait，P1）
- 两阶段反思（先提问再检索验证，P1）
- 召回即强化（recall 命中 trait 时 +0.02，P1）
- Trait Transparency UI（用户查看/编辑 trait，P1）
- 敏感特质保护（心理健康/政治/宗教不推断，P1）
- LIST 分区（P1）
- fact/episodic 的 LLM 操作判断 ADD/UPDATE/DELETE（Mem0 模式，P1）
- 异步 reflection 后台任务（保持同步调用模式）

### 后续版本
- P1：上述延后项 + core 拆分为 personality/value
- P2：程序性记忆、前瞻记忆、横向关联（Zettelkasten）

## 已知约束

- RPIV-1 存储基座已就位（trait 专用列、辅助表、content_hash 去重）
- 复用现有 LLM provider，不增加新的 provider 配置
- reflect() 保持同步调用（应用层控制调用时机），不引入后台异步任务
- 所有现有测试必须通过，公共 API 向后兼容
- 涉及 LLM Prompt 的功能计划，必须在计划文档中给出完整的 prompt 文本

## 架构决策

| 决策 | 内容 | 理由 |
|------|------|------|
| 触发时机 | 异步模式：应用层调用 reflect()，内置条件检查 | 不阻塞 ingest，LLM 调用耗时长 |
| LLM 操作判断 | 仅限 trait 管理范围 | fact/episodic 的 hash 去重已足够 |
| Prompt 调用 | 1 次主调用 + 1 次可选矛盾调用 | 成本可控，LLM 做模式识别，代码做数学 |
| LLM Provider | 复用现有 llm_provider | MVP 简单，用户可自定义 |
| 升级判断 | LLM 语义聚类 + 代码门槛验证 | "指向同一倾向"需语义理解 |
| Confidence | 使用 DB 存储值，reflection 时更新 | search 不做实时衰减计算 |
| 架构分层 | reflection.py(编排) + trait_engine.py(新建,生命周期) + search.py(召回) | 职责分离 |

## 各场景功能要点

### 场景 1：Reflection 触发系统

**功能点**：
- `should_reflect(user_id)` 公共方法，评估三种触发条件，返回 bool
- `reflect(user_id, force=False, session_ended=False)` 内置触发检查
  - force=True 跳过条件直接执行
  - session_ended=True 标记会话结束触发
  - 条件不满足时立即返回（无性能损耗）
- 重要度累积：`SUM(importance) FROM memories WHERE created_at > last_reflected_at AND memory_type IN ('fact', 'episodic')` ≥ 30
- 定时兜底：`NOW() - last_reflected_at` ≥ 24h
- 会话结束：session_ended 参数
- 状态存储：conversation_sessions.last_reflected_at

**异常处理**：
- last_reflected_at 为 NULL → 视为首次反思，直接触发
- 无新记忆 → 跳过（即使定时触发，无新数据也无意义）
- 并发调用 → 幂等处理（检查 last_reflected_at 是否刚更新）

### 场景 2：Reflection 执行引擎

**功能点**：
- 9 步执行流程：
  1. 扫描 last_reflected_at 后的所有新 fact/episodic
  2. [LLM] 检测短期趋势 → 生成 trend（带 valid_window）
  3. [代码] 检查已有 trend → 过期清除或升级为 candidate
  4. [LLM] 检测行为模式 → 生成/强化 behavior trait
  5. [LLM] 检测 behavior 聚类 → 升级为 preference
  6. [LLM] 检测 preference 聚类 → 升级为 core
  7. [LLM] 检测已有 trait 的矛盾证据
  8. [代码] 应用时间衰减 → confidence 更新，低于 0.1 则 dissolved
  9. [代码] 更新 last_reflected_at
- 步骤 2/4/5/6/7 合并为 1 次 LLM 调用
- LLM 输入：新增记忆列表 + 已有 trait 摘要（id, content, stage, subtype, confidence, context）
- LLM 输出：结构化 JSON
  ```json
  {
    "new_trends": [{"content": "...", "evidence_ids": [...], "window_days": 30, "context": "work"}],
    "new_behaviors": [{"content": "...", "evidence_ids": [...], "confidence": 0.4, "context": "..."}],
    "reinforcements": [{"trait_id": "...", "new_evidence_ids": [...], "quality_grade": "C"}],
    "contradictions": [{"trait_id": "...", "contradicting_evidence_ids": [...]}],
    "upgrades": [{"from_trait_ids": [...], "new_content": "...", "new_subtype": "preference", "reasoning": "..."}]
  }
  ```
- reflection_cycles 表写入：trigger_type, trigger_value, 统计信息（memories_scanned, traits_created, traits_reinforced, traits_dissolved）, status, timestamps

**异常处理**：
- LLM 返回格式错误 → JSON 解析失败时 fallback 跳过本轮，记录错误到 reflection_cycles
- LLM 调用失败 → 记录错误，不影响已有数据
- 新记忆为 0 → 仅执行步骤 3（trend 过期）和步骤 8（衰减），跳过 LLM 调用

### 场景 3：Trait 生成（trend + behavior）

**功能点**：
- trend 创建：
  - LLM 识别短期趋势
  - 写入：memory_type="trait", trait_stage="trend", trait_subtype="behavior"
  - trait_window_start=NOW(), trait_window_end=NOW()+window_days（LLM 建议 14 或 30 天，默认 30）
  - trait_confidence=NULL（trend 用 window 管理，不用 confidence）
  - trait_context 由 LLM 推断（work/personal/social/learning/general）
  - trait_derived_from="reflection"
- behavior 创建：
  - LLM 识别行为模式（≥3 条 fact/episodic 呈现相同模式）
  - 写入：trait_stage="candidate", trait_subtype="behavior", trait_confidence=0.4
  - trait_first_observed=最早证据时间
- 证据链写入：
  - trait_evidence 表：每条证据的 trait_id, memory_id, evidence_type("supporting"), quality(A/B/C/D)
  - quality 由 LLM 在输出中标注
- memory_sources 表：trait 关联来源 conversation_session
- 相似 trait 去重：content_hash 检查 + 向量相似度（>0.95 则视为重复，强化而非新建）

**关键约束**：trait 仅由 reflection 生成，永远不从单次对话直接提取

### 场景 4：Trait 升级链

**功能点**：
- behavior→preference：
  - LLM 识别 ≥2 个 behavior 指向同一倾向
  - 代码验证：各 behavior confidence ≥ 0.5
  - 创建 preference：trait_subtype="preference", trait_stage="emerging", confidence=MAX(子trait)+0.1
  - trait_parent_id 关联子 behavior
  - 子 behavior 保留（不压缩），通过 parent_id 双向引用
- preference→core：
  - LLM 识别 ≥2 个 preference 指向同一人格维度
  - 代码验证：各 preference confidence ≥ 0.6
  - 创建 core：trait_subtype="core", trait_stage="emerging", confidence=MAX(子trait)+0.1
- trend→candidate（纯代码，无需 LLM）：
  - 条件：valid_window 期间内被 ≥2 个**不同 reflection cycle** 强化
  - 动作：trait_stage="candidate", trait_confidence=0.3, 清空 window
- trend 过期清除（纯代码）：
  - 条件：NOW() > trait_window_end 且 强化 cycle 数 < 2
  - 动作：trait_stage="dissolved"
- 证据继承：升级产物继承子 trait 的全部证据（写入 trait_evidence）

**异常处理**：
- 循环引用检测：parent_id 不能指向自身或后代
- 升级后 stage 起始为 "emerging"（而非直接 "established"），需继续积累证据

### 场景 5：置信度模型

**功能点**：
- 强化：`new_confidence = old + (1 - old) * factor`
  - A 级（跨情境一致）→ 0.25
  - B 级（显式陈述）→ 0.20
  - C 级（跨对话行为）→ 0.15
  - D 级（同对话/隐式）→ 0.05
- 矛盾削弱：`new_confidence = old * (1 - factor)`
  - 单条矛盾 → factor=0.2
  - 强矛盾/多条 → factor=0.4
- 时间衰减（在 reflection 步骤⑧中执行，更新 DB 存储值）：
  ```
  effective_lambda = base_lambda / (1 + 0.1 * reinforcement_count)
  decayed = confidence * exp(-effective_lambda * days_since_last_reinforced)
  ```
  - base_lambda: behavior=0.005, preference=0.002, core=0.001
- 衰减后 confidence < 0.1 → trait_stage="dissolved"
- 阶段自动流转：
  - confidence < 0.3 → candidate
  - 0.3-0.6 → emerging
  - 0.6-0.85 → established
  - > 0.85 → core（stage，非 subtype）
- 更新字段：trait_reinforcement_count, trait_contradiction_count, trait_last_reinforced, trait_confidence

**异常处理**：confidence 永远 clamp 在 [0, 1] 范围内

### 场景 6：矛盾处理

**功能点**：
- 矛盾检测：LLM 在主调用中识别新证据与已有 trait 的矛盾
- 矛盾记录：
  - trait_contradiction_count + 1
  - trait_evidence 表写入 evidence_type="contradicting"
- 阈值判断：`contradiction_count / (reinforcement_count + contradiction_count) > 0.3`
- 超阈值触发专项 LLM 反思（第 2 次 LLM 调用）：
  - 输入：矛盾 trait + 全部 supporting/contradicting 证据内容
  - 输出：`{"action": "modify"|"dissolve", "new_content": "...", "reasoning": "..."}`
- 修正：更新 trait content、重新计算 confidence
- 废弃：trait_stage="dissolved", expired_at=NOW()
- 审计写入：memory_history 表记录 event="modified"|"dissolved", old_content, new_content, actor="reflection"

**异常处理**：
- 首次矛盾不触发反思（仅计数），给予累积观察期
- 专项反思 LLM 调用失败 → 保持现状，下次 reflection 再检查

### 场景 7：召回公式改造

**功能点**：
- trait_boost 权重映射：
  - trend=0.0, candidate=0.0（不参与 recall）
  - emerging=0.05, established=0.15, core=0.25
- 最终分数公式：`base_score * (1 + recency_bonus + importance_bonus + trait_boost)`
- 阶段过滤：搜索 SQL 添加 `AND NOT (memory_type = 'trait' AND trait_stage IN ('trend', 'candidate', 'dissolved'))`
- confidence 使用 DB 存储值（reflection 时已更新衰减），search 不做实时计算

**异常处理**：
- trait_stage 为 NULL → trait_boost=0（向后兼容 RPIV-1 之前的数据）
- memory_type 非 trait → trait_boost=0

### 场景 8：Trait 画像查询 API

**功能点**：
- `get_user_traits(user_id, min_stage="emerging", subtype=None, context=None)` 公共方法
- 返回用户所有活跃 trait（排除 dissolved）
- 按 stage 降序（core > established > emerging）+ confidence 降序排列
- 支持过滤：
  - min_stage：最低阶段（默认 "emerging"，排除 trend/candidate）
  - subtype：behavior/preference/core
  - context：work/personal/social/learning/general
- 返回格式：与 search 结果一致的 Memory 对象列表
- 用于应用层构建 system prompt（§6.2）

**异常处理**：
- 用户无 trait → 返回空列表
- 无效 stage/subtype 参数 → 忽略过滤条件
