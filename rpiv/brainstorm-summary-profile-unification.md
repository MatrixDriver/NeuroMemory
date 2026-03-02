---
description: "需求摘要: Profile 统一架构 - 消除三套平行用户画像机制"
status: pending
created_at: 2026-03-02T20:00:00
updated_at: 2026-03-02T20:00:00
archived_at: null
---

## 需求摘要

### 产品愿景
- **核心问题**：系统中存在三套平行机制（KV Profile、Emotion Profile、v2 Trait）描述"用户是谁"，数据源分裂、质量参差，KV Profile 基于单次 LLM 推断（r=0.27），违背 v2 "trait 必须归纳产生"的科学原则
- **价值主张**：统一为 fact + trait + 计算视图的单一数据流架构，让每条用户画像数据都有明确的来源、置信度和证据链，实现高质量记忆
- **目标用户**：neuromem SDK 和 Cloud 的开发者与集成方
- **产品形态**：SDK 内部架构重构 + Cloud extraction prompt 同步改造，有破坏性 API 变更

### 核心场景（按优先级排序）
1. **Ingest 流程改造**：去掉 profile_updates 提取，identity/occupation 合入 fact
2. **Recall 流程改造**：`_fetch_user_profile()` 替换为 `profile_view()`，从 fact + trait 实时组装
3. **Digest/Reflect 流程改造**：删除 emotion profile 更新，情绪模式归入 trait，watermark 迁入 reflection_cycles
4. **数据迁移**：KV profile → fact/trait，emotion macro → trait，提供迁移脚本
5. **Cloud 适配**：extraction_prompt、core.py、schemas 同步去掉 profile_updates

### 产品边界
- **MVP 范围内**：5 个核心场景全部完成，SDK + Cloud 同步改造
- **明确不做**：Me2 适配（后续单独处理）、profile_view 缓存（延迟决策）
- **后续版本考虑**：Me2 前端 ProfileSection 改造、性能优化

### 已知约束
- 有破坏性 API 变更，需要版本号跳升
- Cloud 的 One-LLM 模式 prompt 需同步修改
- 迁移脚本需要处理现有用户数据

### 各场景功能要点

#### 场景1：Ingest 流程改造
- **功能点**：extraction prompt 删除 `profile_updates` 块；identity/occupation 作为带 `metadata_.category` 的普通 fact 提取；删除 `_store_profile_updates()` 方法及 `_PROFILE_OVERWRITE_KEYS`/`_PROFILE_APPEND_KEYS` 常量
- **关键交互**：LLM extraction 输出结构从 `{facts, episodes, triples, profile_updates}` 简化为 `{facts, episodes, triples}`；fact 的 extraction prompt 中增加 category 指引（identity/occupation/general）
- **异常处理**：如 LLM 未标注 category，默认为 general；空 identity/occupation 不创建 fact

#### 场景2：Recall 流程改造
- **功能点**：新增 `profile_view(user_id)` 方法，从 fact（最新 identity/occupation）+ trait（emerging+ 阶段）+ 近期 episodic emotion metadata 实时组装；返回结构区分数据源：`{"facts": {...}, "traits": {...}, "recent_mood": {...}}`，每个条目附带 source/confidence
- **关键交互**：recall() 返回值中 `user_profile` 字段结构变更；profile_view 与 vector search 并行执行
- **异常处理**：新用户无 trait 时 traits 部分为空，仅返回 facts；无 emotion 数据时 recent_mood 为 null

#### 场景3：Digest/Reflect 流程改造
- **功能点**：删除 `_update_emotion_profile()` 方法；emotion macro（dominant_emotions、emotion_triggers）由 reflection engine 以 trait 形式产生（情境化 trait，如"工作场景下倾向焦虑"）；meso 情绪状态改为 recall 时从近期 episodic 的 emotion metadata 实时聚合；`last_reflected_at` watermark 迁入 reflection_cycles 表
- **关键交互**：digest() 返回值去掉 `emotion_profile` 字段；reflection engine 需增加情绪模式识别能力
- **异常处理**：迁移期间 watermark 不丢失，确保不重复处理已分析的记忆

#### 场景4：数据迁移
- **功能点**：提供迁移脚本，KV profile 中 identity/occupation → fact（带 category metadata），interests/preferences/values/personality → behavior trait（trend 阶段，低置信度）；emotion_profiles 中 macro 字段 → trait；watermark → reflection_cycles；迁移完成后删除 emotion_profiles 表，清理 KV profile namespace
- **关键交互**：迁移脚本为独立可执行脚本，支持 dry-run 模式预览变更
- **异常处理**：迁移失败可回滚（事务保护）；空值字段跳过不迁移

#### 场景5：Cloud 适配
- **功能点**：extraction_prompt.py 中 SDK 模式和 One-LLM 模式的 prompt 同步去掉 profile_updates；core.py 中 `ingest_extracted` 去掉 profile_updates 处理逻辑；schemas.py 清理 profile 相关 schema
- **关键交互**：Cloud 与 SDK 的 extraction 输出结构保持一致
- **异常处理**：Cloud 端需兼容旧版 SDK 客户端可能仍发送 profile_updates 的情况（静默忽略）

### 关键设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| fact category 存储 | metadata JSONB | 低频查询，不值得加列 |
| identity/occupation 覆写语义 | 追加不覆写，取最新 | 记忆不应被悄悄覆写，历史轨迹有价值 |
| profile_view 返回结构 | 区分数据源 + 置信度 | 调用方需知道数据可信度以组装更好的 prompt |
| profile_view 缓存 | 延迟决策 | 先不缓存，等性能测试后再定 |
| emotion macro | 归入 trait | "工作话题容易焦虑"本质就是情境化 trait |
| emotion meso | recall 时实时聚合 | 近期情绪是临时状态，不需要持久化存储 |
| watermark | 迁入 reflection_cycles | 纯运维字段，不属于用户画像 |
| 现有数据 | 迁移转化 | 保留历史积累，但降低置信度等待 reflection 验证 |
