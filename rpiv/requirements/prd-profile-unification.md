---
description: "产品需求文档: Profile 统一架构 - 消除三套平行用户画像机制"
status: completed
created_at: 2026-03-02T21:00:00
updated_at: 2026-03-02T21:30:00
archived_at: null
---

# PRD: Profile 统一架构

## 1. 执行摘要

neuromem SDK 当前存在三套平行的用户画像机制：KV Profile（通过 `_store_profile_updates` 写入 KV 存储）、Emotion Profile（通过 `_update_emotion_profile` 写入 `emotion_profiles` 表）、以及记忆分类 V2 引入的 Trait 系统（存储在 `memories` 表的 trait 类型记忆中）。三套机制数据源分裂、质量参差不齐，其中 KV Profile 基于单次 LLM 推断直接提取用户画像（研究表明 r=0.27），严重违背了 V2 设计的核心科学原则——"trait 必须由反思引擎归纳产生，禁止从单次对话直接提取"。

本项目将统一为 **fact + trait + 计算视图** 的单一数据流架构：identity/occupation 等身份信息降级为带 category 标注的普通 fact；情绪宏观模式（dominant_emotions、emotion_triggers）归入 trait 由反思引擎归纳产生；近期情绪状态改为 recall 时从 episodic 记忆的 emotion metadata 实时聚合。最终通过新增的 `profile_view()` 方法提供统一的用户画像视图，每条数据都有明确的来源、置信度和证据链。

**核心价值主张**：消除数据分裂，让用户画像的每一条数据都符合科学原则，提升记忆系统的整体质量和可信度。

**MVP 目标**：SDK 和 Cloud 同步完成改造，提供迁移脚本处理历史数据，版本号跳升以反映破坏性变更。

## 2. 使命

**产品使命**：为 AI 记忆系统提供基于科学原则的用户画像机制——每条画像数据都可追溯、有置信度、经过多轮验证。

**核心原则**：

1. **科学严谨性**：trait 只能由反思引擎归纳产生，禁止从单次对话直接推断人格特质（Mischel CAPS + Allport 特质理论）
2. **单一数据源**：消除平行机制，fact 和 trait 存储在统一的 `memories` 表中，不再分散到 KV 和独立表
3. **可追溯性**：每条画像数据标注来源（extraction/reflection）、置信度和证据链
4. **向前兼容**：通过迁移脚本转化历史数据，不丢失用户积累；Cloud 端兼容旧版 SDK 客户端
5. **最小必要变更**：只改必须改的代码路径，不做 scope creep

## 3. 目标用户

**主要用户角色**：

- **neuromem SDK 开发者**：直接调用 `NeuroMemory` 类进行记忆管理的 Python 开发者。技术舒适度高，关注 API 稳定性和数据质量。痛点：三套画像机制让他们困惑，不确定该信任哪套数据
- **neuromem Cloud 集成方**：通过 REST API / MCP 协议使用 Cloud 服务的 AI Agent 开发者。关注 extraction prompt 返回结构的一致性。痛点：One-LLM 模式下 `profile_updates` 字段的存在增加了集成复杂度
- **Me2 团队（间接影响）**：Me2 应用依赖 SDK 0.8.0，本次改造后需后续单独适配。本 MVP 不涉及 Me2 改造

**关键需求**：
- 统一且可信的用户画像数据
- 清晰的 API 变更文档和迁移指南
- 不丢失历史积累的用户数据

## 4. MVP 范围

### 范围内

**核心功能：**
- ✅ Ingest 流程改造：extraction prompt 删除 `profile_updates` 块，identity/occupation 作为带 `metadata_.category` 标注的普通 fact 提取
- ✅ 删除 `_store_profile_updates()` 方法及 `_PROFILE_OVERWRITE_KEYS`/`_PROFILE_APPEND_KEYS` 常量
- ✅ 新增 `profile_view(user_id)` 方法，从 fact + trait + 近期 episodic emotion 实时组装用户画像
- ✅ Recall 流程改造：`_fetch_user_profile()` 替换为 `profile_view()` 调用
- ✅ Digest/Reflect 流程改造：删除 `_update_emotion_profile()` 方法，情绪宏观模式归入 trait
- ✅ `last_reflected_at` watermark 从 `emotion_profiles` 表和 `conversation_sessions` 表迁入 `reflection_cycles` 表
- ✅ 数据迁移脚本：KV profile -> fact/trait，emotion macro -> trait，watermark -> reflection_cycles
- ✅ 删除 `emotion_profiles` 表（迁移完成后）
- ✅ Cloud 适配：extraction_prompt.py、core.py 中 `ingest_extracted` 同步去掉 profile_updates 处理

**技术：**
- ✅ SDK 版本号跳升（破坏性 API 变更）
- ✅ Cloud 端兼容旧版 SDK 客户端（静默忽略 `profile_updates`）
- ✅ 迁移脚本支持 dry-run 模式和事务保护

### 范围外

- ❌ Me2 适配（后续单独处理，Me2 有自己的 `from app.main import nm` 全局单例模式）
- ❌ `profile_view()` 缓存（延迟决策，先不缓存，等性能测试后再定）
- ❌ Me2 前端 ProfileSection 改造
- ❌ 召回即强化（recall 时自动给匹配的 trait +0.02 confidence）
- ❌ 记忆横向关联（Zettelkasten 模式）
- ❌ Trait Transparency（向用户展示 trait 决策链路）

## 5. 用户故事

**US-1**：作为 SDK 开发者，我想要从 `recall()` 返回值中获取统一的用户画像视图，以便用一致的数据源组装更好的 LLM prompt。
- 示例：`result["user_profile"]` 返回 `{"facts": {"identity": "张三，男，28岁", ...}, "traits": [{"content": "工作时倾向焦虑", ...}], "recent_mood": {"valence_avg": -0.3, ...}}`

**US-2**：作为 SDK 开发者，我想要 identity/occupation 信息作为普通 fact 被提取和存储，以便保留完整的历史轨迹（而非被覆写）。
- 示例：用户先说"我在 Google 工作"，后说"我跳槽到 Meta 了"，两条 fact 都保留，`profile_view` 取最新

**US-3**：作为 SDK 开发者，我想要情绪宏观模式（如"工作话题容易焦虑"）由反思引擎归纳产生为 trait，以便获得更可信的情绪画像。
- 示例：digest 后产生 trait: `{"content": "工作场景下倾向焦虑", "trait_context": "work", "trait_subtype": "behavior", "trait_confidence": 0.4}`

**US-4**：作为 Cloud 集成方，我想要 One-LLM 模式的 extraction prompt 不再包含 `profile_updates` 字段，以便简化集成逻辑。
- 示例：`ingest_extracted` 的 `data` 参数结构从 `{facts, episodes, triples, profile_updates}` 简化为 `{facts, episodes, triples}`

**US-5**：作为现有用户，我想要历史积累的 KV profile 和 emotion profile 数据被完整迁移到新系统，以便不丢失任何信息。
- 示例：KV profile 中 `identity: "张三"` 迁移为 fact `{"content": "用户名为张三", "metadata_": {"category": "identity"}}`, interests `["摄影"]` 迁移为 behavior trait（trend 阶段，低置信度）

**US-6**：作为 SDK 开发者，我想要通过 `profile_view()` 独立调用获取用户画像视图，以便在非 recall 场景下也能访问。
- 示例：`profile = await nm.profile_view(user_id="u1")` 直接返回画像数据

**US-7**：作为 Cloud 维护者，我想要 Cloud 端兼容仍发送 `profile_updates` 的旧版 SDK 客户端，以便平滑过渡。
- 示例：旧客户端发送 `ingest_extracted` 含 `profile_updates` 时，Cloud 静默忽略该字段，不报错

## 6. 核心架构与模式

### 改造前数据流

```
ingest() → LLM extraction → {facts, episodes, triples, profile_updates}
                              ├── facts/episodes → memories 表
                              ├── triples → graph_nodes/edges 表
                              └── profile_updates → KV 存储 (namespace="profile")

recall() → _fetch_user_profile() → KV 存储读取 7 个 key → user_profile dict

digest() → _update_emotion_profile() → emotion_profiles 表
         → _generate_insights() → memories 表 (type=trait, stage=trend)

reflect() → ReflectionService → trait 分析 → memories 表 (type=trait)
          → watermark 在 conversation_sessions.last_reflected_at
```

### 改造后数据流

```
ingest() → LLM extraction → {facts, episodes, triples}
                              ├── facts (含 identity/occupation category) → memories 表
                              ├── episodes (含 emotion metadata) → memories 表
                              └── triples → graph_nodes/edges 表

recall() → profile_view() → 从 memories 表实时组装:
                              ├── facts: 最新 identity/occupation/interests 等
                              ├── traits: emerging+ 阶段的活跃 trait
                              └── recent_mood: 近期 episodic emotion 聚合

digest() → _generate_insights() → memories 表 (type=trait, stage=trend)
         → [不再更新 emotion_profiles]

reflect() → ReflectionService → trait 分析（含情绪模式识别）→ memories 表 (type=trait)
          → watermark 在 reflection_cycles 表
```

### 关键设计模式

- **Facade 模式不变**：`NeuroMemory` 仍是唯一入口，`profile_view()` 作为新公共方法添加到 Facade
- **Service 层职责调整**：`MemoryExtractionService` 不再负责 profile 更新；`ReflectionService` 删除 emotion profile 更新，增加情绪模式识别能力
- **计算视图模式**：`profile_view()` 不存储聚合结果，每次调用实时查询并组装，保证数据新鲜度

### 目录结构变更

```
neuromem/
  _core.py                    # +profile_view(), -_fetch_user_profile(), 修改 recall()/digest()
  services/
    memory_extraction.py       # -_store_profile_updates(), 修改 prompt
    reflection.py              # -_update_emotion_profile(), -_build_emotion_summary_prompt()
                               # 修改 watermark 逻辑
  models/
    emotion_profile.py         # 标记废弃，迁移后删除
scripts/
  migrate_profile_unification.py  # 新增迁移脚本
```

## 7. 功能规范

### 7.1 Ingest 流程改造

**涉及文件**：
- `neuromem/services/memory_extraction.py`
- `neuromem-cloud/server/src/neuromem_cloud/extraction_prompt.py`

**改动点**：

1. **extraction prompt 修改**（SDK `_build_zh_prompt` / `_build_en_prompt`）：
   - 删除 `profile_updates` 块（profile_section_zh / profile_section_en）
   - 在 Facts 提取规则中增加 category 指引：`identity`（姓名、年龄、性别等核心身份信息）和 `occupation`（职业/公司/职位）作为 fact 的 category 选项
   - 返回格式从 `{facts, episodes, triples, profile_updates}` 简化为 `{facts, episodes, triples}`

2. **删除 `_store_profile_updates()` 方法和相关常量**：
   - 删除 `_PROFILE_OVERWRITE_KEYS` 常量
   - 删除 `_PROFILE_APPEND_KEYS` 常量
   - 删除 `_store_profile_updates()` 方法
   - 删除 `extract_from_messages()` 中对 `profile_updates` 的调用

3. **`_parse_classification_result()` 修改**：
   - 不再解析 `profile_updates` 字段（静默忽略，兼容旧 LLM 输出可能仍返回该字段）

4. **Cloud extraction_prompt.py 同步修改**：
   - `_build_en_extraction_prompt()` 和 `_build_zh_extraction_prompt()` 删除 Profile Updates 块
   - 返回格式同步简化

### 7.2 profile_view() 方法

**涉及文件**：
- `neuromem/_core.py`

**功能描述**：
新增公共方法 `profile_view(user_id: str) -> dict`，从 memories 表实时组装用户画像。

**返回结构**：
```python
{
    "facts": {
        "identity": "张三，男，28岁",       # 最新 category=identity 的 fact
        "occupation": "Meta 软件工程师",     # 最新 category=occupation 的 fact
        "interests": ["摄影", "徒步"],       # 最新若干 category=hobby 的 fact.content
        "skills": ["Python", "Rust"],        # 最新若干 category=skill 的 fact.content
        "location": "北京",                  # 最新 category=location 的 fact
        # ... 根据实际 fact 的 category 动态填充
    },
    "traits": [
        {
            "content": "工作场景下倾向焦虑",
            "subtype": "behavior",
            "stage": "emerging",
            "confidence": 0.45,
            "context": "work",
        },
        # ... emerging+ 阶段的活跃 trait
    ],
    "recent_mood": {
        "valence_avg": -0.3,
        "arousal_avg": 0.5,
        "sample_count": 12,
        "period": "last_14_days",
    } or None,  # 无 emotion 数据时为 None
}
```

**实现逻辑**：
1. **facts 查询**：从 memories 表查询 `memory_type='fact'` 且 `valid_until IS NULL` 的记忆，按 `metadata_->>'category'` 分组，每组取最新记录。对于列表型 category（interests/skills），取最新若干条的 content
2. **traits 查询**：从 memories 表查询 `memory_type='trait'` 且 `trait_stage NOT IN ('trend', 'dissolved')` 的记忆，按 `trait_confidence DESC` 排序，取 top N
3. **recent_mood 聚合**：从 memories 表查询最近 14 天的 `memory_type='episodic'` 记忆，提取 `metadata_->'emotion'` 中的 valence/arousal，计算平均值

**与 recall 的关系**：
- `recall()` 中将 `self._fetch_user_profile(user_id)` 替换为 `self.profile_view(user_id)`
- 两者并行执行，`profile_view` 和 vector search 同步进行

### 7.3 Digest/Reflect 流程改造

**涉及文件**：
- `neuromem/services/reflection.py`
- `neuromem/_core.py`

**改动点**：

1. **删除 `_update_emotion_profile()` 方法**（reflection.py）：
   - 同时删除 `_build_emotion_summary_prompt()` 和 `_parse_emotion_summary()` 和 `_get_current_period()`
   - `digest()` 方法返回值去掉 `emotion_profile` 字段，只返回 `{"insights": [...]}`

2. **反思引擎增加情绪模式识别**（reflection.py）：
   - 在 `REFLECTION_PROMPT_TEMPLATE` 中增加引导 LLM 从带有 emotion metadata 的记忆中识别情绪模式
   - 情绪模式作为情境化 trait 产生，例如 `{"content": "工作话题讨论时倾向焦虑", "context": "work"}`

3. **watermark 迁移**（reflection.py + _core.py）：
   - `_digest_impl()` 中的 watermark 读写从 `emotion_profiles.last_reflected_at` 改为查询 `reflection_cycles` 表最新完成的 cycle 时间
   - `_update_watermark()` 方法修改为在 reflection_cycles 表中记录，不再更新 `conversation_sessions.last_reflected_at`（该字段可保留用于会话管理但不再用于反思水位线）
   - `should_reflect()` 中的 watermark 查询同步修改

4. **`_core.py` 中 `digest()` 返回值调整**：
   - 返回值不再包含 `emotion_profile` 字段

### 7.4 数据迁移

**新增文件**：
- `scripts/migrate_profile_unification.py`

**迁移内容**：

| 源数据 | 目标 | 转换规则 |
|--------|------|----------|
| KV profile: identity | fact (category=identity) | 直接创建 fact，带 `{"category": "identity", "source": "migration"}` |
| KV profile: occupation | fact (category=occupation) | 直接创建 fact |
| KV profile: interests | behavior trait (trend) | 每项创建独立 trait，置信度 0.2（低），`{"source": "migration"}` |
| KV profile: preferences | behavior trait (trend) | 同上 |
| KV profile: values | behavior trait (trend) | 同上，context=general |
| KV profile: personality | behavior trait (trend) | 同上 |
| KV profile: relationships | fact (category=relationship) | 每项创建独立 fact |
| emotion_profiles: dominant_emotions | behavior trait (trend) | 每项创建独立 trait，context 标注 |
| emotion_profiles: emotion_triggers | behavior trait (trend) | 每项创建独立 trait，context 从 trigger 话题推断 |
| emotion_profiles: last_reflected_at | reflection_cycles | 创建 migration type 的 cycle 记录 |

**迁移脚本要求**：
- 支持 `--dry-run` 模式预览变更
- 事务保护，失败可回滚
- 空值字段跳过不迁移
- 迁移完成后删除 KV profile namespace 数据
- 迁移后的 trait 统一设置低置信度（0.2），等待后续反思引擎验证升级
- 需要 embedding provider 为迁移的 fact/trait 生成向量

### 7.5 Cloud 适配

**涉及文件**：
- `neuromem-cloud/server/src/neuromem_cloud/extraction_prompt.py`
- `neuromem-cloud/server/src/neuromem_cloud/core.py`

**改动点**：

1. **extraction_prompt.py**：删除 Profile Updates 块（已在 7.1 描述）

2. **core.py `do_ingest_extracted()`**：
   - 删除 `profile_updates` 的处理逻辑（第 177 行和 237-242 行）
   - 返回值去掉 `profile_updates_stored` 字段
   - 兼容处理：如果旧客户端仍发送 `profile_updates`，静默忽略（不报错）

3. **core.py `do_digest()`**：
   - 返回值去掉 `profile_updated` 字段（因为不再有 emotion profile 更新）

## 8. 技术栈

本项目不引入新技术栈，所有改动在现有技术栈内完成：

- **SDK**：Python 3.11+, SQLAlchemy 2.0 async, asyncpg, pgvector
- **Cloud 后端**：FastAPI 0.115+, FastMCP 2.x
- **数据库**：PostgreSQL + pgvector + pg_search（ParadeDB）
- **测试**：pytest (asyncio_mode="auto"), 端口 5436 的测试数据库

**依赖变更**：无新增依赖

## 9. 安全与配置

**安全范围**：
- 本项目不涉及认证/授权变更
- 数据迁移脚本需要直接数据库访问权限（DATABASE_URL）
- 迁移脚本应在维护窗口执行，建议先备份数据库

**配置变更**：
- 无新增环境变量
- 无新增配置项

**部署考虑**：
- SDK 需要版本号跳升（建议 0.9.0），因为有破坏性 API 变更
- Cloud 部署顺序：先升级 SDK 依赖 → 再部署 Cloud 服务 → 最后执行迁移脚本
- 迁移脚本执行期间服务可正常运行（迁移是追加操作，不删除源数据直到确认完成）

## 10. API 规范

### 10.1 `profile_view()` 新增 API

```python
async def profile_view(self, user_id: str) -> dict:
    """获取用户画像视图。

    从 fact + trait + 近期 episodic emotion 实时组装用户画像。

    Args:
        user_id: 用户 ID

    Returns:
        {"facts": {...}, "traits": [...], "recent_mood": {...} | None}
    """
```

### 10.2 `recall()` 返回值变更

**Before**：
```python
{
    "user_profile": {
        "identity": "张三",
        "occupation": "Google 工程师",
        "interests": ["摄影", "徒步"],
        ...  # 7 个 KV key
    },
    "merged": [...],
    ...
}
```

**After**：
```python
{
    "user_profile": {
        "facts": {"identity": "张三，男，28岁", "occupation": "Meta 工程师", ...},
        "traits": [{"content": "...", "subtype": "...", "confidence": ...}],
        "recent_mood": {"valence_avg": ..., "arousal_avg": ..., ...} or None,
    },
    "merged": [...],
    ...
}
```

### 10.3 `digest()` 返回值变更

**Before**：
```python
{
    "memories_analyzed": 50,
    "insights_generated": 3,
    "insights": [...],
    "emotion_profile": {"latest_state": "...", "dominant_emotions": {...}, ...},
}
```

**After**：
```python
{
    "memories_analyzed": 50,
    "insights_generated": 3,
    "insights": [...],
    # emotion_profile 字段被移除
}
```

### 10.4 Extraction 输出结构变更

**Before**：
```json
{
    "facts": [...],
    "episodes": [...],
    "triples": [...],
    "profile_updates": {
        "identity": "...",
        "occupation": "...",
        "interests": [...]
    }
}
```

**After**：
```json
{
    "facts": [...],
    "episodes": [...],
    "triples": [...]
}
```

Facts 中的 category 增加 `identity` 和 `occupation` 选项，示例：
```json
{
    "content": "用户在 Meta 担任软件工程师",
    "category": "occupation",
    "confidence": 0.95,
    "importance": 9
}
```

### 10.5 Cloud `ingest_extracted` 返回值变更

**Before**：
```json
{
    "memory_id": "...",
    "user_id": "...",
    "facts_stored": 3,
    "episodes_stored": 1,
    "triples_stored": 2,
    "profile_updates_stored": 1
}
```

**After**：
```json
{
    "memory_id": "...",
    "user_id": "...",
    "facts_stored": 3,
    "episodes_stored": 1,
    "triples_stored": 2
}
```

## 11. 成功标准

**MVP 成功定义**：SDK + Cloud 完成所有 5 个核心场景改造，历史数据完整迁移，所有现有测试通过。

**功能要求**：
- ✅ `recall()` 返回的 `user_profile` 使用新结构（facts + traits + recent_mood）
- ✅ `profile_view()` 可独立调用并返回正确数据
- ✅ identity/occupation 作为 fact 存储，历史轨迹保留（不覆写）
- ✅ `digest()` 不再更新 `emotion_profiles` 表
- ✅ 反思引擎能识别情绪模式并产生情境化 trait
- ✅ 迁移脚本成功将所有历史数据转化
- ✅ Cloud One-LLM 模式 prompt 不再包含 `profile_updates`
- ✅ Cloud `ingest_extracted` 兼容旧版客户端（静默忽略 `profile_updates`）

**质量指标**：
- 所有现有 SDK 测试通过
- 所有现有 Cloud 测试通过
- 新增测试覆盖 `profile_view()` 的所有分支
- 新增测试覆盖迁移脚本的 dry-run 和实际迁移
- 新增测试覆盖反思引擎的情绪模式识别
- watermark 迁移后不丢失、不重复处理已分析的记忆

**用户体验目标**：
- `profile_view()` 响应时间 < 200ms（无缓存，单用户数据量 < 10000 条记忆）
- 迁移脚本执行时间 < 5 分钟（单租户 < 100000 条记忆）

## 12. 实施阶段

### Phase 1：Ingest 流程改造
**目标**：消除 profile_updates 提取和存储路径
**交付物**：
- ✅ SDK extraction prompt 修改（中文 + 英文）
- ✅ `_store_profile_updates()` 方法及常量删除
- ✅ `_parse_classification_result()` 兼容修改
- ✅ Cloud extraction_prompt.py 同步修改
- ✅ Cloud core.py `ingest_extracted` 修改（含旧客户端兼容）
**验证**：SDK 和 Cloud 的 ingest 相关测试全部通过，LLM extraction 输出不再包含 profile_updates

### Phase 2：profile_view() + Recall 改造
**目标**：提供统一的用户画像视图
**交付物**：
- ✅ `profile_view()` 方法实现
- ✅ `_fetch_user_profile()` 替换为 `profile_view()`
- ✅ recall() 返回值结构变更
- ✅ 新增 profile_view 单元测试
**验证**：recall 相关测试通过，profile_view 返回正确的 facts + traits + recent_mood

### Phase 3：Digest/Reflect 改造 + Watermark 迁移
**目标**：消除 emotion profile 机制，统一 watermark
**交付物**：
- ✅ `_update_emotion_profile()` 及相关方法删除
- ✅ 反思引擎情绪模式识别增强
- ✅ watermark 逻辑迁移到 reflection_cycles
- ✅ digest() 返回值调整
- ✅ Cloud do_digest 返回值调整
**验证**：digest/reflect 测试通过，watermark 正确从 reflection_cycles 读写

### Phase 4：数据迁移 + 清理
**目标**：历史数据完整迁移，旧机制清理
**交付物**：
- ✅ 迁移脚本编写和测试
- ✅ emotion_profiles 表废弃/删除
- ✅ KV profile namespace 清理
- ✅ 版本号跳升
**验证**：迁移脚本 dry-run 验证、实际迁移测试、全套回归测试

## 13. 未来考虑

**MVP 后增强**：
- Me2 适配：更新 Me2 后端对 SDK API 变更的调用点
- `profile_view()` 缓存：基于性能测试结果决定是否添加 LRU 缓存
- Trait Transparency：允许用户查看 trait 的证据链和决策过程
- 召回即强化：recall 匹配到的 trait 自动 +0.02 confidence

**集成机会**：
- Cloud Dashboard 展示用户画像视图（基于 `profile_view()` 的结构化数据）
- MCP tool 暴露 `profile_view` 操作

**高级功能**：
- 记忆横向关联（Zettelkasten）
- 两阶段反思（快速扫描 + 深度分析）
- 前瞻记忆（"用户计划下周去旅行" → 提前准备相关记忆）

## 14. 风险与缓解措施

| 风险 | 影响 | 概率 | 缓解策略 |
|------|------|------|----------|
| **破坏性 API 变更导致下游集成方报错** | 高 | 中 | Cloud 端兼容旧客户端（静默忽略 profile_updates）；版本号跳升明确标识；提供迁移指南 |
| **迁移脚本数据丢失或损坏** | 高 | 低 | 事务保护 + dry-run 模式；迁移前建议备份；迁移是追加操作，源数据在确认后才清理 |
| **watermark 迁移导致记忆重复处理** | 中 | 中 | 迁移脚本将旧 watermark 精确转移到 reflection_cycles；添加幂等性检查 |
| **`profile_view()` 性能不足** | 中 | 低 | 预留缓存接口但不实现；查询使用索引；限制返回数量 |
| **反思引擎情绪模式识别质量不佳** | 中 | 中 | 保守处理：情绪 trait 初始置信度低（0.3），需要多次强化才能升级；不影响核心画像功能 |

## 15. 附录

### 相关文档
- 记忆分类 V2 设计：`D:/CODE/NeuroMem/docs/design/memory-classification-v2.md`
- 需求摘要：`D:/CODE/NeuroMem/rpiv/brainstorm-summary-profile-unification.md`

### 关键代码位置
- SDK Facade：`D:/CODE/NeuroMem/neuromem/_core.py`
- 记忆提取服务：`D:/CODE/NeuroMem/neuromem/services/memory_extraction.py`
- 反思服务：`D:/CODE/NeuroMem/neuromem/services/reflection.py`
- Trait 引擎：`D:/CODE/NeuroMem/neuromem/services/trait_engine.py`
- Emotion Profile 模型：`D:/CODE/NeuroMem/neuromem/models/emotion_profile.py`
- Reflection Cycle 模型：`D:/CODE/NeuroMem/neuromem/models/reflection_cycle.py`
- Cloud 业务逻辑：`D:/CODE/neuromem-cloud/server/src/neuromem_cloud/core.py`
- Cloud Extraction Prompt：`D:/CODE/neuromem-cloud/server/src/neuromem_cloud/extraction_prompt.py`

### 关键设计决策记录

| 决策点 | 选择 | 理由 |
|--------|------|------|
| fact category 存储方式 | metadata JSONB 中的 `category` 字段 | 低频查询场景，不值得为此新增数据库列 |
| identity/occupation 覆写语义 | 追加不覆写，`profile_view` 取最新 | 记忆不应被悄悄覆写，历史轨迹有价值（如职业变迁） |
| profile_view 返回结构 | 区分 facts / traits / recent_mood | 调用方需要知道数据来源和可信度，以组装更好的 prompt |
| profile_view 缓存 | MVP 不缓存 | 先测性能，避免过早优化带来的缓存一致性复杂度 |
| emotion macro 归属 | 归入 trait | "工作话题容易焦虑"本质是情境化特质，符合 V2 trait 定义 |
| emotion meso 处理 | recall 时实时聚合 | 近期情绪是临时状态，不需要持久化到独立表 |
| watermark 存储 | 迁入 reflection_cycles | 纯运维字段，不属于用户画像数据 |
| 历史数据处理 | 迁移转化 + 降低置信度 | 保留积累，但以低置信度标记等待反思引擎验证 |
