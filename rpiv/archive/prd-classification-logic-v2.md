---
description: "产品需求文档: classification-logic-v2 (Reflection 引擎 + Trait 生命周期 + 召回改造)"
status: archived
created_at: 2026-03-01T02:00:00
updated_at: 2026-03-02T00:05:00
archived_at: 2026-03-02T00:05:00
---

# PRD: 分类逻辑 V2 — Reflection 引擎 + Trait 生命周期 + 召回改造

## 1. 执行摘要

neuromem SDK v0.8.0 已通过 RPIV-1 完成存储基座建设（Memory ORM 重写、trait 专用列、4 张辅助表、content_hash 去重、halfvec 迁移），但系统仍缺乏核心智能层：**从多次对话中自动归纳用户特质（trait）的 reflection 引擎**。当前的 `ReflectionService.digest()` 仅能生成浅层的 pattern/summary 洞察并更新情绪画像，无法实现 trait 的生成、升级、衰减和矛盾处理。

RPIV-2 将**完全替换**现有 `reflection.py` 的核心逻辑，实现 9 步反思流程编排，新建 `trait_engine.py` 管理 trait 生命周期（behavior→preference→core 升级链），改造 `search.py` 的召回公式加入 trait_boost 权重，并扩展公共 API 提供 `reflect()` / `should_reflect()` / `get_user_traits()` 三个新方法。

核心价值主张：让 neuromem 从"记住用户说了什么"进化为"理解用户是什么样的人"，通过经过多次验证的 trait 体系为应用层（Me2、neuromem-cloud、第三方）提供用户画像能力。

## 2. 使命

**产品使命**：为 AI agent 提供从对话历史中自动归纳、验证和演化用户特质的能力，使 AI 能真正"理解"用户而非仅"记住"用户。

**核心原则**：

1. **特质只能归纳，不能直接提取**：trait 仅由 reflection 引擎从多条 fact/episodic 中归纳产生，永不从单次对话直接提取（LLM 单次推断人格精度仅 r=0.27）
2. **渐进式置信度**：trait 需要跨多次对话反复验证才能从 trend 升级到 core，自动过滤偶发的人设表演
3. **遗忘即学习**：时间衰减 + 矛盾反思 + dissolved 归档三重遗忘机制保证信噪比
4. **向后兼容**：所有现有 353 个测试必须通过，公共 API 保持兼容

## 3. 目标用户

**主要用户角色**：neuromem SDK 的开发者 / 集成方

- **Me2 应用**：陪伴式 AI 聊天，需要用户画像构建 system prompt
- **neuromem-cloud**：SaaS 多租户服务，通过 REST API / MCP 暴露 trait 能力
- **第三方 AI agent 开发者**：需要 SDK 层面的记忆+特质管理

**技术舒适度**：Python 异步编程经验，熟悉 SQLAlchemy + PostgreSQL

**关键需求与痛点**：

- 当前 digest() 只生成浅层洞察，无法形成结构化的用户画像
- 缺乏从行为到偏好到人格的自动推断能力
- 召回结果未区分不同可信度的记忆
- 应用层无法获取用户的 trait 列表用于 prompt 构建

## 4. MVP 范围

### 范围内

- ✅ Reflection 触发系统：三种触发条件（重要度累积 / 定时24h / 会话结束）
- ✅ Reflection 执行引擎：9 步流程编排，1 次主 LLM 调用 + 1 次可选矛盾专项调用
- ✅ Trait 生成：从 fact/episodic 归纳 trend 和 behavior
- ✅ Trait 升级链：behavior→preference→core 全链路
- ✅ 置信度模型：证据质量 4 级分级（A/B/C/D）+ 间隔效应衰减
- ✅ 矛盾处理：检测 + 计数 + 超阈值专项反思（修正 or 废弃）
- ✅ 召回公式改造：trait_boost 权重 + 阶段过滤
- ✅ Trait 画像查询 API：get_user_traits() 公共方法
- ✅ 公共 API 扩展：reflect() / should_reflect() / get_user_traits()
- ✅ 新建 trait_engine.py：trait 生命周期管理模块
- ✅ 改写 reflection.py：9 步反思流程编排
- ✅ 4 张辅助表填充（trait_evidence, reflection_cycles, memory_history, memory_sources）
- ✅ 所有现有 353 测试通过
- ✅ ConversationSession ORM 补充 last_reflected_at（RPIV-1 遗留 #3）

### 范围外

- ❌ 情境化双面 trait 分裂（矛盾→contextual 复合 trait）— P1
- ❌ 两阶段反思（先提问再检索验证）— P1
- ❌ 召回即强化（recall 命中 trait 时 +0.02）— P1
- ❌ Trait Transparency UI（用户查看/编辑 trait）— P1
- ❌ 敏感特质保护（心理健康/政治/宗教不推断）— P1
- ❌ LIST 分区（存储方案 V2 设计中的 P1）— P1
- ❌ fact/episodic 的 LLM 操作判断 ADD/UPDATE/DELETE（Mem0 模式）— P1
- ❌ 异步 reflection 后台任务（保持同步调用模式）
- ❌ 物化视图 mv_trait_decayed — P1
- ❌ core 拆分为 personality + value — P1

## 5. 用户故事

1. **作为 AI agent 开发者**，我想要系统能从用户的多次对话中自动归纳出行为模式（如"深夜活跃"、"决策前必查数据"），以便构建更精准的用户画像。

2. **作为 Me2 应用开发者**，我想要获取用户的 trait 列表（按 core > preference > behavior 排序），以便在 system prompt 中包含用户核心特质，提升对话个性化水平。

3. **作为 SDK 使用方**，我想要调用 `should_reflect(user_id)` 检查是否需要触发反思，然后调用 `reflect(user_id)` 执行反思，以便在合适的时机（会话结束、重要信息累积）进行特质归纳。

4. **作为 AI agent 开发者**，我想要 trait 的置信度随时间自然衰减且被新证据强化时增长，以便系统自动保持用户画像的时效性。

5. **作为 SDK 使用方**，我想要当新证据与已有 trait 矛盾时系统能自动检测并在矛盾比例超阈值时触发专项反思，以便 trait 能被修正或废弃而非无限期保留错误特质。

6. **作为 AI agent 开发者**，我想要在召回结果中 trait 类型记忆按其阶段获得不同权重加成（core > established > emerging），以便高置信度特质在检索时被优先返回。

7. **作为 SDK 使用方**，我想要 `get_user_traits(user_id, min_stage="emerging")` 返回用户活跃 trait 的结构化列表，以便应用层灵活构建个性化 system prompt。

## 6. 核心架构与模式

### 6.1 架构分层

```
NeuroMemory (Facade, _core.py)
  ├── reflect() / should_reflect() / get_user_traits() ← 新增公共 API
  ├── ReflectionService (reflection.py) ← 完全改写：9 步反思流程编排
  │     ├── Step 1-2: 扫描 + LLM 主调用
  │     ├── Step 3: trend 过期/升级（纯代码）
  │     ├── Step 4-6: 处理 LLM 返回的 trait 操作
  │     ├── Step 7: 矛盾专项反思（可选 LLM 调用）
  │     ├── Step 8: 时间衰减（纯代码）
  │     └── Step 9: 更新水位线
  ├── TraitEngine (trait_engine.py) ← 新建：trait 生命周期管理
  │     ├── create_trend() / create_behavior()
  │     ├── reinforce_trait() / apply_contradiction()
  │     ├── try_upgrade_to_preference() / try_upgrade_to_core()
  │     ├── promote_trend_to_candidate()
  │     ├── expire_trends() / apply_decay()
  │     └── resolve_contradiction() — 专项反思
  ├── SearchService (search.py) ← 修改：trait_boost + 阶段过滤
  └── EmotionProfile update ← 保留现有逻辑
```

### 6.2 关键设计模式

- **Facade 模式**：`_core.py` 的 `NeuroMemory` 类提供统一入口，内部委托 Service 层
- **编排+引擎分离**：`reflection.py` 负责流程编排（9 步），`trait_engine.py` 负责 trait 生命周期操作，职责清晰
- **LLM 作模式识别、代码作数学**：LLM 负责语义理解（趋势检测、行为模式识别、矛盾判断），代码负责置信度计算、衰减公式、阶段流转
- **结构化 JSON 通信**：LLM 返回结构化 JSON，代码解析后执行

### 6.3 数据流

```
reflect(user_id) 调用流程：

1. should_reflect() 检查触发条件
   └── 重要度累积 ≥ 30 | 距上次 ≥ 24h | session_ended=True

2. 扫描 last_reflected_at 之后的新 fact/episodic
   └── SQL: WHERE created_at > last_reflected_at AND memory_type IN ('fact','episodic')

3. 加载已有 trait 摘要
   └── SQL: WHERE memory_type = 'trait' AND trait_stage NOT IN ('dissolved')

4. LLM 主调用（1 次）
   └── 输入: 新记忆列表 + 已有 trait 摘要
   └── 输出: new_trends, new_behaviors, reinforcements, contradictions, upgrades

5. 代码执行 trait 操作
   ├── TraitEngine.create_trend() / create_behavior()
   ├── TraitEngine.reinforce_trait()
   ├── TraitEngine.try_upgrade()
   └── TraitEngine.apply_contradiction()

6. 矛盾超阈值 → LLM 专项调用（可选）
   └── TraitEngine.resolve_contradiction()

7. TraitEngine.apply_decay() — 全量衰减

8. 更新 last_reflected_at 水位线

9. 写入 reflection_cycles 记录
```

## 7. 功能规格

### 场景 1：Reflection 触发系统

**功能点**：

- `should_reflect(user_id)` 公共方法，评估三种触发条件，返回 `bool`
- `reflect(user_id, force=False, session_ended=False)` 内置触发检查
  - `force=True` 跳过条件直接执行
  - `session_ended=True` 标记会话结束触发
  - 条件不满足时立即返回（无性能损耗）

**触发条件**：

| 条件 | 计算方式 | 阈值 |
|------|---------|------|
| 重要度累积 | `SUM(importance) FROM memories WHERE created_at > last_reflected_at AND memory_type IN ('fact','episodic')` | ≥ 30 |
| 定时兜底 | `NOW() - last_reflected_at` | ≥ 24 小时 |
| 会话结束 | `session_ended` 参数 | True |

**状态存储**：`conversation_sessions.last_reflected_at`（RPIV-1 已添加列，RPIV-2 需补充 ORM mapped_column）

**异常处理**：

- `last_reflected_at` 为 NULL → 视为首次反思，直接触发
- 无新记忆 → 跳过（即使定时触发，无新数据也无意义）
- 并发调用 → 幂等处理（检查 `last_reflected_at` 是否刚更新过，间隔 < 60s 则跳过）

### 场景 2：Reflection 执行引擎

**功能点**：

9 步执行流程：

| 步骤 | 类型 | 内容 |
|------|------|------|
| 1 | 代码 | 扫描 `last_reflected_at` 后的所有新 fact/episodic |
| 2 | LLM | 主调用：检测趋势 + 行为模式 + 强化 + 矛盾 + 升级（合并为 1 次调用） |
| 3 | 代码 | 检查已有 trend → 过期清除或升级为 candidate |
| 4 | 代码 | 处理 LLM 返回的 new_trends / new_behaviors（调用 TraitEngine） |
| 5 | 代码 | 处理 LLM 返回的 reinforcements（调用 TraitEngine） |
| 6 | 代码 | 处理 LLM 返回的 upgrades（调用 TraitEngine） |
| 7 | LLM(可选) | 矛盾超阈值 → 专项反思（第 2 次 LLM 调用） |
| 8 | 代码 | 应用时间衰减 → confidence 更新，低于 0.1 则 dissolved |
| 9 | 代码 | 更新 `last_reflected_at`、写入 `reflection_cycles` |

**LLM 主调用输入**：

```
新增记忆列表 + 已有 trait 摘要（id, content, stage, subtype, confidence, context）
```

**LLM 主调用 Prompt**：

```
你是一个用户特质分析引擎。根据用户的新增记忆和已有特质，执行以下分析任务。

## 已有特质
{existing_traits_json}

## 新增记忆（自上次反思以来）
{new_memories_json}

## 分析任务

请严格按以下规则分析，返回 JSON 结果：

### 1. 短期趋势检测 (new_trends)
- 从新增记忆中识别**近期趋势**（证据跨度短、数量少的初步模式）
- 每条 trend 需要至少 2 条记忆支撑
- 为每条 trend 推断情境标签(context): work/personal/social/learning/general
- 建议观察窗口(window_days): 情绪相关趋势 14 天，其他 30 天

### 2. 行为模式检测 (new_behaviors)
- 从新增记忆中识别**行为模式**（≥3 条记忆呈现相同模式，或跨度较长）
- 与已有 trait 内容去重：如果某个模式已被已有 trait 覆盖，归入 reinforcements 而非 new_behaviors
- 为每条 behavior 推断情境标签(context)
- 初始置信度建议：通常 0.4，跨情境一致的可以给 0.5

### 3. 已有 trait 强化 (reinforcements)
- 检查新增记忆中是否有支持已有 trait 的证据
- 标注证据质量等级：
  - A: 跨情境行为一致性（同一模式在 work+personal 等不同情境中出现）
  - B: 用户显式自我陈述（"我是个急性子"）
  - C: 跨对话行为（不同对话中观测到相同模式）
  - D: 同对话内信号或隐式推断

### 4. 矛盾检测 (contradictions)
- 检查新增记忆中是否有**与已有 trait 矛盾**的证据
- 仅报告明确矛盾，不报告细微差异

### 5. 升级建议 (upgrades)
- 检查已有 behavior 是否有 ≥2 个指向同一倾向 → 建议升级为 preference
- 检查已有 preference 是否有 ≥2 个指向同一人格维度 → 建议升级为 core
- 注意：升级建议由代码层验证 confidence 门槛后执行

只返回 JSON，不要其他内容：
```json
{
  "new_trends": [
    {
      "content": "趋势描述（具体、有细节）",
      "evidence_ids": ["记忆ID1", "记忆ID2"],
      "window_days": 30,
      "context": "work"
    }
  ],
  "new_behaviors": [
    {
      "content": "行为模式描述",
      "evidence_ids": ["记忆ID1", "记忆ID2", "记忆ID3"],
      "confidence": 0.4,
      "context": "work"
    }
  ],
  "reinforcements": [
    {
      "trait_id": "已有trait的UUID",
      "new_evidence_ids": ["记忆ID"],
      "quality_grade": "C"
    }
  ],
  "contradictions": [
    {
      "trait_id": "已有trait的UUID",
      "contradicting_evidence_ids": ["记忆ID"],
      "description": "矛盾描述"
    }
  ],
  "upgrades": [
    {
      "from_trait_ids": ["behavior-id-1", "behavior-id-2"],
      "new_content": "升级后的 preference/core 描述",
      "new_subtype": "preference",
      "reasoning": "升级理由"
    }
  ]
}
```
```

**LLM 主调用输出 Schema**：

```json
{
  "new_trends": [{"content": "...", "evidence_ids": [...], "window_days": 30, "context": "work"}],
  "new_behaviors": [{"content": "...", "evidence_ids": [...], "confidence": 0.4, "context": "work"}],
  "reinforcements": [{"trait_id": "...", "new_evidence_ids": [...], "quality_grade": "C"}],
  "contradictions": [{"trait_id": "...", "contradicting_evidence_ids": [...], "description": "..."}],
  "upgrades": [{"from_trait_ids": [...], "new_content": "...", "new_subtype": "preference", "reasoning": "..."}]
}
```

**reflection_cycles 表写入**：

| 字段 | 内容 |
|------|------|
| trigger_type | "importance_accumulated" / "scheduled" / "session_end" / "force" |
| trigger_value | 累积重要度值（importance 触发时） |
| memories_scanned | 扫描的新记忆数 |
| traits_created | 新建 trait 数（trend + behavior） |
| traits_updated | 更新 trait 数（reinforcement + upgrade） |
| traits_dissolved | dissolved trait 数（衰减 + 矛盾废弃） |
| status | "running" → "completed" / "failed" |
| error_message | 失败时记录错误信息 |

**异常处理**：

- LLM 返回格式错误 → JSON 解析失败时 fallback 跳过本轮 LLM 操作，仅执行步骤 3（trend 过期）和步骤 8（衰减），记录错误到 reflection_cycles
- LLM 调用失败（网络/超时）→ 记录错误到 reflection_cycles，不影响已有数据，不更新水位线（下次重试）
- 新记忆为 0 → 仅执行步骤 3（trend 过期）和步骤 8（衰减），跳过 LLM 调用

### 场景 3：Trait 生成（trend + behavior）

**功能点**：

**Trend 创建**（TraitEngine.create_trend）：

| 字段 | 值 |
|------|------|
| memory_type | "trait" |
| trait_stage | "trend" |
| trait_subtype | "behavior" |
| trait_confidence | NULL（trend 用 window 管理） |
| trait_window_start | NOW() |
| trait_window_end | NOW() + window_days（LLM 建议，默认 30 天） |
| trait_context | LLM 推断（work/personal/social/learning/general） |
| trait_derived_from | "reflection" |
| content | LLM 生成的趋势描述 |
| importance | 0.5（默认） |

**Behavior 创建**（TraitEngine.create_behavior）：

| 字段 | 值 |
|------|------|
| memory_type | "trait" |
| trait_stage | "candidate" |
| trait_subtype | "behavior" |
| trait_confidence | 0.4（LLM 建议值，clamp 在 [0.3, 0.5]） |
| trait_context | LLM 推断 |
| trait_first_observed | 最早证据的 created_at |
| trait_derived_from | "reflection" |

**证据链写入**（trait_evidence 表）：

- 每条证据：`trait_id`, `memory_id`, `evidence_type="supporting"`, `quality`（LLM 标注的 A/B/C/D）
- 在同一事务中与 trait 一起写入

**memory_sources 表写入**：

- trait 关联来源 conversation_session

**相似 trait 去重**：

1. `content_hash` 检查 → 完全匹配则视为重复，执行强化而非新建
2. 向量相似度 > 0.95 → 视为语义重复，执行强化而非新建

**关键约束**：trait 仅由 reflection 生成，永远不从单次对话直接提取

### 场景 4：Trait 升级链

**behavior→preference 升级**（TraitEngine.try_upgrade_to_preference）：

- 触发条件：LLM 在 upgrades 中建议 + 代码验证
- 代码验证：各源 behavior 的 confidence ≥ 0.5
- 创建 preference：
  - trait_subtype = "preference"
  - trait_stage = "emerging"（起始阶段）
  - trait_confidence = MAX(子 trait confidence) + 0.1
  - trait_parent_id 关联到子 behavior 的 UUID（子 behavior 保留，不压缩）
- 证据继承：升级产物继承子 trait 的全部证据（写入 trait_evidence）

**preference→core 升级**（TraitEngine.try_upgrade_to_core）：

- 触发条件：LLM 建议 + 代码验证各源 preference confidence ≥ 0.6
- 创建 core：
  - trait_subtype = "core"
  - trait_stage = "emerging"
  - trait_confidence = MAX(子 trait confidence) + 0.1

**trend→candidate 升级**（TraitEngine.promote_trend_to_candidate，纯代码）：

- 条件：valid_window 期间内被 ≥ 2 个**不同 reflection cycle** 强化
- 动作：trait_stage = "candidate"，trait_confidence = 0.3，清空 window 字段

**trend 过期清除**（TraitEngine.expire_trends，纯代码）：

- 条件：NOW() > trait_window_end 且 reinforcement_count < 2
- 动作：trait_stage = "dissolved"，expired_at = NOW()

**异常处理**：

- 循环引用检测：parent_id 不能指向自身或后代
- 升级后 stage 起始为 "emerging"（而非直接 "established"），需继续积累证据

### 场景 5：置信度模型

**强化计算**（TraitEngine.reinforce_trait）：

```python
new_confidence = old_confidence + (1 - old_confidence) * factor
```

| 证据质量 | factor | 说明 |
|---------|--------|------|
| A 级 | 0.25 | 跨情境行为一致性 |
| B 级 | 0.20 | 用户显式自我陈述 |
| C 级 | 0.15 | 跨对话行为 |
| D 级 | 0.05 | 同对话/隐式信号 |

同时更新：

- `trait_reinforcement_count += 1`
- `trait_last_reinforced = NOW()`

**矛盾削弱**（TraitEngine.apply_contradiction）：

```python
new_confidence = old_confidence * (1 - factor)
```

- 单条矛盾 → factor = 0.2
- 强矛盾/多条 → factor = 0.4

同时更新：`trait_contradiction_count += 1`

**时间衰减**（TraitEngine.apply_decay，在 reflection 步骤 8 中执行）：

```python
base_lambda = {"behavior": 0.005, "preference": 0.002, "core": 0.001}
effective_lambda = base_lambda[subtype] / (1 + 0.1 * reinforcement_count)
decayed = confidence * exp(-effective_lambda * days_since_last_reinforced)
```

- 衰减后 confidence < 0.1 → trait_stage = "dissolved"，expired_at = NOW()
- 更新 DB 存储值（search 不做实时衰减计算）

**阶段自动流转**（基于更新后的 confidence）：

| confidence 范围 | trait_stage |
|----------------|------------|
| < 0.1 | dissolved |
| < 0.3 | candidate |
| 0.3 - 0.6 | emerging |
| 0.6 - 0.85 | established |
| > 0.85 | core（stage，非 subtype） |

注意：阶段只能**向上**流转或降级为 dissolved，不能跳级。例如 candidate 的 confidence 达到 0.7 时流转到 established，不会直接跳到 core stage。

**异常处理**：confidence 永远 clamp 在 [0, 1] 范围内

### 场景 6：矛盾处理

**矛盾检测**：LLM 在主调用中识别新证据与已有 trait 的矛盾

**矛盾记录**：

1. `trait_contradiction_count += 1`
2. `trait_evidence` 表写入 `evidence_type="contradicting"`
3. 应用置信度削弱（factor=0.2）

**阈值判断**：

```python
contradiction_ratio = contradiction_count / (reinforcement_count + contradiction_count)
should_trigger_special_reflection = contradiction_ratio > 0.3 and contradiction_count >= 2
```

注意：首次矛盾不触发专项反思（`contradiction_count >= 2` 限制），给予累积观察期。

**专项 LLM 反思 Prompt**（第 2 次 LLM 调用）：

```
你是一个用户特质矛盾分析系统。请分析以下特质的矛盾情况并做出决策。

## 待分析特质
- 内容: {trait_content}
- 子类型: {trait_subtype}
- 当前置信度: {trait_confidence}
- 情境: {trait_context}

## 支持证据
{supporting_evidence_list}

## 矛盾证据
{contradicting_evidence_list}

## 请分析并做出决策

决策选项：
1. **modify**: 原判断需要修正，更新特质描述。适用于：证据整体支持该倾向但描述不够精确
2. **dissolve**: 证据太弱或矛盾太强，该特质不成立。适用于：支持证据和矛盾证据势均力敌或矛盾占优

只返回 JSON，不要其他内容：
```json
{
  "action": "modify" 或 "dissolve",
  "new_content": "修正后的特质描述（仅 modify 时需要）",
  "reasoning": "决策理由"
}
```
```

**专项反思结果处理**：

- `modify`：更新 trait content、重新计算 confidence（保留支持证据的累积效果，但打折）、写入 memory_history（event="modified"）
- `dissolve`：trait_stage = "dissolved"、expired_at = NOW()、写入 memory_history（event="dissolved"）

**memory_history 表审计记录**：

| 字段 | 内容 |
|------|------|
| memory_id | trait 的 UUID |
| memory_type | "trait" |
| event | "modified" / "dissolved" |
| old_content | 修改前的 content |
| new_content | 修改后的 content（dissolved 时为 NULL） |
| actor | "reflection" |

**异常处理**：

- 专项反思 LLM 调用失败 → 保持现状，下次 reflection 再检查
- LLM 返回无效 action → 保持现状，记录警告日志

### 场景 7：召回公式改造

**trait_boost 权重映射**：

| trait_stage | boost 值 | 说明 |
|-------------|---------|------|
| trend | 0.0 | 不参与 recall |
| candidate | 0.0 | 不参与 recall |
| emerging | 0.05 | 微弱加成 |
| established | 0.15 | 显著加成 |
| core（stage） | 0.25 | 最高加成 |

**最终分数公式**：

```python
final_score = base_rrf_score * (1 + recency_bonus + importance_bonus + trait_boost)
```

其中 recency_bonus 和 importance_bonus 保留现有 search.py 的计算逻辑。

**阶段过滤**：搜索 SQL 添加过滤条件，排除不参与 recall 的 trait：

```sql
AND NOT (memory_type = 'trait' AND trait_stage IN ('trend', 'candidate', 'dissolved'))
```

**异常处理**：

- trait_stage 为 NULL → trait_boost = 0（向后兼容 RPIV-1 之前的数据）
- memory_type 非 trait → trait_boost = 0

### 场景 8：Trait 画像查询 API

**功能点**：

`get_user_traits(user_id, min_stage="emerging", subtype=None, context=None)` 公共方法

**参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| user_id | str | 必需 | 用户 ID |
| min_stage | str | "emerging" | 最低阶段过滤（排除 trend/candidate） |
| subtype | str/None | None | 按子类过滤：behavior/preference/core |
| context | str/None | None | 按情境过滤：work/personal/social/learning/general |

**返回**：

- 排除 dissolved 的 trait 列表
- 按 stage 降序（core > established > emerging）+ confidence 降序排列
- 返回 Memory 对象列表（与 search 结果格式一致）

**SQL 查询模板**：

```sql
SELECT * FROM memories
WHERE user_id = :user_id
  AND memory_type = 'trait'
  AND trait_stage NOT IN ('dissolved')
  AND trait_stage >= :min_stage  -- 由代码层转换为具体过滤条件
  [AND trait_subtype = :subtype]
  [AND trait_context = :context]
ORDER BY
  CASE trait_stage
    WHEN 'core' THEN 1
    WHEN 'established' THEN 2
    WHEN 'emerging' THEN 3
    WHEN 'candidate' THEN 4
    WHEN 'trend' THEN 5
  END,
  trait_confidence DESC NULLS LAST
```

**异常处理**：

- 用户无 trait → 返回空列表
- 无效 stage/subtype 参数 → 忽略过滤条件，记录警告日志

## 8. 技术栈

**后端**：

- Python 3.10+
- SQLAlchemy 2.0 (async)
- PostgreSQL + pgvector (halfvec)
- 复用现有 LLM Provider（OpenAI/DeepSeek 兼容接口）
- 复用现有 Embedding Provider（SiliconFlow/OpenAI）

**依赖**：

- 无新增外部依赖
- 使用标准库 `math.exp` 做衰减计算
- 使用标准库 `hashlib` 做 content_hash

## 9. 安全与配置

**配置参数**（通过 NeuroMemory 构造函数或 reflect() 参数传入）：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| reflection_importance_threshold | 30 | 重要度累积触发阈值 |
| reflection_time_interval_hours | 24 | 定时触发间隔（小时） |
| trait_decay_enabled | True | 是否启用时间衰减 |
| contradiction_threshold | 0.3 | 矛盾比例触发专项反思的阈值 |

**安全范围**：

- SDK 层不涉及认证/授权（由应用层负责）
- 数据按 user_id 隔离
- LLM 调用复用现有 provider 配置

## 10. API 规范

### 公共 API 扩展（_core.py NeuroMemory 类）

```python
# 新增方法 1：检查是否应触发反思
async def should_reflect(self, user_id: str) -> bool:
    """检查用户是否满足反思触发条件。

    三种触发条件（任一满足即返回 True）：
    - 重要度累积 ≥ 阈值（默认 30）
    - 距上次反思 ≥ 时间间隔（默认 24h）
    - 首次反思（last_reflected_at 为 NULL）
    """

# 新增方法 2：执行反思
async def reflect(
    self,
    user_id: str,
    force: bool = False,
    session_ended: bool = False,
) -> dict:
    """执行用户特质反思。

    Args:
        user_id: 用户 ID
        force: True 时跳过触发条件检查
        session_ended: True 时标记为会话结束触发

    Returns:
        {
            "triggered": bool,          # 是否实际执行了反思
            "trigger_type": str | None, # "importance_accumulated" / "scheduled" / "session_end" / "force"
            "memories_scanned": int,
            "traits_created": int,
            "traits_updated": int,
            "traits_dissolved": int,
            "cycle_id": str | None,     # reflection_cycles 记录 ID
        }
    """

# 新增方法 3：获取用户特质列表
async def get_user_traits(
    self,
    user_id: str,
    min_stage: str = "emerging",
    subtype: str | None = None,
    context: str | None = None,
) -> list[dict]:
    """获取用户活跃特质列表。

    Returns:
        [
            {
                "id": "uuid",
                "content": "特质描述",
                "trait_subtype": "behavior|preference|core",
                "trait_stage": "emerging|established|core",
                "trait_confidence": 0.72,
                "trait_context": "work",
                "trait_reinforcement_count": 5,
                "trait_first_observed": "2024-01-15T...",
                "trait_last_reinforced": "2024-02-20T...",
                "created_at": "2024-01-15T...",
            },
            ...
        ]
    """
```

### 现有 API 变更

```python
# digest() 保持不变（向后兼容）
# 内部仍然调用 ReflectionService，但 ReflectionService 的实现已完全替换
# digest() 内部除了调用新的 reflect 逻辑外，保留 emotion_profile 更新

# ingest() 无变更
# recall() 无变更（search.py 内部改造对外透明）
```

## 11. 成功标准

**MVP 成功定义**：

- ✅ 8 个核心场景全部实现并通过测试
- ✅ 所有现有 353 个测试通过
- ✅ reflect() 能从多条 fact/episodic 中自动生成 trait（trend + behavior）
- ✅ trait 升级链完整工作（behavior→preference→core）
- ✅ 置信度模型正确（强化/削弱/衰减/阶段流转）
- ✅ 矛盾检测和专项反思正确触发和执行
- ✅ 召回结果中 trait 按阶段获得正确的 boost
- ✅ get_user_traits() 返回正确排序的 trait 列表

**质量指标**：

- 新增测试覆盖所有 8 个场景
- LLM prompt 能正确解析并处理各种边界情况
- 无数据泄漏（user_id 隔离）
- 所有数据库操作在事务中完成

**用户体验目标**：

- reflect() 单次执行耗时 < 10s（取决于 LLM 响应速度）
- should_reflect() 执行耗时 < 100ms（纯数据库查询）
- get_user_traits() 执行耗时 < 100ms

## 12. 实施阶段

### 阶段 1：基础设施补全（RPIV-1 遗留修复）

**目标**：补全 RPIV-1 遗留的基础设施问题

**交付物**：

- ✅ ConversationSession ORM 补充 `last_reflected_at` mapped_column
- ✅ 确认 4 张辅助表的 ORM 模型就绪

**验证标准**：现有 353 测试通过

### 阶段 2：TraitEngine + Reflection 引擎核心

**目标**：实现 trait 生命周期管理和反思流程编排

**交付物**：

- ✅ 新建 `neuromem/services/trait_engine.py`
- ✅ 改写 `neuromem/services/reflection.py`
- ✅ 扩展 `neuromem/_core.py` 三个新公共方法
- ✅ 完整的 LLM prompt 文本

**验证标准**：

- 场景 1-6 测试通过
- 手动验证 LLM 调用返回合理结果

### 阶段 3：召回改造 + API 集成

**目标**：搜索管道加入 trait 权重，公共 API 完整

**交付物**：

- ✅ 修改 `neuromem/services/search.py`
- ✅ get_user_traits() 实现
- ✅ 场景 7-8 测试

**验证标准**：

- 全部 8 个场景测试通过
- 现有 353 测试通过
- 召回结果中 trait 的排序正确

### 阶段 4：集成测试 + 回归

**目标**：端到端验证、回归测试

**交付物**：

- ✅ 端到端集成测试（ingest→reflect→recall 完整流程）
- ✅ 回归测试（确认无破坏性变更）
- ✅ 代码审查

**验证标准**：所有测试通过，代码审查无 CRITICAL/HIGH 问题

## 13. 未来考虑

**P1（近期增强）**：

- 情境化双面 trait 分裂（矛盾→contextual 复合 trait）
- 召回即强化（recall 命中 trait 时 +0.02 微弱强化）
- Trait Transparency UI（用户查看/编辑 trait + 证据链）
- 敏感特质保护（心理健康/政治/宗教类别不推断）
- LIST 分区 + 物化视图 mv_trait_decayed
- fact/episodic 的 LLM 操作判断（ADD/UPDATE/DELETE/NOOP）
- core 拆分为 personality + value

**P2（远期演进）**：

- 两阶段反思（先提问再检索验证，借鉴 Generative Agents）
- 程序性记忆（用户工作流程和交互模式）
- 前瞻记忆（用户未来意图和目标）
- 记忆间横向关联（Zettelkasten 自组织网络）
- Sleep-time 异步反思架构
- 跨用户 trait 模式发现（群体画像）

## 14. 风险与缓解措施

| # | 风险 | 影响 | 缓解措施 |
|---|------|------|----------|
| 1 | LLM 返回格式不稳定 | 反思流程中断 | JSON 解析容错 + fallback 跳过策略 + 错误记录到 reflection_cycles |
| 2 | 现有 digest() 调用方破坏 | Me2/Cloud 使用方受影响 | 保持 digest() 接口不变，内部逻辑替换；新功能通过 reflect() 暴露 |
| 3 | trait 生成质量依赖 LLM 能力 | 低质量 LLM 可能生成无意义 trait | 代码层验证门槛（证据数量、confidence 门槛）+ 衰减自动清理低质量 trait |
| 4 | reflection 执行时间过长 | 用户体验下降 | 保持同步调用模式但在 _core.py 层面支持 background=True；LLM 调用控制在 1-2 次 |
| 5 | 并发 reflect() 导致数据冲突 | trait 重复创建或 confidence 计算错误 | 幂等检查（last_reflected_at 间隔 < 60s 跳过）+ content_hash 去重 |

## 15. 附录

### 相关文档

| 文档 | 路径 | 说明 |
|------|------|------|
| 记忆分类 V2 设计 | `docs/design/memory-classification-v2.md` | 权威设计参考 |
| 存储方案 V2 设计 | `docs/design/storage-schema-v2.md` | 存储层设计 |
| RPIV-1 交付报告 | `rpiv/validation/delivery-report-storage-foundation-v2.md` | 已完成的存储基座 |
| 需求摘要 | `rpiv/brainstorm-summary-classification-logic-v2.md` | 需求来源 |

### 关键代码文件

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `neuromem/services/reflection.py` | 完全改写 | 9 步反思流程编排 |
| `neuromem/services/trait_engine.py` | 新建 | trait 生命周期管理 |
| `neuromem/services/search.py` | 修改 | trait_boost + 阶段过滤 |
| `neuromem/_core.py` | 扩展 | 3 个新公共 API |
| `neuromem/models/memory.py` | 无变更 | RPIV-1 已就位 |
| `neuromem/models/trait_evidence.py` | 无变更 | RPIV-1 已就位 |
| `neuromem/models/reflection_cycle.py` | 无变更 | RPIV-1 已就位 |
| `neuromem/models/memory_history.py` | 无变更 | RPIV-1 已就位 |
| `neuromem/models/memory_source.py` | 无变更 | RPIV-1 已就位 |
| `neuromem/models/conversation.py` | 小修改 | 补充 last_reflected_at mapped_column |

### 现有 ReflectionService 变更说明

当前 `reflection.py` 的核心逻辑将被**完全替换**：

| 现有功能 | RPIV-2 处理方式 |
|---------|----------------|
| `_generate_insights()` → 生成 pattern/summary | 替换为 9 步反思流程（trait 生成/升级/衰减） |
| `_update_emotion_profile()` → 情绪画像更新 | **保留**，作为反思流程的附属操作 |
| insight prompt → 简单模式识别 | 替换为结构化 trait 分析 prompt |
| 存储为 `memory_type="trait", trait_stage="trend"` | 保持，但增加完整 trait 字段填充 |

### emotion_profile 保留说明

现有的 emotion_profile 更新逻辑（`_update_emotion_profile`）**保留不变**。它与 trait 系统是正交的：

- emotion_profile 是用户级聚合统计（情绪基线）
- trait 是经过多次验证的行为/偏好/人格特质

两者在 `digest()` / `reflect()` 调用中可以共存执行。
