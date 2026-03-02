---
description: "测试策略: Profile 统一架构重构"
status: completed
created_at: 2026-03-02T20:10:00
updated_at: 2026-03-02T20:10:00
---

# 测试策略: Profile 统一架构

## 1. 测试范围概述

本次重构涉及 5 个核心场景，影响 SDK 全部三个核心流程（ingest/recall/digest）及 Cloud 适配层。测试需覆盖：

| 场景 | 涉及模块 | 测试类型 |
|------|----------|----------|
| S1: Ingest 流程改造 | `memory_extraction.py`, extraction prompt | 单元 + 集成 |
| S2: Recall 流程改造 | `_core.py`, 新增 `profile_view()` | 单元 + 集成 |
| S3: Digest/Reflect 改造 | `reflection.py`, `_core.py` | 单元 + 集成 |
| S4: 数据迁移 | 迁移脚本 | 单元 + 集成 + 端到端 |
| S5: Cloud 适配 | `extraction_prompt.py`, `core.py`, `schemas.py` | 单元 + 集成 |
| 回归 | 全部已有测试 | 回归 |

## 2. 测试环境

- **数据库**：PostgreSQL 端口 5436（与现有 `conftest.py` 一致）
- **Fixture**：复用现有 `db_session`、`mock_embedding`、`mock_llm`、`nm` fixture
- **Mock 策略**：所有 LLM/Embedding 调用使用 Mock Provider，无外部 API 依赖
- **asyncio_mode**：`auto`，测试函数直接 `async def`
- **隔离**：每个测试函数独立的 db session + rollback

## 3. 场景测试详细计划

### 3.1 S1: Ingest 流程改造

**目标**：验证 extraction prompt 不再产生 `profile_updates`，identity/occupation 作为带 category 的 fact 提取。

#### 单元测试

| 测试用例 | 验证点 | 优先级 |
|----------|--------|--------|
| `test_extraction_no_profile_updates` | Mock LLM 返回新格式（无 profile_updates），提取成功 | P0 |
| `test_extraction_identity_as_fact` | identity 信息作为 `memory_type=fact` + `metadata_.category=identity` 存储 | P0 |
| `test_extraction_occupation_as_fact` | occupation 信息作为 `memory_type=fact` + `metadata_.category=occupation` 存储 | P0 |
| `test_extraction_old_format_graceful` | 如果 LLM 仍返回 profile_updates 字段，静默忽略不报错 | P0 |
| `test_extraction_category_default_general` | LLM 未标注 category 时默认为 `general` | P1 |
| `test_parse_classification_no_profile_updates` | `_parse_classification_result()` 输出不含 `profile_updates` key | P0 |
| `test_store_profile_updates_removed` | `_store_profile_updates()` 方法和 `_PROFILE_*_KEYS` 常量已删除 | P0 |

#### 集成测试

| 测试用例 | 验证点 | 优先级 |
|----------|--------|--------|
| `test_ingest_pipeline_no_kv_profile_write` | 完整 ingest 流程不再写入 KV profile namespace | P0 |
| `test_ingest_fact_with_category_stored` | ingest 后 DB 中 fact 记录的 metadata 含正确 category | P0 |

### 3.2 S2: Recall 流程改造

**目标**：验证 `profile_view()` 正确组装 facts/traits/recent_mood，`_fetch_user_profile()` 被替换。

#### 单元测试

| 测试用例 | 验证点 | 优先级 |
|----------|--------|--------|
| `test_profile_view_returns_correct_structure` | 返回 `{"facts": {...}, "traits": {...}, "recent_mood": {...}}` | P0 |
| `test_profile_view_facts_from_identity_occupation` | 从 category=identity/occupation 的 fact 中取最新 | P0 |
| `test_profile_view_traits_emerging_and_above` | 只包含 emerging+ 阶段的 trait | P0 |
| `test_profile_view_traits_with_confidence` | 每个 trait 条目附带 confidence 和 source 信息 | P1 |
| `test_profile_view_recent_mood_from_episodic` | 从近期 episodic 的 emotion metadata 聚合 | P0 |
| `test_profile_view_new_user_empty` | 新用户返回空 facts、空 traits、null recent_mood | P0 |
| `test_profile_view_no_emotion_data` | 无 emotion 数据时 recent_mood 为 null | P1 |
| `test_fetch_user_profile_removed` | `_fetch_user_profile()` 方法已删除或重定向到 `profile_view()` | P0 |

#### 集成测试

| 测试用例 | 验证点 | 优先级 |
|----------|--------|--------|
| `test_recall_uses_profile_view` | `recall()` 返回值中 `user_profile` 使用新结构 | P0 |
| `test_recall_profile_view_parallel` | profile_view 与 vector search 并行执行（性能不退化） | P1 |
| `test_recall_user_profile_field_structure` | recall 返回的 `user_profile` 区分 facts/traits/recent_mood | P0 |

### 3.3 S3: Digest/Reflect 流程改造

**目标**：验证 digest 不再更新 emotion_profiles 表，情绪模式归入 trait，watermark 迁入 reflection_cycles。

#### 单元测试

| 测试用例 | 验证点 | 优先级 |
|----------|--------|--------|
| `test_digest_no_emotion_profile_update` | digest() 不再写入 emotion_profiles 表 | P0 |
| `test_digest_returns_no_emotion_profile_field` | digest() 返回值不含 `emotion_profile` 字段 | P0 |
| `test_update_emotion_profile_removed` | `_update_emotion_profile()` 方法已删除 | P0 |
| `test_digest_emotion_pattern_as_trait` | 情绪模式以 trait 形式产生（情境化 trait） | P0 |
| `test_digest_watermark_in_reflection_cycles` | watermark 存储在 reflection_cycles 表而非 emotion_profiles | P0 |
| `test_digest_watermark_incremental_from_cycles` | 增量处理根据 reflection_cycles 中的 completed_at 确定 watermark | P0 |
| `test_digest_convergence_with_new_watermark` | 多次 digest 后收敛（与现有 test_reflect_watermark 逻辑一致） | P1 |

#### 集成测试

| 测试用例 | 验证点 | 优先级 |
|----------|--------|--------|
| `test_digest_full_pipeline_no_emotion_table` | 完整 digest 流程不触碰 emotion_profiles 表 | P0 |
| `test_digest_trait_generation_with_emotion` | 含情绪数据的记忆经 digest 后产生情境化 trait | P0 |

### 3.4 S4: 数据迁移

**目标**：验证迁移脚本正确将 KV profile、emotion_profiles 数据转化为 fact/trait，watermark 迁入 reflection_cycles。

#### 单元测试

| 测试用例 | 验证点 | 优先级 |
|----------|--------|--------|
| `test_migrate_kv_identity_to_fact` | KV identity → fact（category=identity） | P0 |
| `test_migrate_kv_occupation_to_fact` | KV occupation → fact（category=occupation） | P0 |
| `test_migrate_kv_preferences_to_trait` | KV preferences → behavior trait（trend 阶段，低置信度） | P0 |
| `test_migrate_kv_interests_to_trait` | KV interests → behavior trait（trend 阶段） | P0 |
| `test_migrate_kv_values_to_trait` | KV values → behavior trait（trend 阶段） | P0 |
| `test_migrate_kv_personality_to_trait` | KV personality → behavior trait（trend 阶段） | P0 |
| `test_migrate_emotion_macro_to_trait` | emotion_profiles macro 字段 → trait | P0 |
| `test_migrate_watermark_to_reflection_cycles` | last_reflected_at → reflection_cycles 记录 | P0 |
| `test_migrate_empty_values_skip` | 空值字段不创建记录 | P1 |
| `test_migrate_dry_run` | dry-run 模式不写入数据库，仅输出预览 | P0 |
| `test_migrate_rollback_on_failure` | 迁移过程中异常时事务回滚，数据不丢失 | P0 |
| `test_migrate_idempotent` | 重复执行迁移不产生重复数据 | P1 |

#### 集成测试

| 测试用例 | 验证点 | 优先级 |
|----------|--------|--------|
| `test_migration_end_to_end` | 完整迁移流程：KV 数据 + emotion 数据 → fact + trait + reflection_cycles | P0 |
| `test_migration_preserves_data_integrity` | 迁移后新数据可被 recall/profile_view 正确检索 | P0 |
| `test_migration_cleanup_kv_namespace` | 迁移完成后 KV profile namespace 被清理 | P1 |
| `test_migration_cleanup_emotion_table` | 迁移完成后 emotion_profiles 表被删除（或标记废弃） | P1 |

### 3.5 S5: Cloud 适配

**目标**：验证 Cloud 端 extraction prompt 和处理逻辑同步去掉 profile_updates。

#### 单元测试（Cloud 仓库 `neuromem-cloud/server/tests/`）

| 测试用例 | 验证点 | 优先级 |
|----------|--------|--------|
| `test_extraction_prompt_no_profile_updates` | SDK 模式和 One-LLM 模式的 prompt 不含 profile_updates | P0 |
| `test_ingest_extracted_ignores_profile_updates` | `core.py` 的 `ingest_extracted` 忽略 profile_updates 字段 | P0 |
| `test_schemas_no_profile_fields` | schemas.py 中无 profile 相关字段 | P1 |
| `test_cloud_backward_compat_old_sdk` | 旧版 SDK 仍发送 profile_updates 时静默忽略 | P0 |

## 4. 回归测试

### 4.1 必须通过的现有测试

以下现有测试文件需要全部通过（部分测试可能需要修改以适应新 API）：

| 测试文件 | 关注点 | 预期修改 |
|----------|--------|----------|
| `test_memory_extraction.py` | extraction 流程 | 修改：去掉 profile_updates 相关断言 |
| `test_recall.py` | recall 评分排序 | 可能修改：user_profile 结构断言 |
| `test_recall_emotion.py` | 情绪标签注入 | 修改：emotion_profiles 表相关测试 |
| `test_reflection.py` | 反思生成 | 修改：去掉 emotion_profile 相关断言 |
| `test_reflect_watermark.py` | watermark 增量 | 修改：watermark 读取改为 reflection_cycles |
| `test_reflect_api.py` | public API | 修改：digest 返回值结构 |
| `test_reflection_v2.py` | v2 反思管道 | 可能修改 |
| `test_trait_engine.py` | trait 衰减/升级 | 不变 |
| `test_kv.py` | KV 存储 CRUD | 不变 |
| `test_conversations.py` | 会话管理 | 不变 |
| `test_search.py` | 搜索功能 | 不变 |
| `test_graph*.py` | 图谱功能 | 不变 |
| `test_temporal*.py` | 时间功能 | 不变 |
| `test_storage_v2*.py` | 存储层 | 不变 |

### 4.2 需要修改的测试

需要重点审查并修改的测试：

1. **`test_memory_extraction.py`**：
   - `test_extract_memories_from_conversations`：Mock LLM 返回含 profile_updates，需改为新格式
   - `test_parse_classification_result`：返回值不再含 profile_updates key
   - KVService 验证 preferences 存储的断言需删除

2. **`test_reflection.py`**：
   - `test_reflect_generates_insights`：去掉 `emotion_profile` 返回值断言
   - `test_reflect_updates_emotion_profile`：整个测试应删除或改为验证情绪 trait
   - `test_reflect_with_no_emotions_skips_profile_update`：修改为验证新行为

3. **`test_reflect_watermark.py`**：
   - 所有读取 `emotion_profiles.last_reflected_at` 的断言改为读取 `reflection_cycles`

4. **`test_recall_emotion.py`**：
   - `test_recall_no_emotion_profile_in_merged`：emotion_profiles 表不再存在，测试逻辑需调整

5. **`test_recall.py`**（`nm_with_llm` fixture）：
   - Mock LLM 返回含 `profile_updates`，需改为新格式

## 5. 测试代码规范

遵循项目现有测试模式：

```python
# 文件级 Mock LLM：每个测试文件定义自己的 MockLLMProvider
class MockLLMProvider(LLMProvider):
    def __init__(self, response: str = ""):
        self._response = response
    async def chat(self, messages, temperature=0.1, max_tokens=2048) -> str:
        return self._response

# fixture 使用 conftest.py 的 db_session, mock_embedding
# 也可使用 conftest.py 的 nm fixture（完整 NeuroMemory 实例）

# helper 函数用于重复操作
async def _insert_trait_row(db_session, mock_embedding, *, user_id, content, ...):
    ...

# 测试组织：使用 class 分组相关测试或平铺
class TestProfileView:
    @pytest.mark.asyncio
    async def test_xxx(self, db_session, mock_embedding):
        ...

# 直接 SQL 验证数据库状态
rows = await db_session.execute(
    text("SELECT ... FROM memories WHERE ..."),
    {"uid": user_id},
)
```

## 6. 测试执行计划

### 阶段 1: 编写新功能测试（T7 任务）
1. 创建 `tests/test_profile_unification.py`：覆盖 S1-S3 的所有新功能测试
2. 创建 `tests/test_migration_profile.py`：覆盖 S4 迁移脚本测试

### 阶段 2: 修改现有测试（T7 任务，与新测试一起）
1. 更新 `test_memory_extraction.py` 的 profile_updates 相关测试
2. 更新 `test_reflection.py` 的 emotion_profile 相关测试
3. 更新 `test_reflect_watermark.py` 的 watermark 读取
4. 更新 `test_recall_emotion.py` 的 emotion_profiles 表依赖
5. 更新 `test_recall.py` 的 nm_with_llm fixture

### 阶段 3: 运行全量测试（T8 任务）
```bash
# 新功能测试
pytest tests/test_profile_unification.py -v
pytest tests/test_migration_profile.py -v

# 修改后的回归测试
pytest tests/test_memory_extraction.py -v
pytest tests/test_reflection.py -v
pytest tests/test_reflect_watermark.py -v
pytest tests/test_recall_emotion.py -v
pytest tests/test_recall.py -v

# 全量回归
pytest tests/ -v
```

### 阶段 4: Cloud 端测试
```bash
cd D:/CODE/neuromem-cloud/server
pytest tests/test_one_llm_mode.py -v
pytest tests/ -v
```

## 7. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| emotion_profiles 表删除导致现有测试批量失败 | 高 | 测试修改与代码修改同步进行 |
| 迁移脚本在有大量数据时超时 | 中 | 迁移测试包含批量数据场景 |
| Cloud 旧版 SDK 兼容性断裂 | 高 | 测试 backward_compat：旧格式静默忽略 |
| profile_view 性能回退 | 中 | 集成测试验证并行执行 |
| watermark 迁移后 digest 重复处理 | 高 | 迁移测试验证 watermark 精确转移 |

## 8. 验收标准

- [ ] 所有 P0 测试用例编写并通过
- [ ] 所有 P1 测试用例编写并通过
- [ ] 全量回归测试（`pytest tests/ -v`）零失败
- [ ] Cloud 端测试（`pytest tests/ -v`）零失败
- [ ] 迁移脚本 dry-run 和实际执行均通过
- [ ] 无 `profile_updates` 相关代码残留（grep 验证）
- [ ] 无 `_update_emotion_profile` 相关代码残留
- [ ] `emotion_profiles` 表仅在迁移脚本中被引用（用于读取旧数据）
