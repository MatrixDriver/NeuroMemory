---
title: "记忆分类 V2 远期演进功能（P2）"
type: feature
status: open
priority: low
created_at: 2026-03-01T20:00:00
updated_at: 2026-03-03T23:00:00
---

# 记忆分类 V2 远期演进功能（P2）

## 动机与背景

V2 核心已实现，P1 中期功能待推进。以下 7 个 P2 功能是更长远的演进方向，涉及新的记忆类型、高级反思机制和群体智能，需要更多数据积累和架构评估后再启动。

来源：`docs/design/memory-classification-v2.md` §8.3

## 功能清单

### 1. 记忆间横向关联（Zettelkasten 模式）

- **描述**：记忆之间建立横向关联，形成自组织的知识网络，而非纯层级结构
- **理论依据**：Generative Agents #02 + MemGPT #03 + A-MEM (NeurIPS 2025)
- **涉及文件**：`models/memory.py`（metadata 预留 `related_memories` 字段）、`services/reflection.py`（关联发现）
- **MVP**：metadata 中增加 `related_memories: list[UUID]`；reflection 时识别语义相近的记忆并建立双向关联

### 2. 两阶段反思

- **描述**：reflection 改为"先提问再检索验证"模式，提高反思质量
- **理论依据**：Stanford Generative Agents 的反思机制
- **涉及文件**：`services/reflection.py`（重构反思流程为两阶段）
- **MVP**：第一阶段 LLM 生成"关于该用户的关键问题"；第二阶段针对问题检索相关记忆并生成结论

### 3. Zep 双时间线

- **描述**：fact 区分"事件时间"（事情发生的时间）和"系统时间"（记录到系统的时间）
- **理论依据**：商业系统调研 #04（Zep AI / Graphiti）
- **涉及文件**：`models/memory.py`（增加 `event_time` 字段）、`services/memory_extraction.py`（提取时解析时间表达）
- **MVP**：fact/episodic 增加 `event_time` 字段；LLM 提取时尝试解析对话中的时间表达

### 4. 程序性记忆

- **描述**：捕获用户的工作流程和交互模式（如"写代码前总是先画架构图"），区别于 behavior trait
- **理论依据**：认知心理学调研 #01（Tulving 长时记忆分类中的程序性记忆）
- **涉及文件**：可能需要新增 memory_type `procedural`，或作为 trait 的特殊子类
- **MVP**：待设计——需要明确程序性记忆与 behavior trait 的边界

### 5. 前瞻记忆

- **描述**：捕获用户的未来意图和目标（如"计划明年考 AWS 认证"）
- **理论依据**：认知心理学调研 #01
- **涉及文件**：可能需要新增 memory_type `prospective`，或作为 episodic 的子类
- **MVP**：待设计——需要明确生命周期（目标完成后如何处理）

### 6. 跨用户 trait 模式发现

- **描述**：从多用户的 trait 数据中发现群体级模式（如"程序员群体中 85% 偏好深色主题"）
- **涉及文件**：需要新增聚合分析服务，可能在 cloud 层实现而非 SDK 层
- **MVP**：待设计——涉及隐私和数据伦理问题，需要匿名化处理

### 7. 基于 trait 的主动行为预测

- **描述**：利用已有 trait 预测用户可能的行为或需求，实现主动推荐
- **涉及文件**：需要新增预测服务
- **MVP**：待设计——需要明确预测的边界，避免"恐怖谷"效应

## 用户场景

1. **场景 A**：用户多次提到不同技术栈，系统通过横向关联发现"用户在构建全栈应用"
2. **场景 B**：用户说"上周参加了 Python meetup"，系统区分事件时间（上周）和记录时间（今天）
3. **场景 C**：用户反复执行"先搜文档 → 写 POC → 提交 PR"的流程，系统捕获为程序性记忆

### 8. 实体摘要（Entity Summaries）

- **描述**：为高频出现的实体（人物、组织、项目）自动生成摘要
- **理论依据**：Generative Agents #02（Hindsight 的 Entity Summaries）
- **涉及文件**：`services/graph_memory.py`（当前只有 `find_entity_facts()`，无摘要生成）
- **MVP**：待设计——需要定义摘要触发条件和生成频率

### 9. ~~recall 情绪因子（Emotion Matching Factor）~~ ✓ 已实现 2026-03-03

- **描述**：recall 评分中增加情绪匹配因子（当前对话情绪与记忆情绪的一致性加成）
- **理论依据**：认知心理学调研 #01（杏仁核介导的情绪记忆增强效应）
- **涉及文件**：`services/search.py`（scored_search 新增 `current_emotion` 参数 + emotion_match bonus 0~0.10）、`_core.py`（recall 透传 current_emotion）
- **MVP**：emotion_match = 0.10 × (1 - valence-arousal 欧式距离 / 2.83)，在 final score 公式中叠加

### 10. ~~behavior_kind 区分（Pattern vs Procedural）~~ ✓ 已实现 2026-03-03

- **描述**：behavior trait 内部增加 `behavior_kind` 字段，区分统计规律型（"深夜活跃"）和操作流程型（"先画架构图再写代码"）
- **理论依据**：认知心理学调研 #01
- **涉及文件**：`services/reflection.py`（prompt 新增 behavior_kind 指导 + 调用传参）、`services/trait_engine.py`（create_behavior 新增 behavior_kind 参数，存入 metadata_）
- **MVP**：`metadata_.behavior_kind = "pattern" | "procedural"`，由 LLM 反思时推断

### 11. ~~fact_temporality 区分（Current/Prospective/Historical）~~ ✓ 已实现 2026-03-03

- **描述**：fact 增加 `temporality` 字段，区分当前事实、未来意图、已过时事实
- **理论依据**：认知心理学调研 #01
- **涉及文件**：`services/memory_extraction.py`（中英文 prompt 新增 temporality 必填字段 + _store_facts 存入 metadata_）
- **MVP**：`metadata_.temporality = "current" | "prospective" | "historical"`，LLM 提取时标注

## 备选方案

无

## 参考

- 设计文档：`docs/design/memory-classification-v2.md` §8.3
- TODO 文档：`docs/design/TODO-memory-v2.md`（P2-6~P2-9 额外项）
- 调研报告：`docs/design/research/01-cognitive-psychology.md`、`02-generative-agents.md`、`03-memgpt-letta.md`、`04-commercial-systems.md`
