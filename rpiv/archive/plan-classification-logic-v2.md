---
description: "功能实施计划: classification-logic-v2 (Reflection 引擎 + Trait 生命周期 + 召回改造)"
status: archived
created_at: 2026-03-01T02:45:00
updated_at: 2026-03-02T00:05:00
archived_at: 2026-03-02T00:05:00
related_files:
  - rpiv/requirements/prd-classification-logic-v2.md
---

# 功能：分类逻辑 V2 — Reflection 引擎 + Trait 生命周期 + 召回改造

以下计划应该是完整的，但在开始实施之前，验证文档和代码库模式以及任务合理性非常重要。

特别注意现有工具、类型和模型的命名。从正确的文件导入等。

## 功能描述

完全替换 neuromem SDK 的 ReflectionService，实现 9 步反思流程编排，新建 TraitEngine 管理 trait 生命周期（behavior→preference→core 升级链），改造 SearchService 的召回公式加入 trait_boost 权重，并扩展公共 API 提供 `reflect()` / `should_reflect()` / `get_user_traits()` 三个新方法。

## 用户故事

作为 AI agent 开发者
我想要系统能从多次对话中自动归纳用户特质并管理其生命周期
以便构建真正"理解用户"的 AI 应用

## 问题陈述

RPIV-1 铺好存储基座（trait 专用列、辅助表），但系统缺乏核心智能层：reflection 引擎无法生成 trait、无生命周期管理、召回未利用 trait 权重。当前 `ReflectionService.digest()` 仅生成浅层 pattern/summary 洞察。

## 解决方案陈述

1. 新建 `trait_engine.py` 封装 trait CRUD + 置信度计算 + 衰减 + 升级 + 矛盾处理
2. 完全改写 `reflection.py` 为 9 步反思流程编排器
3. 修改 `search.py` 的 `scored_search()` 加入 trait_boost 和阶段过滤
4. 扩展 `_core.py` 三个新公共 API
5. 保留现有 `digest()` 向后兼容

## 功能元数据

**功能类型**：新功能 + 增强
**估计复杂度**：高
**主要受影响的系统**：ReflectionService, SearchService, NeuroMemory facade
**依赖项**：无新增外部依赖（复用现有 LLM/Embedding provider）

---

## 上下文参考

### 相关代码库文件（实施前必读）

- `neuromem/services/reflection.py`（全文）— 原因：**完全改写**目标，需了解现有接口和 `_update_emotion_profile()` 保留部分
- `neuromem/services/search.py`（第 234-417 行）— 原因：`scored_search()` 方法，需加入 trait_boost + 阶段过滤
- `neuromem/_core.py`（第 535-600 行）— 原因：NeuroMemory 构造函数，了解 provider 注入模式
- `neuromem/_core.py`（第 811-820 行）— 原因：`_maybe_trigger_digest()`，当前触发机制
- `neuromem/_core.py`（第 982-1060 行）— 原因：`recall()` 方法，了解 search 调用路径
- `neuromem/_core.py`（第 1455-1628 行）— 原因：`digest()` / `_digest_impl()`，了解水位线机制和分页模式
- `neuromem/models/memory.py`（全文）— 原因：Memory ORM 模型，所有 trait 专用列
- `neuromem/models/trait_evidence.py`（全文）— 原因：TraitEvidence ORM
- `neuromem/models/reflection_cycle.py`（全文）— 原因：ReflectionCycle ORM
- `neuromem/models/memory_history.py`（全文）— 原因：MemoryHistory ORM
- `neuromem/models/memory_source.py`（全文）— 原因：MemorySource ORM
- `neuromem/models/conversation.py`（第 65-91 行）— 原因：ConversationSession ORM，需补充 `last_reflected_at`
- `neuromem/providers/llm.py`（全文）— 原因：LLMProvider 抽象基类，`chat()` 方法签名
- `neuromem/db.py`（第 120-140 行）— 原因：迁移逻辑中 `last_reflected_at` 的 DDL 添加

### 要创建的新文件

- `neuromem/services/trait_engine.py` — Trait 生命周期管理引擎
- `tests/test_trait_engine.py` — TraitEngine 单元测试
- `tests/test_reflection_v2.py` — 新 ReflectionService 测试
- `tests/test_recall_trait_boost.py` — 召回 trait_boost 测试
- `tests/test_reflect_api.py` — 公共 API reflect()/should_reflect()/get_user_traits() 测试

### 要遵循的模式

**Service 构造模式**：

```python
# 所有 Service 接收 db session + provider
class TraitEngine:
    def __init__(self, db: AsyncSession, embedding: EmbeddingProvider):
        self.db = db
        self._embedding = embedding
```

**Facade → Service 调用模式**（`_core.py` 标准模式）：

```python
async with self._db.session() as session:
    svc = SomeService(session, self._embedding, self._llm)
    result = await svc.some_method(user_id, ...)
```

**JSON 解析模式**（复用现有 `_parse_insight_result` 模式）：

```python
text = result_text.strip()
if "```json" in text:
    start = text.find("```json") + 7
    end = text.find("```", start)
    text = text[start:end].strip()
result = json.loads(text)
```

**日志模式**：

```python
logger = logging.getLogger(__name__)
logger.info("Reflect[%s]: ...", user_id)
logger.error("...: %s", e, exc_info=True)
```

**命名约定**：snake_case 方法和变量名、PascalCase 类名

---

## 实施计划

### 阶段 1：基础设施补全

补全 RPIV-1 遗留的 ORM 缺失，为反思引擎铺路。

**任务**：任务 1

### 阶段 2：TraitEngine 核心

新建 `trait_engine.py`，实现 trait 生命周期的所有操作。

**任务**：任务 2-3

### 阶段 3：Reflection 引擎改写

完全改写 `reflection.py`，实现 9 步反思流程。

**任务**：任务 4-5

### 阶段 4：召回改造 + 公共 API

修改 `search.py` 加入 trait_boost，扩展 `_core.py` 三个新公共 API。

**任务**：任务 6-8

---

## 逐步任务

### 任务 1：UPDATE `neuromem/models/conversation.py` — 补充 last_reflected_at ORM 字段

- **IMPLEMENT**：在 ConversationSession 类（第 65-91 行）添加 `last_reflected_at` mapped_column
- **PATTERN**：参考 `neuromem/models/conversation.py:83-85`（`last_message_at` 字段的定义模式）
- **代码**：
  ```python
  # 在 metadata_ 字段之后、__table_args__ 之前添加
  last_reflected_at: Mapped[Optional[datetime]] = mapped_column(
      DateTime(timezone=True), nullable=True
  )
  ```
- **GOTCHA**：DDL 层已通过 `db.py:133` 的 ALTER TABLE 动态添加此列，此处仅补全 ORM 映射
- **VALIDATE**：`cd /d/CODE/NeuroMem && uv run python -c "from neuromem.models.conversation import ConversationSession; print('OK')" `

### 任务 2：CREATE `neuromem/services/trait_engine.py` — Trait 生命周期管理引擎

- **IMPLEMENT**：新建 TraitEngine 类，包含以下方法：

**构造函数**：
```python
class TraitEngine:
    def __init__(self, db: AsyncSession, embedding: EmbeddingProvider):
        self.db = db
        self._embedding = embedding
```

**方法清单**（按调用顺序）：

1. `async def create_trend(self, user_id, content, evidence_ids, window_days, context, cycle_id) -> Memory`
   - 创建 trend 阶段 trait
   - 生成 embedding 向量
   - 计算 content_hash 去重检查（hash 命中 → 强化而非新建；向量相似度 > 0.95 → 强化）
   - 填充字段：memory_type="trait", trait_stage="trend", trait_subtype="behavior", trait_window_start=NOW(), trait_window_end=NOW()+window_days, trait_context=context, trait_derived_from="reflection", importance=0.5
   - 写入 trait_evidence 表（每条 evidence_id → supporting, quality="D"）
   - 返回创建的 Memory 对象

2. `async def create_behavior(self, user_id, content, evidence_ids, confidence, context, cycle_id) -> Memory`
   - 创建 candidate 阶段 behavior trait
   - 去重检查（同 create_trend）
   - 填充字段：trait_stage="candidate", trait_subtype="behavior", trait_confidence=clamp(confidence, 0.3, 0.5), trait_context=context, trait_first_observed=最早证据时间, trait_derived_from="reflection"
   - 写入 trait_evidence 表

3. `async def reinforce_trait(self, trait_id, evidence_ids, quality_grade, cycle_id) -> None`
   - 计算新 confidence：`old + (1 - old) * factor`（factor 由 quality_grade 映射：A=0.25, B=0.20, C=0.15, D=0.05）
   - 更新 trait_reinforcement_count += len(evidence_ids)
   - 更新 trait_last_reinforced = NOW()
   - 更新 trait_stage（基于新 confidence 的阶段流转）
   - 写入 trait_evidence 表（每条 → supporting）
   - clamp confidence 在 [0, 1]

4. `async def apply_contradiction(self, trait_id, evidence_ids, cycle_id) -> dict`
   - 更新 trait_contradiction_count += len(evidence_ids)
   - 计算 confidence 削弱：`old * (1 - 0.2)`（单条）或 `old * (1 - 0.4)`（多条，len > 1）
   - 写入 trait_evidence 表（每条 → contradicting, quality="C"）
   - 检查矛盾比例：`contradiction_count / (reinforcement_count + contradiction_count) > 0.3 and contradiction_count >= 2`
   - 返回 `{"needs_special_reflection": bool, "trait_id": str, "new_confidence": float}`

5. `async def try_upgrade(self, from_trait_ids, new_content, new_subtype, reasoning, cycle_id) -> Memory | None`
   - 代码验证门槛：
     - behavior→preference：各源 behavior confidence ≥ 0.5
     - preference→core：各源 preference confidence ≥ 0.6
   - 创建新 trait：trait_subtype=new_subtype, trait_stage="emerging", confidence=MAX(子 trait) + 0.1
   - 设置子 trait 的 trait_parent_id 指向新 trait
   - 继承子 trait 的全部证据（复制 trait_evidence 行）
   - 循环引用检测

6. `async def promote_trends(self, user_id) -> int`
   - 查找所有可升级的 trend：window 内且 reinforcement_count >= 2
   - 升级为 candidate：trait_stage="candidate", trait_confidence=0.3, 清空 window
   - 返回升级数量

7. `async def expire_trends(self, user_id) -> int`
   - 查找所有过期 trend：NOW() > trait_window_end AND reinforcement_count < 2
   - 标记 dissolved：trait_stage="dissolved", expired_at=NOW()
   - 返回过期数量

8. `async def apply_decay(self, user_id) -> int`
   - 查找用户所有非 trend、非 dissolved 的 trait
   - 对每个 trait 计算衰减后 confidence
   - 公式：`confidence * exp(-effective_lambda * days_since_last_reinforced)`
   - effective_lambda = base_lambda / (1 + 0.1 * reinforcement_count)
   - base_lambda: behavior=0.005, preference=0.002, core=0.001
   - 衰减后 < 0.1 → dissolved
   - 更新阶段（基于新 confidence）
   - 返回 dissolved 数量

9. `async def resolve_contradiction(self, trait_id, llm, cycle_id) -> dict`
   - 加载 trait + 全部 supporting/contradicting 证据
   - 构建专项反思 prompt（完整 prompt 见下文）
   - 调用 LLM，解析结果
   - action="modify" → 更新 trait content + 调整 confidence + 写入 memory_history
   - action="dissolve" → trait_stage="dissolved", expired_at=NOW() + 写入 memory_history
   - 返回 `{"action": str, "trait_id": str}`

10. `_update_stage(self, confidence) -> str`（内部方法）
    - < 0.1 → "dissolved"
    - < 0.3 → "candidate"
    - < 0.6 → "emerging"
    - < 0.85 → "established"
    - >= 0.85 → "core"

11. `_find_similar_trait(self, user_id, content, content_hash) -> Memory | None`（内部方法）
    - 先查 content_hash 完全匹配
    - 再查向量相似度 > 0.95
    - 用于去重

**矛盾专项反思 Prompt**（`resolve_contradiction` 使用）：

```python
CONTRADICTION_PROMPT = """你是一个用户特质矛盾分析系统。请分析以下特质的矛盾情况并做出决策。

## 待分析特质
- 内容: {content}
- 子类型: {subtype}
- 当前置信度: {confidence:.2f}
- 情境: {context}

## 支持证据（{supporting_count} 条）
{supporting_list}

## 矛盾证据（{contradicting_count} 条）
{contradicting_list}

## 请分析并做出决策

决策选项：
1. **modify**: 原判断需要修正，更新特质描述。适用于：证据整体支持该倾向但描述不够精确
2. **dissolve**: 证据太弱或矛盾太强，该特质不成立。适用于：支持证据和矛盾证据势均力敌或矛盾占优

只返回 JSON，不要其他内容：
```json
{{
  "action": "modify" 或 "dissolve",
  "new_content": "修正后的特质描述（仅 modify 时需要）",
  "reasoning": "决策理由"
}}
```"""
```

- **IMPORTS**：
  ```python
  from __future__ import annotations
  import hashlib
  import json
  import logging
  import math
  from datetime import datetime, timedelta, timezone
  from typing import Optional
  from sqlalchemy import select, text
  from sqlalchemy.ext.asyncio import AsyncSession
  from neuromem.models.memory import Memory
  from neuromem.models.trait_evidence import TraitEvidence
  from neuromem.models.memory_history import MemoryHistory
  from neuromem.providers.embedding import EmbeddingProvider
  from neuromem.providers.llm import LLMProvider
  ```
- **GOTCHA**：
  - confidence 计算结果必须 `max(0.0, min(1.0, value))` clamp
  - trait_stage 只能向上流转或降级到 dissolved，不能跳级
  - `create_trend` 和 `create_behavior` 中 `evidence_ids` 可能包含不存在的 UUID（LLM 可能幻觉），需做 EXISTS 校验
  - 向量相似度去重需要计算新 content 的 embedding，这意味着即使重复也会消耗一次 embedding API 调用
- **VALIDATE**：`cd /d/CODE/NeuroMem && uv run python -c "from neuromem.services.trait_engine import TraitEngine; print('OK')"`

### 任务 3：UPDATE `neuromem/services/__init__.py` — 导出 TraitEngine（如果存在该文件）

- **IMPLEMENT**：检查 `neuromem/services/__init__.py` 是否存在。如果存在，添加 TraitEngine 导出。如果不存在，跳过（现有 Service 不通过 __init__ 导出，而是在使用处直接 import）
- **PATTERN**：检查 `neuromem/services/` 目录下的导出模式
- **VALIDATE**：`cd /d/CODE/NeuroMem && uv run python -c "from neuromem.services.trait_engine import TraitEngine; print('OK')"`

### 任务 4：UPDATE `neuromem/services/reflection.py` — 完全改写为 9 步反思引擎

- **IMPLEMENT**：改写 `ReflectionService` 类，保留 `_update_emotion_profile()` 及其辅助方法，替换其余逻辑

**新的 ReflectionService 结构**：

```python
class ReflectionService:
    def __init__(self, db: AsyncSession, embedding: EmbeddingProvider, llm: LLMProvider):
        self.db = db
        self._embedding = embedding
        self._llm = llm
        self._trait_engine = TraitEngine(db, embedding)

    async def should_reflect(self, user_id: str) -> tuple[bool, str | None, float | None]:
        """检查是否满足反思触发条件。
        返回: (should_trigger, trigger_type, trigger_value)
        """
        # 1. 查询 conversation_sessions.last_reflected_at
        # 2. NULL → 首次反思，返回 (True, "first_time", None)
        # 3. 计算重要度累积：SUM(importance) WHERE created_at > last_reflected_at AND memory_type IN ('fact','episodic')
        # 4. 累积 >= 30 → (True, "importance_accumulated", accumulated_value)
        # 5. NOW() - last_reflected_at >= 24h → (True, "scheduled", None)
        # 6. 幂等检查：如果 last_reflected_at 在 60s 内 → (False, None, None)
        # 7. 无新记忆 → (False, None, None)

    async def reflect(self, user_id: str, force: bool = False, session_ended: bool = False) -> dict:
        """执行 9 步反思流程。"""
        # 0. 触发检查（除非 force=True 或 session_ended=True）
        # 1. 创建 reflection_cycle 记录（status="running"）
        # 2. 执行 _run_reflection_steps()
        # 3. 更新 reflection_cycle 记录（status="completed"/"failed"）
        # 4. 返回结果

    async def _run_reflection_steps(self, user_id, trigger_type, trigger_value, cycle_id) -> dict:
        """9 步反思流程核心。"""
        stats = {"memories_scanned": 0, "traits_created": 0, "traits_updated": 0, "traits_dissolved": 0}

        # Step 1: 扫描新记忆
        new_memories = await self._scan_new_memories(user_id)
        stats["memories_scanned"] = len(new_memories)

        # Step 3 (先于 LLM): trend 过期/升级（纯代码）
        expired = await self._trait_engine.expire_trends(user_id)
        promoted = await self._trait_engine.promote_trends(user_id)
        stats["traits_dissolved"] += expired
        stats["traits_updated"] += promoted

        if not new_memories:
            # 无新记忆 → 仅执行 Step 8 衰减
            dissolved = await self._trait_engine.apply_decay(user_id)
            stats["traits_dissolved"] += dissolved
            await self._update_watermark(user_id)
            return stats

        # Step 2: LLM 主调用
        existing_traits = await self._load_existing_traits(user_id)
        llm_result = await self._call_reflection_llm(new_memories, existing_traits)

        if llm_result is None:
            # LLM 失败 → 仅执行衰减，不更新水位线
            dissolved = await self._trait_engine.apply_decay(user_id)
            stats["traits_dissolved"] += dissolved
            return stats

        # Step 4: 处理 new_trends + new_behaviors
        for trend in llm_result.get("new_trends", []):
            await self._trait_engine.create_trend(
                user_id=user_id,
                content=trend["content"],
                evidence_ids=trend.get("evidence_ids", []),
                window_days=trend.get("window_days", 30),
                context=trend.get("context", "general"),
                cycle_id=cycle_id,
            )
            stats["traits_created"] += 1

        for behavior in llm_result.get("new_behaviors", []):
            await self._trait_engine.create_behavior(
                user_id=user_id,
                content=behavior["content"],
                evidence_ids=behavior.get("evidence_ids", []),
                confidence=behavior.get("confidence", 0.4),
                context=behavior.get("context", "general"),
                cycle_id=cycle_id,
            )
            stats["traits_created"] += 1

        # Step 5: 处理 reinforcements
        for reinforcement in llm_result.get("reinforcements", []):
            await self._trait_engine.reinforce_trait(
                trait_id=reinforcement["trait_id"],
                evidence_ids=reinforcement.get("new_evidence_ids", []),
                quality_grade=reinforcement.get("quality_grade", "C"),
                cycle_id=cycle_id,
            )
            stats["traits_updated"] += 1

        # Step 6: 处理 upgrades
        for upgrade in llm_result.get("upgrades", []):
            result = await self._trait_engine.try_upgrade(
                from_trait_ids=upgrade["from_trait_ids"],
                new_content=upgrade["new_content"],
                new_subtype=upgrade["new_subtype"],
                reasoning=upgrade.get("reasoning", ""),
                cycle_id=cycle_id,
            )
            if result:
                stats["traits_created"] += 1

        # Step 7: 处理 contradictions + 可能的专项反思
        for contradiction in llm_result.get("contradictions", []):
            result = await self._trait_engine.apply_contradiction(
                trait_id=contradiction["trait_id"],
                evidence_ids=contradiction.get("contradicting_evidence_ids", []),
                cycle_id=cycle_id,
            )
            if result.get("needs_special_reflection"):
                resolved = await self._trait_engine.resolve_contradiction(
                    trait_id=contradiction["trait_id"],
                    llm=self._llm,
                    cycle_id=cycle_id,
                )
                if resolved.get("action") == "dissolve":
                    stats["traits_dissolved"] += 1
                else:
                    stats["traits_updated"] += 1

        # Step 8: 时间衰减
        dissolved = await self._trait_engine.apply_decay(user_id)
        stats["traits_dissolved"] += dissolved

        # Step 9: 更新水位线
        await self._update_watermark(user_id)

        return stats

    async def _scan_new_memories(self, user_id) -> list[dict]:
        """扫描 last_reflected_at 之后的新 fact/episodic。"""
        # 查询 conversation_sessions.last_reflected_at
        # SELECT id, content, memory_type, importance, metadata, created_at
        # FROM memories WHERE user_id=:uid AND memory_type IN ('fact','episodic')
        # AND created_at > :watermark ORDER BY created_at ASC

    async def _load_existing_traits(self, user_id) -> list[dict]:
        """加载已有 trait 摘要供 LLM 参考。"""
        # SELECT id, content, trait_stage, trait_subtype, trait_confidence, trait_context
        # FROM memories WHERE user_id=:uid AND memory_type='trait'
        # AND trait_stage NOT IN ('dissolved')
        # ORDER BY trait_confidence DESC NULLS LAST LIMIT 50

    async def _call_reflection_llm(self, new_memories, existing_traits) -> dict | None:
        """调用 LLM 执行主反思分析。返回 None 表示失败。"""
        prompt = self._build_reflection_prompt(new_memories, existing_traits)
        try:
            result_text = await self._llm.chat(
                messages=[
                    {"role": "system", "content": "你是一个用户特质分析引擎。根据用户的新增记忆和已有特质，执行结构化分析。只返回 JSON。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=4096,
            )
            return self._parse_reflection_result(result_text)
        except Exception as e:
            logger.error("Reflection LLM call failed: %s", e, exc_info=True)
            return None

    def _build_reflection_prompt(self, new_memories, existing_traits) -> str:
        """构建反思主调用 prompt。"""
        # 完整 prompt 文本见下方

    def _parse_reflection_result(self, result_text) -> dict | None:
        """解析 LLM 返回的 JSON。"""
        # 复用现有 ```json 提取模式
        # 返回 None 表示解析失败

    async def _update_watermark(self, user_id) -> None:
        """更新 conversation_sessions.last_reflected_at。"""
        # UPDATE conversation_sessions SET last_reflected_at = NOW()
        # WHERE user_id = :uid
        # 如果用户没有 session 记录，使用 INSERT ON CONFLICT

    # ============== 保留的方法（不修改） ==============
    # _update_emotion_profile() — 完整保留
    # _build_emotion_summary_prompt() — 完整保留
    # _parse_emotion_summary() — 完整保留
    # _get_current_period() — 完整保留
```

**反思主调用完整 Prompt**（`_build_reflection_prompt` 使用）：

```python
REFLECTION_PROMPT_TEMPLATE = """## 已有特质
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
- 与已有特质内容去重：如果某个模式已被已有特质覆盖，归入 reinforcements 而非 new_behaviors
- 为每条 behavior 推断情境标签(context)
- 初始置信度建议：通常 0.4，跨情境一致的可以给 0.5

### 3. 已有特质强化 (reinforcements)
- 检查新增记忆中是否有支持已有特质的证据
- 标注证据质量等级：
  - A: 跨情境行为一致性（同一模式在 work+personal 等不同情境中出现）
  - B: 用户显式自我陈述（"我是个急性子"）
  - C: 跨对话行为（不同对话中观测到相同模式）
  - D: 同对话内信号或隐式推断

### 4. 矛盾检测 (contradictions)
- 检查新增记忆中是否有**与已有特质矛盾**的证据
- 仅报告明确矛盾，不报告细微差异

### 5. 升级建议 (upgrades)
- 检查已有 behavior 是否有 ≥2 个指向同一倾向 → 建议升级为 preference
- 检查已有 preference 是否有 ≥2 个指向同一人格维度 → 建议升级为 core
- 注意：升级建议由代码层验证 confidence 门槛后执行

如果没有发现任何模式、强化或矛盾，返回所有数组为空的 JSON。

只返回 JSON，不要其他内容：
```json
{{
  "new_trends": [
    {{
      "content": "趋势描述（具体、有细节）",
      "evidence_ids": ["记忆ID1", "记忆ID2"],
      "window_days": 30,
      "context": "work"
    }}
  ],
  "new_behaviors": [
    {{
      "content": "行为模式描述",
      "evidence_ids": ["记忆ID1", "记忆ID2", "记忆ID3"],
      "confidence": 0.4,
      "context": "work"
    }}
  ],
  "reinforcements": [
    {{
      "trait_id": "已有特质的UUID",
      "new_evidence_ids": ["记忆ID"],
      "quality_grade": "C"
    }}
  ],
  "contradictions": [
    {{
      "trait_id": "已有特质的UUID",
      "contradicting_evidence_ids": ["记忆ID"],
      "description": "矛盾描述"
    }}
  ],
  "upgrades": [
    {{
      "from_trait_ids": ["behavior-id-1", "behavior-id-2"],
      "new_content": "升级后的描述",
      "new_subtype": "preference",
      "reasoning": "升级理由"
    }}
  ]
}}
```"""
```

- **IMPORTS**：新增 `from neuromem.services.trait_engine import TraitEngine`、`from neuromem.models.reflection_cycle import ReflectionCycle`
- **GOTCHA**：
  - 必须保留 `_update_emotion_profile` 及其 3 个辅助方法（`_build_emotion_summary_prompt`, `_parse_emotion_summary`, `_get_current_period`）
  - 新记忆列表中的 `id` 是字符串格式的 UUID，LLM 会在 evidence_ids 中引用它们
  - 水位线迁移：新 reflect() 使用 conversation_sessions.last_reflected_at，旧 digest() 保持使用 emotion_profiles.last_reflected_at
  - LLM 返回的 trait_id/evidence_ids 可能包含不存在的 UUID，TraitEngine 需做 EXISTS 校验
  - 新记忆列表最大限制 200 条（超过时按 importance 排序取 TOP 200），避免 token 溢出
  - existing_traits 最大限制 50 条
- **VALIDATE**：`cd /d/CODE/NeuroMem && uv run python -c "from neuromem.services.reflection import ReflectionService; print('OK')"`

### 任务 5：UPDATE `neuromem/services/reflection.py` — 保留 digest() 兼容入口

- **IMPLEMENT**：在改写后的 ReflectionService 中保留 `digest()` 方法作为向后兼容入口
- **代码**：
  ```python
  async def digest(self, user_id, recent_memories, existing_insights=None):
      """向后兼容入口（保留旧 digest 接口）。
      注意：新代码应使用 reflect() 方法。
      """
      if not recent_memories:
          return {"insights": [], "emotion_profile": None}

      # 调用情绪画像更新（保留原有功能）
      emotion_profile = await self._update_emotion_profile(user_id, recent_memories)

      return {
          "insights": [],  # 旧 insight 生成已被 reflect() 替代
          "emotion_profile": emotion_profile,
      }
  ```
- **GOTCHA**：`_core.py` 的 `_digest_impl()` 仍然调用 `svc.digest()`，此兼容入口确保 `NeuroMemory.digest()` 不会报错。emotion_profile 更新逻辑保留。
- **VALIDATE**：`cd /d/CODE/NeuroMem && uv run python -c "from neuromem.services.reflection import ReflectionService; print(hasattr(ReflectionService, 'digest'))"`

### 任务 6：UPDATE `neuromem/services/search.py` — 添加 trait_boost + 阶段过滤

- **IMPLEMENT**：修改 `scored_search()` 方法（第 234-417 行），在两个位置添加改动：

**改动 1**：在 filters 构建逻辑中（约第 312 行 time-travel filter 之前），添加阶段过滤：

```python
# Exclude inactive trait stages from search results
filters += " AND NOT (memory_type = 'trait' AND trait_stage IN ('trend', 'candidate', 'dissolved'))"
```

**改动 2**：在 SQL final score 计算中（约第 378-385 行），添加 trait_boost 项。修改 `score` 计算公式：

原始：
```sql
LEAST(vector_score + CASE WHEN bm25_score > 0 THEN 0.05 ELSE 0 END, 1.0)
* (1.0
   + 0.15 * EXP(...)
   + 0.15 * COALESCE(...)
) AS score
```

修改为：
```sql
LEAST(vector_score + CASE WHEN bm25_score > 0 THEN 0.05 ELSE 0 END, 1.0)
* (1.0
   + 0.15 * EXP(...)
   + 0.15 * COALESCE(...)
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
) AS score
```

**改动 3**：在 `vector_ranked` CTE 的 SELECT 列表中添加 `trait_stage` 列（约第 346 行）：

```sql
SELECT id, content, memory_type, metadata, created_at, extracted_timestamp,
       access_count, last_accessed_at, trait_stage,
       ...
```

同时在 hybrid CTE 和最终 SELECT 中也传递 `trait_stage`。

- **PATTERN**：参考 `search.py:378-385`（现有 score 计算）
- **GOTCHA**：
  - `trait_stage` 可能为 NULL（非 trait 类型的记忆），CASE WHEN 已处理
  - 需要确保 `hybrid` CTE 也传递 `trait_stage` 列
  - 搜索结果 dict 中可选添加 `trait_stage` 和 `trait_boost` 字段
- **VALIDATE**：`cd /d/CODE/NeuroMem && uv run pytest tests/test_search.py -v --timeout=60 2>/dev/null ; echo "Exit: $?"`

### 任务 7：UPDATE `neuromem/_core.py` — 添加三个新公共 API

- **IMPLEMENT**：在 NeuroMemory 类中添加三个新方法。位置：在 `digest()` 方法之后（约第 1630 行之前）添加。

**方法 1：should_reflect()**

```python
async def should_reflect(self, user_id: str) -> bool:
    """检查用户是否满足反思触发条件。

    三种触发条件（任一满足即返回 True）：
    - 重要度累积 >= 30
    - 距上次反思 >= 24h
    - 首次反思（last_reflected_at 为 NULL）
    """
    from neuromem.services.reflection import ReflectionService

    async with self._db.session() as session:
        svc = ReflectionService(session, self._embedding, self._llm)
        should, _, _ = await svc.should_reflect(user_id)
        return should
```

**方法 2：reflect()**

```python
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
            "triggered": bool,
            "trigger_type": str | None,
            "memories_scanned": int,
            "traits_created": int,
            "traits_updated": int,
            "traits_dissolved": int,
            "cycle_id": str | None,
        }
    """
    from neuromem.services.reflection import ReflectionService

    async with self._db.session() as session:
        svc = ReflectionService(session, self._embedding, self._llm)
        return await svc.reflect(user_id, force=force, session_ended=session_ended)
```

**方法 3：get_user_traits()**

```python
async def get_user_traits(
    self,
    user_id: str,
    min_stage: str = "emerging",
    subtype: str | None = None,
    context: str | None = None,
) -> list[dict]:
    """获取用户活跃特质列表。

    Args:
        user_id: 用户 ID
        min_stage: 最低阶段过滤（默认 "emerging"）
        subtype: 按子类过滤 (behavior/preference/core)
        context: 按情境过滤 (work/personal/social/learning/general)

    Returns:
        按 stage 降序 + confidence 降序排列的 trait dict 列表
    """
    from sqlalchemy import text as sql_text

    stage_order = {
        "trend": 5, "candidate": 4, "emerging": 3,
        "established": 2, "core": 1,
    }
    min_stage_val = stage_order.get(min_stage, 3)
    allowed_stages = [s for s, v in stage_order.items() if v <= min_stage_val and s != "dissolved"]

    if not allowed_stages:
        return []

    async with self._db.session() as session:
        # Build dynamic SQL
        stage_placeholders = ", ".join(f":stage_{i}" for i in range(len(allowed_stages)))
        params = {"uid": user_id}
        for i, s in enumerate(allowed_stages):
            params[f"stage_{i}"] = s

        where = f"user_id = :uid AND memory_type = 'trait' AND trait_stage IN ({stage_placeholders})"

        if subtype:
            where += " AND trait_subtype = :subtype"
            params["subtype"] = subtype

        if context:
            where += " AND trait_context = :context"
            params["context"] = context

        sql = sql_text(f"""
            SELECT id, content, trait_subtype, trait_stage, trait_confidence,
                   trait_context, trait_reinforcement_count, trait_contradiction_count,
                   trait_first_observed, trait_last_reinforced, created_at
            FROM memories
            WHERE {where}
            ORDER BY
                CASE trait_stage
                    WHEN 'core' THEN 1
                    WHEN 'established' THEN 2
                    WHEN 'emerging' THEN 3
                    WHEN 'candidate' THEN 4
                    WHEN 'trend' THEN 5
                END,
                trait_confidence DESC NULLS LAST
        """)

        result = await session.execute(sql, params)
        rows = result.fetchall()

        return [
            {
                "id": str(row.id),
                "content": row.content,
                "trait_subtype": row.trait_subtype,
                "trait_stage": row.trait_stage,
                "trait_confidence": row.trait_confidence,
                "trait_context": row.trait_context,
                "trait_reinforcement_count": row.trait_reinforcement_count,
                "trait_contradiction_count": row.trait_contradiction_count,
                "trait_first_observed": row.trait_first_observed,
                "trait_last_reinforced": row.trait_last_reinforced,
                "created_at": row.created_at,
            }
            for row in rows
        ]
```

- **PATTERN**：参考 `_core.py:1455-1487`（`digest()` 方法的 facade → service 调用模式）
- **GOTCHA**：
  - `reflect()` 使用独立的 session（与 digest 模式一致，每次操作开启独立 session）
  - `get_user_traits()` 是纯查询方法，不需要 LLM/Embedding provider
  - 不要修改现有 `digest()` 方法的实现
- **VALIDATE**：`cd /d/CODE/NeuroMem && uv run python -c "from neuromem._core import NeuroMemory; print(hasattr(NeuroMemory, 'reflect'), hasattr(NeuroMemory, 'should_reflect'), hasattr(NeuroMemory, 'get_user_traits'))"`

### 任务 8：UPDATE `neuromem/_core.py` — 更新 `_maybe_trigger_digest` 增强触发逻辑

- **IMPLEMENT**：增强 `_maybe_trigger_digest()`（第 811-820 行），在现有计数器触发之外，额外调用 `reflect(session_ended=True)` 的逻辑。但为保持最小改动，仅在 `_do_extraction` 结束后**并行调用** reflect（如果满足条件）。

  考虑到 MVP 的简洁性，此任务可选实现。核心触发路径是用户显式调用 `reflect()` 或 `should_reflect()` + `reflect()`。自动触发可延后。

- **PATTERN**：参考 `_core.py:811-820`
- **GOTCHA**：保持 `digest()` 现有自动触发不变，`reflect()` 的自动触发可在后续版本中集成
- **VALIDATE**：`cd /d/CODE/NeuroMem && uv run pytest tests/ -m "not slow" --timeout=60 -x -q 2>/dev/null | tail -5`

---

## 测试策略

### 单元测试

**`tests/test_trait_engine.py`**（约 25-30 个测试）：

- `test_create_trend` — 创建 trend trait + 字段验证
- `test_create_trend_dedup_hash` — content_hash 去重
- `test_create_trend_dedup_vector` — 向量相似度去重
- `test_create_behavior` — 创建 behavior trait + confidence clamp
- `test_reinforce_trait_grade_a/b/c/d` — 四个等级的强化计算
- `test_reinforce_trait_stage_transition` — 强化后阶段流转
- `test_apply_contradiction_single` — 单条矛盾削弱
- `test_apply_contradiction_multiple` — 多条矛盾削弱
- `test_contradiction_threshold` — 矛盾比例检查
- `test_try_upgrade_behavior_to_preference` — 升级链
- `test_try_upgrade_insufficient_confidence` — 升级门槛不满足
- `test_try_upgrade_preference_to_core` — preference→core
- `test_promote_trends` — trend→candidate 升级
- `test_expire_trends` — trend 过期清除
- `test_apply_decay_behavior` — behavior 衰减
- `test_apply_decay_core` — core 慢衰减
- `test_apply_decay_dissolved` — 衰减到 dissolved
- `test_apply_decay_interval_effect` — 间隔效应验证
- `test_resolve_contradiction_modify` — 专项反思修正
- `test_resolve_contradiction_dissolve` — 专项反思废弃
- `test_confidence_clamp` — 边界值 clamp

**`tests/test_reflection_v2.py`**（约 15-20 个测试）：

- `test_should_reflect_first_time` — 首次反思触发
- `test_should_reflect_importance` — 重要度累积触发
- `test_should_reflect_scheduled` — 定时触发
- `test_should_reflect_no_new_memories` — 无新记忆不触发
- `test_should_reflect_idempotent` — 幂等检查
- `test_reflect_force` — 强制执行
- `test_reflect_session_ended` — 会话结束触发
- `test_reflect_full_pipeline` — 9 步完整流程（mock LLM）
- `test_reflect_llm_failure` — LLM 失败降级
- `test_reflect_json_parse_error` — JSON 解析失败降级
- `test_reflect_empty_memories` — 空记忆仅衰减
- `test_reflect_creates_cycle_record` — reflection_cycles 记录
- `test_reflect_updates_watermark` — 水位线更新
- `test_digest_backward_compat` — digest() 向后兼容
- `test_emotion_profile_preserved` — 情绪画像保留

**`tests/test_recall_trait_boost.py`**（约 8-10 个测试）：

- `test_search_excludes_trend` — trend 不参与召回
- `test_search_excludes_candidate` — candidate 不参与召回
- `test_search_excludes_dissolved` — dissolved 不参与召回
- `test_search_includes_emerging` — emerging 参与
- `test_search_boost_core` — core 获得 0.25 boost
- `test_search_boost_established` — established 获得 0.15 boost
- `test_search_boost_emerging` — emerging 获得 0.05 boost
- `test_search_null_stage` — trait_stage NULL 不报错
- `test_search_non_trait_no_boost` — fact 类型无 boost

**`tests/test_reflect_api.py`**（约 5-8 个测试）：

- `test_get_user_traits_basic` — 基本查询
- `test_get_user_traits_min_stage` — min_stage 过滤
- `test_get_user_traits_subtype_filter` — subtype 过滤
- `test_get_user_traits_context_filter` — context 过滤
- `test_get_user_traits_ordering` — 排序验证
- `test_get_user_traits_empty` — 无 trait 返回空列表
- `test_should_reflect_api` — 公共 API 调用
- `test_reflect_api` — 公共 API 调用

### 集成测试

- 端到端：ingest 多条消息 → reflect → recall 验证 trait 出现在结果中
- 回归：运行全部 353 个现有测试

### 边缘情况

- LLM 返回空 JSON `{}`
- LLM 返回不存在的 trait_id / evidence_id
- 并发调用 reflect() 的幂等性
- confidence 边界值（0.0, 1.0, exactly 0.3, 0.6, 0.85）
- trait_stage 为 NULL 的旧数据兼容
- 用户无 conversation_session 记录

---

## 验证命令

### 级别 1：语法和导入

```bash
cd /d/CODE/NeuroMem && uv run python -c "
from neuromem.services.trait_engine import TraitEngine
from neuromem.services.reflection import ReflectionService
from neuromem._core import NeuroMemory
print('All imports OK')
print('reflect:', hasattr(NeuroMemory, 'reflect'))
print('should_reflect:', hasattr(NeuroMemory, 'should_reflect'))
print('get_user_traits:', hasattr(NeuroMemory, 'get_user_traits'))
"
```

### 级别 2：单元测试

```bash
cd /d/CODE/NeuroMem && uv run pytest tests/test_trait_engine.py -v --timeout=60
cd /d/CODE/NeuroMem && uv run pytest tests/test_reflection_v2.py -v --timeout=60
cd /d/CODE/NeuroMem && uv run pytest tests/test_recall_trait_boost.py -v --timeout=60
cd /d/CODE/NeuroMem && uv run pytest tests/test_reflect_api.py -v --timeout=60
```

### 级别 3：回归测试

```bash
cd /d/CODE/NeuroMem && uv run pytest tests/ -m "not slow" --timeout=60 -x -q
```

### 级别 4：完整测试

```bash
cd /d/CODE/NeuroMem && uv run pytest tests/ --timeout=120 -q
```

---

## 验收标准

- [ ] 8 个核心场景全部实现
- [ ] 所有现有 353 测试通过
- [ ] reflect() 能从 fact/episodic 生成 trait（trend + behavior）
- [ ] trait 升级链完整（behavior→preference→core）
- [ ] 置信度模型正确（强化/削弱/衰减/阶段流转）
- [ ] 矛盾检测和专项反思正确触发
- [ ] 召回 trait_boost 按阶段正确加成
- [ ] get_user_traits() 返回正确排序的列表
- [ ] digest() 向后兼容
- [ ] ConversationSession ORM 补充 last_reflected_at
- [ ] 新增测试 ≥ 50 个
- [ ] 代码遵循项目约定（logger、类型提示、async/await）

---

## 完成检查清单

- [ ] 任务 1-8 按顺序完成
- [ ] 每个任务验证命令通过
- [ ] 所有验证命令成功执行
- [ ] 完整测试套件通过
- [ ] 无导入错误或类型检查错误
- [ ] 所有验收标准均满足

---

## 备注

### 文件变更范围估计

| 文件 | 变更类型 | 估计行数 | 复杂度 |
|------|---------|---------|--------|
| `neuromem/services/trait_engine.py` | 新建 | 400-500 | 高 |
| `neuromem/services/reflection.py` | 完全改写 | 350-450 | 高 |
| `neuromem/services/search.py` | 修改 | +30 | 低 |
| `neuromem/_core.py` | 扩展 | +120 | 中 |
| `neuromem/models/conversation.py` | 小修改 | +3 | 低 |
| 测试文件（4 个） | 新建 | 500-700 | 中 |
| **总计** | | ~1400-1800 | |

### 建议 dev agent 数量

建议使用 **1 个 dev agent** 按顺序执行任务 1-8。原因：
- 任务之间有强依赖关系（trait_engine → reflection → _core）
- 文件之间有交叉引用（reflection.py import trait_engine）
- 同一文件（_core.py）在多个任务中修改

### 架构决策记录

| # | 决策 | 理由 |
|---|------|------|
| 1 | 水位线并行（新 reflect 用 conversation_sessions，旧 digest 用 emotion_profiles） | 向后兼容，避免迁移风险 |
| 2 | LLM prompt 使用 system + user 双消息 | 更好的角色定义，现有 provider 完全支持 |
| 3 | reflect() 返回 dict 而非自定义类 | 与现有 digest()/recall() 返回格式一致 |
| 4 | TraitEngine 不持有 LLM provider | 仅 resolve_contradiction 需要 LLM，通过参数传入，降低耦合 |
| 5 | 阶段过滤作为静态 SQL 条件 | 无参数绑定，性能最优 |
| 6 | 不修改 _maybe_trigger_digest | MVP 阶段保持最小改动，reflect 由用户显式调用 |
