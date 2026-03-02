---
description: "测试规格与验收标准: Profile 统一架构"
status: archived
created_at: 2026-03-02T21:30:00
updated_at: 2026-03-02T14:45:30
---

# 测试规格与验收标准: Profile 统一架构

本文档基于 PRD 和测试策略，为每个功能点定义精确的测试规格、输入/输出、验收标准。

---

## 1. Ingest 流程改造（PRD 7.1）

### TC-1.1: extraction prompt 输出不含 profile_updates

**前提条件**：MockLLM 返回新格式 `{facts, episodes, triples}`（不含 profile_updates）
**测试步骤**：
1. 创建 `MemoryExtractionService` 实例
2. 构造对话消息列表
3. 调用 `extract_from_messages()`
**验收标准**：
- `result["facts_extracted"]` >= 1
- `result["episodes_extracted"]` >= 0
- 无 `profile_updates` 相关处理日志
- 无异常抛出

### TC-1.2: identity 信息作为带 category 的 fact 提取

**前提条件**：MockLLM 返回 `{"facts": [{"content": "用户名叫张三", "category": "identity", "confidence": 0.95}], "episodes": [], "triples": []}`
**测试步骤**：
1. 调用 `extract_from_messages()`
2. 查询数据库 `memories` 表
**验收标准**：
- DB 中存在 `memory_type='fact'` 的记录
- 该记录 `metadata_->>'category'` = `'identity'`
- 不存在 KV namespace='profile', key='identity' 的记录

### TC-1.3: occupation 信息作为带 category 的 fact 提取

**前提条件**：MockLLM 返回含 `"category": "occupation"` 的 fact
**验收标准**：同 TC-1.2，category 为 'occupation'

### TC-1.4: LLM 仍返回 profile_updates 时静默忽略

**前提条件**：MockLLM 返回旧格式 `{facts: [...], episodes: [], triples: [], profile_updates: {identity: "张三"}}`
**测试步骤**：
1. 调用 `extract_from_messages()`
**验收标准**：
- 不抛出异常
- facts 正常提取和存储
- 不存在 KV profile 写入（`_store_profile_updates` 已删除）
- 不存在 AttributeError 或 KeyError

### TC-1.5: category 缺失时默认为 general

**前提条件**：MockLLM 返回 `{"facts": [{"content": "喜欢蓝色", "confidence": 0.8}], ...}`（无 category 字段）
**验收标准**：
- DB 中 fact 记录的 `metadata_->>'category'` = `'general'` 或 category 字段不存在（取决于实现）

### TC-1.6: _parse_classification_result 输出格式

**测试步骤**：
1. 用各种 JSON 格式调用 `_parse_classification_result()`
**验收标准**：
- 返回 dict 含 keys: `facts`, `episodes`, `triples`
- 不含 `profile_updates` key

### TC-1.7: 已删除的方法和常量不存在

**测试步骤**：
1. 检查 `MemoryExtractionService` 是否有 `_store_profile_updates` 属性
2. 检查 `MemoryExtractionService` 是否有 `_PROFILE_OVERWRITE_KEYS` 属性
3. 检查 `MemoryExtractionService` 是否有 `_PROFILE_APPEND_KEYS` 属性
**验收标准**：
- `hasattr()` 全部返回 `False`

### TC-1.8: 完整 ingest 流程不写入 KV profile

**前提条件**：使用 `nm` fixture（完整 NeuroMemory 实例）
**测试步骤**：
1. 调用 `nm.ingest(user_id, role="user", content="我在 Google 工作，名叫张三")`
2. 等待后台 extraction 完成
3. 查询 KV 存储中 namespace='profile' 的所有记录
**验收标准**：
- KV profile namespace 无记录（或 identity/occupation key 不存在）

---

## 2. profile_view() 方法（PRD 7.2）

### TC-2.1: 返回结构正确

**前提条件**：
- 存在 facts: 1 条 identity fact + 1 条 occupation fact
- 存在 traits: 1 条 emerging behavior trait
- 存在 episodic: 2 条带 emotion metadata 的 episodic（最近 14 天内）
**测试步骤**：
1. 插入上述数据
2. 调用 `nm.profile_view(user_id)`
**验收标准**：
- 返回 dict 含 keys: `facts`, `traits`, `recent_mood`
- `result["facts"]` 是 dict，含 `identity` 和 `occupation` key
- `result["traits"]` 是 list，每项含 `content`, `subtype`, `stage`, `confidence`, `context`
- `result["recent_mood"]` 是 dict，含 `valence_avg`, `arousal_avg`, `sample_count`, `period`

### TC-2.2: facts 取最新的 identity/occupation

**前提条件**：
- 先插入 `"在 Google 工作"` fact (category=occupation)
- 后插入 `"跳槽到 Meta"` fact (category=occupation)
**验收标准**：
- `result["facts"]["occupation"]` 包含 "Meta" 相关内容
- Google 的 fact 不覆盖 Meta（追加不覆写，取最新）

### TC-2.3: traits 只含 emerging 及以上阶段

**前提条件**：
- 插入 trend 阶段 trait
- 插入 emerging 阶段 trait
- 插入 established 阶段 trait
- 插入 dissolved 阶段 trait
**验收标准**：
- `result["traits"]` 不含 trend 阶段 trait
- `result["traits"]` 不含 dissolved 阶段 trait
- 含 emerging 和 established 阶段 trait
- 按 `trait_confidence DESC` 排序

### TC-2.4: traits 条目含 confidence 和 source

**验收标准**：
- 每个 trait 条目有 `confidence` 字段（float）
- 每个 trait 条目有 `context` 字段（string）

### TC-2.5: recent_mood 从近期 episodic 聚合

**前提条件**：
- 插入 3 条最近 7 天的 episodic，emotion metadata: valence=-0.3, -0.5, -0.1
- 插入 1 条 30 天前的 episodic（应被排除）
**验收标准**：
- `result["recent_mood"]["sample_count"]` = 3（不含 30 天前的）
- `result["recent_mood"]["valence_avg"]` 约等于 -0.3
- `result["recent_mood"]["period"]` = "last_14_days"

### TC-2.6: 新用户返回空数据

**前提条件**：不插入任何数据
**验收标准**：
- `result["facts"]` 为空 dict `{}`
- `result["traits"]` 为空 list `[]`
- `result["recent_mood"]` 为 `None`

### TC-2.7: 无 emotion 数据时 recent_mood 为 None

**前提条件**：只有 fact 记忆，无 episodic 记忆或 episodic 无 emotion metadata
**验收标准**：
- `result["recent_mood"]` is `None`

### TC-2.8: _fetch_user_profile 已删除或重定向

**测试步骤**：
1. 检查 `NeuroMemory` 实例是否有 `_fetch_user_profile` 方法
**验收标准**：
- 方法不存在（`hasattr` 返回 `False`）或调用会委托到 `profile_view()`

### TC-2.9: recall() 返回 profile_view 结构

**前提条件**：
- 插入 identity fact + occupation fact + emerging trait
**测试步骤**：
1. 调用 `nm.recall(user_id, query)`
**验收标准**：
- `result["user_profile"]` 含 `facts`, `traits`, `recent_mood` 三个 key
- 不再是旧的 flat dict（identity/occupation/interests/... 直接作为 key）

### TC-2.10: recall 中 profile_view 与 vector search 并行

**测试步骤**：（性能测试，P1）
1. 计时 recall() 调用
2. 分别计时 profile_view() 和 vector search
**验收标准**：
- recall 总耗时不明显超过两者中较长者（表明并行执行）

### TC-2.11: profile_view 作为独立公共方法可调用

**测试步骤**：
1. 直接调用 `nm.profile_view(user_id)`
**验收标准**：
- 返回正确结构，不依赖 recall 上下文
- 方法存在于 `NeuroMemory` 公共 API

---

## 3. Digest/Reflect 流程改造（PRD 7.3）

### TC-3.1: digest() 不写入 emotion_profiles 表

**前提条件**：插入若干 episodic 记忆（带 emotion metadata）
**测试步骤**：
1. 调用 `nm.digest(user_id)`
2. 查询 `emotion_profiles` 表（如果表还存在）
**验收标准**：
- `emotion_profiles` 表中无该 user_id 的记录
- 如果 `emotion_profiles` 表已删除，验证不抛出"表不存在"错误（说明代码不再引用该表）

### TC-3.2: digest() 返回值不含 emotion_profile

**测试步骤**：
1. 调用 `nm.digest(user_id)`
**验收标准**：
- 返回 dict 含 `memories_analyzed`, `insights_generated`, `insights`
- 不含 `emotion_profile` key

### TC-3.3: _update_emotion_profile 方法已删除

**测试步骤**：
1. 检查 `ReflectionService` 是否有 `_update_emotion_profile` 属性
**验收标准**：
- `hasattr()` 返回 `False`

### TC-3.4: 情绪模式以情境化 trait 产生

**前提条件**：
- MockLLM 配置返回含情绪模式识别的反思结果
- 插入若干带负面情绪 metadata 的 episodic 记忆
**测试步骤**：
1. 调用 `nm.digest(user_id)`
2. 查询 DB 中 `memory_type='trait'` 的记录
**验收标准**：
- 存在情绪相关 trait（如 content 含"焦虑"/"stress" 相关内容）
- trait 有 `trait_context` 标注（非空）
- trait 的 `trait_stage` = 'trend'（新产生的 trait 初始阶段）
- trait 的 `trait_subtype` = 'behavior'

### TC-3.5: watermark 存储在 reflection_cycles 表

**测试步骤**：
1. 调用 `nm.digest(user_id)`
2. 查询 `reflection_cycles` 表
**验收标准**：
- 存在 `user_id` 匹配的 reflection_cycle 记录
- 记录 status = 'completed'
- `completed_at` 不为 null

### TC-3.6: watermark 增量处理正确

**测试步骤**：
1. 插入 3 条记忆，调用 `digest()` → 处理 3 条
2. 插入 2 条新记忆，再次调用 `digest()` → 应只处理 2 条（+ 第一次 digest 产生的 trait insights）
**验收标准**：
- 第二次 `digest()` 的 `memories_analyzed` >= 2（新增的 2 条 + 可能的 trait insights）
- 第一次的 3 条记忆不被重复处理

### TC-3.7: 多次 digest 后收敛

**测试步骤**：
1. 插入记忆，调用 digest 3 次
**验收标准**：
- 第三次 digest 的 `memories_analyzed` = 0 或 `insights_generated` = 0
- LLM 不再被调用（或调用次数为 0）

---

## 4. 数据迁移（PRD 7.4）

### TC-4.1: KV identity 迁移为 fact

**前提条件**：KV 中存在 `namespace='profile', key='identity', value='张三'`
**测试步骤**：执行迁移脚本
**验收标准**：
- `memories` 表新增 `memory_type='fact'` 记录
- `metadata_->>'category'` = 'identity'
- `metadata_->>'source'` = 'migration'
- content 含"张三"

### TC-4.2: KV occupation 迁移为 fact

**验收标准**：同 TC-4.1，category='occupation'

### TC-4.3: KV preferences 迁移为 behavior trait

**前提条件**：KV 中存在 `key='preferences', value=["喜欢蓝色", "爱吃火锅"]`
**验收标准**：
- 创建 2 条独立的 trait 记录
- `trait_subtype` = 'behavior'
- `trait_stage` = 'trend'
- `trait_confidence` = 0.2
- `metadata_->>'source'` = 'migration'

### TC-4.4: KV interests 迁移为 behavior trait

**验收标准**：同 TC-4.3

### TC-4.5: KV values 迁移为 behavior trait

**前提条件**：KV 中 `key='values', value=["追求效率", "重视家庭"]`
**验收标准**：
- trait_context = 'general'
- 其余同 TC-4.3

### TC-4.6: KV personality 迁移为 behavior trait

**验收标准**：同 TC-4.3

### TC-4.7: emotion macro dominant_emotions 迁移为 trait

**前提条件**：`emotion_profiles` 中 `dominant_emotions = {"焦虑": 0.6, "兴奋": 0.3}`
**验收标准**：
- 创建对应的 trait 记录
- 内容描述情绪模式
- `trait_stage` = 'trend'
- 低置信度

### TC-4.8: emotion macro emotion_triggers 迁移为 trait

**前提条件**：`emotion_triggers = {"工作": {"valence": -0.6}}`
**验收标准**：
- trait content 描述情绪触发关系（如"工作话题引发负面情绪"）
- `trait_context` 从 trigger 话题推断（如 'work'）

### TC-4.9: watermark 迁移到 reflection_cycles

**前提条件**：`emotion_profiles.last_reflected_at` = `'2026-03-01 12:00:00+08'`
**验收标准**：
- `reflection_cycles` 表新增记录
- `trigger_type` = 'migration'
- `completed_at` 等于原 `last_reflected_at` 值
- `status` = 'completed'

### TC-4.10: 空值字段不迁移

**前提条件**：KV 中 `key='identity', value=None`
**验收标准**：
- 不创建对应 fact 记录

### TC-4.11: dry-run 不写入数据库

**测试步骤**：
1. 插入 KV profile 数据
2. 以 `--dry-run` 执行迁移脚本
3. 检查 `memories` 表
**验收标准**：
- `memories` 表无新增记录
- 脚本输出预览信息（迁移计划摘要）

### TC-4.12: 迁移失败可回滚

**测试步骤**：
1. Mock 数据库操作在中途失败
2. 检查是否有部分数据被提交
**验收标准**：
- 事务回滚，无部分提交的数据
- KV 源数据未被删除

### TC-4.13: 迁移幂等

**测试步骤**：
1. 执行迁移
2. 再次执行迁移
**验收标准**：
- 不产生重复的 fact/trait 记录
- 或脚本检测到已迁移并跳过

### TC-4.14: 端到端迁移

**测试步骤**：
1. 插入完整的 KV profile（identity + occupation + preferences + interests + values + personality）
2. 插入 emotion_profiles 记录（含 dominant_emotions + emotion_triggers + last_reflected_at）
3. 执行迁移
4. 调用 `profile_view()` 验证数据可被检索
**验收标准**：
- `profile_view()` 返回的 facts 含迁移的 identity/occupation
- `profile_view()` 返回的 traits 含迁移的 preferences 等（如果 emerging+ 阶段）
- 注意：迁移的 trait 为 trend 阶段，profile_view 只返回 emerging+，所以 traits 可能为空（这是正确行为）

### TC-4.15: 迁移后 KV namespace 清理

**测试步骤**：
1. 执行迁移（非 dry-run）
2. 查询 KV 中 namespace='profile' 的记录
**验收标准**：
- namespace='profile' 下无记录

### TC-4.16: 迁移后 recall 正常工作

**测试步骤**：
1. 迁移 KV profile 数据
2. 调用 `nm.recall(user_id, "工作")`
**验收标准**：
- recall 返回结果正常
- `user_profile` 使用新结构
- 迁移的 fact 可被向量搜索检索到

---

## 5. Cloud 适配（PRD 7.5）

### TC-5.1: SDK 模式 extraction prompt 无 profile_updates

**测试步骤**：检查 Cloud `extraction_prompt.py` 中 SDK 模式的 prompt 文本
**验收标准**：
- prompt 中不含 "profile_updates" 字符串
- 返回格式说明只含 `facts`, `episodes`, `triples`

### TC-5.2: One-LLM 模式 extraction prompt 无 profile_updates

**验收标准**：同 TC-5.1，针对 One-LLM 模式的 prompt

### TC-5.3: ingest_extracted 忽略 profile_updates

**前提条件**：调用 `do_ingest_extracted()` 传入含 `profile_updates` 的 data
**验收标准**：
- 不抛出异常
- 返回值不含 `profile_updates_stored` 字段
- facts/episodes 正常存储

### TC-5.4: 旧版 SDK 兼容性

**前提条件**：模拟旧版 SDK 发送含 `profile_updates` 的 API 请求
**验收标准**：
- HTTP 200 响应
- 静默忽略 profile_updates
- 其余字段正常处理

---

## 6. 回归测试修改规格

### TC-6.1: test_memory_extraction.py 修改

**需要修改的测试**：
- `test_extract_memories_from_conversations`：MockLLM 返回去掉 profile_updates，去掉 KV preferences 验证断言
- `test_parse_classification_result`：期望返回值不含 `profile_updates` key
- `test_parse_classification_with_triples`：同上

**新增断言**：
- 验证 fact 带有 category metadata

### TC-6.2: test_reflection.py 修改

**需要修改的测试**：
- `test_reflect_generates_insights`：去掉 `assert "emotion_profile" in result` 断言
- `test_reflect_updates_emotion_profile`：**删除整个测试**或改为验证情绪 trait 产生
- `test_reflect_with_no_emotions_skips_profile_update`：修改为验证无 emotion 数据时无情绪 trait 产生
- `test_reflect_facade_method`：返回值断言去掉 `emotion_profile`

### TC-6.3: test_reflect_watermark.py 修改

**需要修改的测试**：
- `test_reflect_watermark_initial`：watermark 验证改为查询 `reflection_cycles` 表
- `test_reflect_watermark_incremental`：同上
- `test_reflect_watermark_no_new_memories`：同上
- `test_reflect_background`：watermark 验证改为 `reflection_cycles` 表

**具体修改**：将所有
```python
row = await session.execute(
    text("SELECT last_reflected_at FROM emotion_profiles WHERE user_id = :uid"),
    ...
)
```
替换为
```python
row = await session.execute(
    text("SELECT completed_at FROM reflection_cycles WHERE user_id = :uid ORDER BY completed_at DESC LIMIT 1"),
    ...
)
```

### TC-6.4: test_recall_emotion.py 修改

**需要修改的测试**：
- `test_recall_no_emotion_profile_in_merged`：emotion_profiles 表不再存在，删除插入 emotion_profile 的 SQL，修改为验证 merged 中无 emotion_profile source item

### TC-6.5: test_recall.py nm_with_llm fixture 修改

**修改**：MockLLM 返回值去掉 `profile_updates` 字段

---

## 7. 验收标准汇总

### P0 验收条件（必须全部满足）

- [ ] ingest 流程不再产生或存储 profile_updates
- [ ] `_store_profile_updates()`、`_PROFILE_OVERWRITE_KEYS`、`_PROFILE_APPEND_KEYS` 已删除
- [ ] `profile_view()` 返回正确的 `{facts, traits, recent_mood}` 结构
- [ ] recall 返回的 `user_profile` 使用新结构
- [ ] `_fetch_user_profile()` 已删除或替换
- [ ] digest 不再写入 emotion_profiles 表
- [ ] digest 返回值不含 `emotion_profile`
- [ ] `_update_emotion_profile()` 已删除
- [ ] watermark 从 reflection_cycles 表读写
- [ ] 迁移脚本 dry-run 正确
- [ ] 迁移脚本事务保护有效
- [ ] 所有迁移数据类型正确转化（KV -> fact/trait，watermark -> reflection_cycles）
- [ ] Cloud extraction prompt 不含 profile_updates
- [ ] Cloud ingest_extracted 兼容旧版客户端
- [ ] 全量回归测试 `pytest tests/ -v` 零失败
- [ ] Cloud 全量测试零失败

### P1 验收条件

- [ ] fact category 缺失时有合理默认值
- [ ] profile_view traits 按 confidence DESC 排序
- [ ] profile_view recent_mood 排除 14 天前数据
- [ ] 迁移脚本幂等
- [ ] 迁移后 KV profile namespace 清理
- [ ] recall 中 profile_view 与 vector search 并行执行
- [ ] 新用户 profile_view 返回空数据
- [ ] 多次 digest 收敛
