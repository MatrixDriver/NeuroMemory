---
description: "技术调研: classification-logic-v2"
status: completed
created_at: 2026-03-01T02:00:00
updated_at: 2026-03-01T02:30:00
archived_at: null
---

# 技术调研：RPIV-2 分类逻辑

## 1. LLM Provider 能力

### 1.1 现有接口

LLM Provider 体系由抽象基类 `LLMProvider`（`neuromem/providers/llm.py`）定义，仅有一个方法：

```python
async def chat(self, messages: list[dict], temperature: float = 0.1, max_tokens: int = 2048) -> str
```

三个具体实现：
- **OpenAILLM**（`openai_llm.py`）：兼容 OpenAI/DeepSeek 等，支持 reasoner 模型自动转换
- **CallbackLLM**（`callback_llm.py`）：MCP Host 模式，不直接调用 API
- **SiliconFlowEmbedding**（`siliconflow.py`）：仅 Embedding，非 LLM

### 1.2 结构化 JSON 输出

- **现有支持**：`chat()` 返回原始字符串，RPIV-2 需要 JSON 解析
- **现有实践**：`reflection.py` 的 `_parse_insight_result()` 和 `_parse_emotion_summary()` 已实现了 JSON 提取逻辑（处理 ```json 代码块包裹），可直接复用此模式
- **结论**：**无需新增 provider 方法**。现有 `chat()` 方法配合 prompt 要求 JSON 输出 + 代码端解析即可满足需求。RPIV-2 的 reflection 主调用和矛盾调用都可使用相同模式

### 1.3 System Prompt 自定义

- **完全支持**：`chat()` 接受 `messages: list[dict]`，可自由构建 system/user 消息序列
- 现有代码仅使用 `{"role": "user"}` 单消息模式（见 `_build_insight_prompt`），但接口不限制 role 类型
- RPIV-2 的 reflection prompt 可使用 `{"role": "system"}` 定义角色 + `{"role": "user"}` 传入数据

### 1.4 Token 限制控制

- **完全支持**：`max_tokens` 参数可自定义
- RPIV-2 的主 LLM 调用（含新记忆列表 + 已有 trait 摘要）可能需要更大的 `max_tokens`（建议 4096）
- OpenAILLM 的 reasoner 模式已自动扩展到 4096

### 1.5 结论

**现有 `chat()` 方法完全够用**，无需新增任何 LLM Provider 方法。RPIV-2 需要：
1. 构建新的 prompt（system + user 消息）
2. 复用现有 JSON 解析模式
3. 适当调整 max_tokens 和 temperature

## 2. 现有 Reflection 实现

### 2.1 当前架构

**ReflectionService**（`neuromem/services/reflection.py`）：
- 入口：`digest(user_id, recent_memories, existing_insights)`
- 两个功能：
  1. `_generate_insights()` → 生成 insight（已改为 `memory_type="trait", trait_stage="trend"`）
  2. `_update_emotion_profile()` → 更新情绪画像

**_core.py 中的调用链**：
- `NeuroMemory.digest(user_id, batch_size, background)` → `_digest_impl()`
- 水位线存储在 **emotion_profiles.last_reflected_at**（非 conversation_sessions）
- 按 batch_size 分页处理未消化的记忆
- `_maybe_trigger_digest()` 作为 post-extraction hook，每 N 条消息自动触发

### 2.2 可复用的部分

| 组件 | 可复用性 | 说明 |
|------|---------|------|
| `_core._digest_impl()` 分页架构 | **需要重大改造** | 当前只做简单的 insight 生成，RPIV-2 需要 9 步流程 |
| `_core._maybe_trigger_digest()` 触发机制 | **部分复用** | 当前是简单计数器，需要扩展为三条件（重要度/定时/会话结束） |
| JSON 解析模式 | **完全复用** | `_parse_insight_result()` 的 ```json 提取模式 |
| 情绪 profile 更新 | **保留** | `_update_emotion_profile()` 独立于 trait 逻辑，不受影响 |
| LLM 调用模式 | **完全复用** | `self._llm.chat(messages=[...])` 模式 |
| 水位线推进 | **需要迁移** | 从 emotion_profiles 迁移到 conversation_sessions |

### 2.3 需要完全重写的部分

| 组件 | 原因 |
|------|------|
| `_generate_insights()` | 需要替换为 9 步 reflection 引擎，当前仅生成 trend 级 insight |
| `_build_insight_prompt()` | 需要全新的 prompt，包含 trait 摘要输入和结构化操作输出 |
| `_digest_impl()` 中的主循环 | 需要加入 trend 过期检查、衰减计算、矛盾处理等步骤 |

### 2.4 建议的架构变更

```
# 当前
_core.py → ReflectionService.digest() → _generate_insights() + _update_emotion_profile()

# RPIV-2
_core.py → reflect(user_id, force, session_ended)
         → should_reflect(user_id)
         → ReflectionService（重写为 9 步编排器）
         → TraitEngine（新建，trait 生命周期管理）
         → 保留 _update_emotion_profile()
```

## 3. Search 召回逻辑

### 3.1 当前评分公式

`scored_search()` 方法（`search.py:234`）的评分公式：

```
score = base_relevance * (1 + recency_bonus + importance_bonus)

base_relevance = min(cosine_similarity + bm25_hit*0.05, 1.0)
recency_bonus  = 0.15 * exp(-seconds / (decay_rate * (1 + arousal * 0.5)))
importance_bonus = 0.15 * (importance / 10.0)
```

### 3.2 trait_boost 集成方案

**最小改动方案**：在 `scored_search()` 的 SQL 最终评分中添加 `trait_boost`：

```sql
-- 现有
LEAST(vector_score + CASE WHEN bm25_score > 0 THEN 0.05 ELSE 0 END, 1.0)
* (1.0 + recency_bonus + importance_bonus)

-- RPIV-2
LEAST(vector_score + CASE WHEN bm25_score > 0 THEN 0.05 ELSE 0 END, 1.0)
* (1.0 + recency_bonus + importance_bonus
   + CASE
       WHEN memory_type = 'trait' THEN
           CASE trait_stage
               WHEN 'core'        THEN 0.25
               WHEN 'established' THEN 0.15
               WHEN 'emerging'    THEN 0.05
               ELSE 0
           END
       ELSE 0
     END
)
```

**需要修改的位置**：
1. `scored_search()` 的 SQL SELECT 增加 `trait_stage` 列读取
2. `scored_search()` 的评分公式增加 `trait_boost` 项
3. 添加阶段过滤：`AND NOT (memory_type = 'trait' AND trait_stage IN ('trend', 'candidate', 'dissolved'))`

**注意**：当前 SQL 查询的 `memories` 表已有 `trait_stage` 列（RPIV-1 已添加），无需 schema 变更。

### 3.3 阶段过滤的添加位置

在 `filters` 构建逻辑中，在 time-travel filter 之前添加：

```python
# Exclude inactive trait stages from search results
filters += " AND NOT (memory_type = 'trait' AND trait_stage IN ('trend', 'candidate', 'dissolved'))"
```

此过滤条件不需要额外参数绑定，是静态条件。

## 4. 辅助表 ORM

### 4.1 TraitEvidence（`models/trait_evidence.py`）

| 字段 | 类型 | RPIV-2 需求 | 状态 |
|------|------|------------|------|
| id | UUID PK | 主键 | OK |
| trait_id | UUID | trait 引用 | OK |
| memory_id | UUID | 证据记忆引用 | OK |
| evidence_type | VARCHAR(15) | 'supporting'/'contradicting' | OK |
| quality | CHAR(1) | 'A'/'B'/'C'/'D' | OK |
| created_at | TIMESTAMPTZ | 创建时间 | OK |

**结论**：完全满足 RPIV-2 需求，无需修改。

### 4.2 ReflectionCycle（`models/reflection_cycle.py`）

| 字段 | 类型 | RPIV-2 需求 | 状态 |
|------|------|------------|------|
| trigger_type | **VARCHAR(50)** | 需要容纳 "importance_accumulated"(24字符) | **OK（已修复）** |
| trigger_value | Float | 累积重要度值 | OK |
| memories_scanned | Integer | 扫描数 | OK |
| traits_created | Integer | 新建 trait 数 | OK |
| traits_updated | Integer | 更新数（含强化） | OK |
| traits_dissolved | Integer | dissolved 数 | OK |
| status | VARCHAR(20) | 'running'/'completed'/'failed' | OK |
| error_message | Text | 错误信息 | OK |

**关键发现**：原设计文档（storage-schema-v2.md）定义 `trigger_type VARCHAR(20)`，存不下 "importance_accumulated"（24 字符）。但 **ORM 实际定义为 VARCHAR(50)**（`reflection_cycle.py:22`），已自行修正，**无风险**。

### 4.3 MemoryHistory（`models/memory_history.py`）

| 字段 | RPIV-2 需求 | 状态 |
|------|------------|------|
| event VARCHAR(20) | 需要 'modified'/'dissolved' 等事件类型 | OK |
| actor VARCHAR(50) | 'reflection' 值 | OK |
| old_content/new_content | trait 修正记录 | OK |
| old_metadata/new_metadata | 元数据变更记录 | OK |

**结论**：完全满足需求。

### 4.4 MemorySource（`models/memory_source.py`）

**结论**：完全满足需求（memory_id + session_id 复合主键 + 可选 conversation_id）。

## 5. 置信度模型数值验证

### 5.1 强化公式验证

公式：`new = old + (1 - old) * factor`

**数学证明**：
- 若 `old` 在 [0,1]，`factor` 在 [0,1]，则 `(1 - old) * factor` 在 [0,1]
- `new = old + non_negative` >= old >= 0
- `new = old + (1 - old) * factor` <= old + (1 - old) = 1
- **结论：公式保证结果恒在 [0,1] 范围内**

**模拟结果**：

| 证据级别 | factor | 20 次后 | 渐近线 |
|---------|--------|---------|-------|
| A 级 | 0.25 | 0.9968 | 1.0 |
| B 级 | 0.20 | 0.9885 | 1.0 |
| C 级 | 0.15 | 0.9612 | 1.0 |
| D 级 | 0.05 | 0.6415 | 1.0 |

**边界验证**：
- old=0, A 级 → 0.25 (在范围内)
- old=0.99, A 级 → 0.9925 (在范围内)
- old=1.0, A 级 → 1.0 (不超过 1)

### 5.2 behavior 从 0.4 经 C 级证据到 0.5

```
初始 confidence = 0.4
第 1 次 C 级(0.15): 0.4 + 0.6 * 0.15 = 0.490
第 2 次 C 级(0.15): 0.49 + 0.51 * 0.15 = 0.5665
```

**结论：需要 2 次 C 级证据**（跨 2 次不同对话的行为观察），才能从 0.4 升到 >= 0.5。这意味着一个 behavior 需要至少 3 次对话中的行为模式才能具备升级为 preference 的条件（初始 0.4 + 2 次强化），合理且保守。

### 5.3 衰减公式验证

公式：`decayed = confidence * exp(-effective_lambda * days)`

其中 `effective_lambda = base_lambda / (1 + 0.1 * reinforcement_count)`

**模拟结果**（初始 confidence = 0.7，90 天后）：

| 子类型 | 强化次数 | 有效 lambda | 90天后 confidence |
|-------|---------|------------|-----------------|
| behavior | 0 | 0.005 | 0.4463 |
| behavior | 5 | 0.0033 | 0.5186 |
| behavior | 10 | 0.0025 | 0.5590 |
| preference | 0 | 0.002 | 0.5847 |
| preference | 10 | 0.001 | 0.6398 |
| core | 0 | 0.001 | 0.6398 |
| core | 10 | 0.0005 | 0.6692 |

**分析**：
- behavior 未强化 90 天后衰减到 0.4463（低于 emerging 阈值 0.3-0.6 的上沿），会降级
- core 即使未强化 90 天也保持 0.6398，依然 established
- 间隔效应显著：behavior 强化 10 次后衰减速率减半（0.559 vs 0.446）

### 5.4 矛盾削弱验证

```
初始 confidence = 0.7
单条矛盾 (factor=0.2): 0.7 * 0.8 = 0.56
强矛盾 (factor=0.4):   0.56 * 0.6 = 0.336
```

**结论**：单条矛盾将 established(0.7) 降到 emerging(0.56)；后续强矛盾再降到 candidate 边界(0.336)，符合设计预期。

## 6. ConversationSession 状态

### 6.1 DDL 层

`last_reflected_at` 列已通过 `db.py:133` 的 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` 动态添加：

```python
"ALTER TABLE conversation_sessions ADD COLUMN IF NOT EXISTS last_reflected_at TIMESTAMPTZ"
```

### 6.2 ORM 层

**关键发现：ConversationSession ORM 模型（`models/conversation.py:65-90`）缺少 `last_reflected_at` 字段映射。**

当前 ORM 字段列表：
- id, user_id, session_id, title, summary, message_count, last_message_at, metadata_

**影响**：
- 无法通过 ORM 查询 `last_reflected_at`（需要用 raw SQL）
- 现有 `_digest_impl()` 使用 **emotion_profiles.last_reflected_at** 作为水位线（非 conversation_sessions），所以当前代码能工作
- RPIV-2 需要将水位线迁移到 conversation_sessions（按设计文档），必须先补全 ORM 字段

### 6.3 当前水位线位置

当前水位线存储在 **emotion_profiles.last_reflected_at**（`_core.py:1502`）。设计文档要求存储在 **conversation_sessions.last_reflected_at**。

**建议**：RPIV-2 实现时两步处理：
1. 在 ConversationSession ORM 中添加 `last_reflected_at` 字段
2. 新的 `reflect()` 使用 conversation_sessions.last_reflected_at
3. 保留旧的 `digest()` 兼容路径（使用 emotion_profiles），确保向后兼容

## 风险评估

### 高风险

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| **LLM 结构化输出不稳定** | reflection 主调用返回的 JSON 格式可能不符合预期 | 1) prompt 中强调 JSON schema 2) 解析层做严格校验 + fallback 3) 设置 temperature=0.1 降低随机性 |
| **水位线迁移** | 从 emotion_profiles 迁到 conversation_sessions 可能中断现有 digest | 两个水位线并行，旧 digest() 保留兼容 |

### 中风险

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| **ConversationSession ORM 缺字段** | last_reflected_at 无法通过 ORM 访问 | RPIV-2 实施前补全 ORM 映射 |
| **reflection 单次 LLM 调用 token 预算** | 大量新记忆 + 大量已有 trait 可能超出 token 限制 | 分页处理 + 限制 trait 摘要条数 |
| **scored_search SQL 复杂度增加** | 添加 trait_boost 和阶段过滤增加 SQL 复杂度 | 变更最小化（仅 2 个新 CASE 表达式 + 1 个 AND 条件） |

### 低风险

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| **辅助表字段不足** | 经审查所有辅助表字段均满足需求 | trigger_type 已为 VARCHAR(50)，不存在溢出问题 |
| **置信度模型数学正确性** | 公式已数值验证，在 [0,1] 范围内 | 代码层增加 clamp(0, 1) 作为防御 |
| **向后兼容** | 公共 API 扩展但不破坏 | reflect()/should_reflect()/get_user_traits() 均为新增方法 |
