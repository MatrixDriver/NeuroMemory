# NeuroMemory LoCoMo 优化历程

## 成绩总览

| 轮次 | 日期 | 改进项 | Overall Judge | 提升 |
|:---:|:---:|------|:---:|:---:|
| 1 | 02-15 | Baseline（无优化） | 0.125 | — |
| 2 | 02-16 | 独立评测DB、后台任务+embedding缓存、只提取user消息、多用户隔离修复、事务原子性、图谱批量去重、embed_batch批量调用 | 0.274 | +119% |
| 3 | 02-17 | Conv 8-9 数据完整性修复 | 0.431 | +57% |
| 4 | 02-17 | 时间戳提取系统、pg_search BM25、情感感知衰减、RRF混合排序、PostgreSQL 18升级 | 0.610 | +42% |
| 5 | 02-18 | 移除emotion profile/2-hop graph、Answer prompt优化、图谱context注入 | 0.585 | -4% |
| 6 | 02-18 | 评测pipeline移除reflect | 0.580 | -1% |
| 7 | 02-19 | 用户画像提取注入(6 KV键)、Recall Limit 10→20、Graph实体匹配(无LLM) | 0.704 | +21% |
| 8 | 02-19 | Episodic boost + enriched recall context | 0.704 | 0% |
| 9 | 02-20 | （同 R8 pipeline，验证性重跑） | 0.704 | 0% |
| 10 | 02-20 | （checkpoint保存，judge score从R11反推） | 0.704 | 0% |
| 11 | 02-21 | 时序查询过滤（query提取时间范围，episodic按时间窗口过滤） | 0.714 | +1.4% |
| 12 | 02-21 | 并行化评测pipeline（ingest/query/evaluate三阶段）+ OpenAI embedding支持 | 0.802 | +12.3% |
| **13** | **02-21** | **Profile重构：preferences合并进profile namespace** | **0.8017** | **≈0%** |

> 累计提升：0.125 → 0.8017（**+541%**）

## 分类成绩对比

| 轮次 | Single-Hop (Cat1) | Temporal (Cat2) | Open-Domain (Cat3) | Multi-Hop (Cat4) | Overall |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 4 (BM25) | 0.645 | 0.574 | 0.417 | 0.612 | 0.610 |
| 7 (画像+图谱) | 0.749 | 0.596 | 0.573 | 0.737 | 0.704 |
| 11 (时序过滤) | ~0.749 | **0.652** | ~0.573 | ~0.786 | 0.714 |
| 13 (当前最优) | **0.871** | **0.716** | **0.819** | **0.809** | **0.8017** |
| R7→R13 变化 | +0.122 | +0.120 | +0.246 | +0.072 | +0.098 |

> R11 分类数据部分为估算（commit message 仅记录 Temporal +0.198、Multi-Hop +0.049）

## 与其他框架对比

| 框架 | Single-Hop | Multi-Hop | Open-Dom | Temporal | Overall | Judge LLM |
|------|:---:|:---:|:---:|:---:|:---:|:---:|
| Backboard | 89.4% | 75.0% | 91.2% | 91.9% | 90.0% | GPT-4.1 |
| Memobase v0.0.37 | 70.9% | 46.9% | 77.2% | 85.1% | 75.8% | ? |
| Zep | 74.1% | 66.0% | 67.7% | 79.8% | 75.1% | ? |
| Letta (GPT-4o-mini) | — | — | — | — | 74.0% | GPT-4o-mini |
| **NeuroMemory (R13)** | **87.1%** | **80.9%** | **81.9%** | **71.6%** | **80.2%** | **DeepSeek** |
| Mem0-Graph | 65.7% | 47.2% | 75.7% | 58.1% | 68.4% | GPT-4o-mini |
| Mem0 | 67.1% | 51.2% | 72.9% | 55.5% | 66.9% | GPT-4o-mini |
| LangMem | 62.2% | 47.9% | 71.1% | 23.4% | 58.1% | GPT-4o-mini |
| OpenAI Memory | 63.8% | 42.9% | 62.3% | 21.7% | 52.9% | GPT-4o-mini |

> 注：各框架使用不同的 Judge LLM，分数不完全可比。NeuroMemory 使用成本较低的 DeepSeek-chat。

## 各轮改进详情

### 第2轮：基础设施与性能（02-16）

| 改进 | 说明 |
|------|------|
| 独立评测数据库 | neuromemory_eval 隔离，避免污染开发数据 |
| 后台任务 + embedding 缓存 | recall 性能优化，避免重复计算 |
| 只对 user 消息提取记忆 | assistant 消息不提取，减少噪音 |
| 多用户隔离修复 | 图谱 user_id 隔离 bug 修复 |
| 事务原子性 | 记忆提取失败不留脏数据 |
| 图谱批量去重 | 避免重复 triple 写入 |
| embed_batch 批量调用 | facts/episodes 一次性批量 embedding |

### 第3轮：数据完整性（02-17）

修复评测框架 bug，确保 10 个 conv 全部完整入库。

### 第4轮：检索引擎升级（02-17）

| 改进 | 说明 |
|------|------|
| 时间戳提取系统 | TemporalExtractor 纯 Python 规则引擎，3 级解析（LLM ISO → LLM 文本 regex → 内容提取） |
| pg_search BM25 | ParadeDB Tantivy 替代 PostgreSQL tsvector，关键词匹配更精准 |
| 情感感知衰减 | arousal 值减缓 recency 衰减，高情感记忆保持更久 |
| RRF 混合排序 | 向量相似度 + BM25 通过 Reciprocal Rank Fusion 融合 |
| PostgreSQL 18 升级 | ParadeDB PG18 + pgvector 0.8.1 + AGE 1.7.0 |

### 第5-6轮：Pipeline 简化（02-18）

移除 emotion profile 注入、2-hop graph 遍历、reflect 阶段。单独看为负优化，但简化了 pipeline，减少了噪音干扰，为第7轮奠定基础。

### 第7轮：画像 + 图谱 + 扩容（02-19）

| 改进 | 说明 |
|------|------|
| 用户画像提取注入 | 6 个 KV 键（identity/occupation/interests/values/relationships/personality），写时提取，读时注入 answer prompt |
| Recall Limit 10→20 | 提供更多上下文，全面提升各类别 |
| Graph 实体匹配 | 子串匹配已知 graph_nodes 实体，无 LLM 依赖，multi-hop +0.125，仅 +25ms 开销 |

### 第8-10轮：Episodic Boost 探索（02-19 ~ 02-20）

| 改进 | 说明 |
|------|------|
| Episodic boost | 提升 episode 类记忆在 recall 中的权重 |
| Enriched recall context | 为 answer prompt 提供更丰富的记忆上下文 |

结果：Judge 无提升（0.704 持平）。R8-R10 为验证性测试，checkpoint 保存于 `locomo_query_checkpoint.json.r10`，judge score 从 R11 commit 反推。

### 第11轮：时序查询过滤（02-21）

| 改进 | 说明 |
|------|------|
| 时间范围提取 | 从 query 中提取时间范围（"in June"、"during 2023"）via TemporalExtractor |
| Episodic 时间窗口过滤 | 时序类查询：episodic 记忆按时间范围过滤，facts 正常向量检索 |
| Answer prompt 格式说明 | 新增 MEMORY FORMAT 章节，说明日期/情感前缀含义 |

效果：Temporal +0.198（0.454→0.652），Multi-Hop +0.049。Overall 0.704→0.714（+1.4%）

### 第12轮：并行化评测 Pipeline（02-21）

| 改进 | 说明 |
|------|------|
| 三阶段并行化 | ingest / query / evaluate 全部并行，可配置并发数（--ingest-concurrency 等） |
| 指数退避重试 | 429/502/503 错误自动重试，避免 rate limit 中断 |
| OpenAI embedding 支持 | 新增 embedding_base_url 配置，支持 OpenAI 兼容 proxy |

效果：Overall 0.714→0.802（+12.3%）。**注意**：此轮分数跃升部分原因可能是并行加速后 ingest 更完整，或 embedding proxy 质量差异，需关注。

### 第13轮：Profile 重构（02-21）

将 `preferences` namespace 合并进 `profile`，无功能性变化。验证重构不影响成绩。

效果：0.8017，与 R12（0.802）持平。

## 尝试但回退的实验

| 实验 | 测试结果 | 回退原因 |
|------|---------|---------|
| 规则化 Query 分类 | Judge -0.013 | Open-domain BM25 权重 0.3 过激 |
| 读时记忆去重 (cosine>0.92) | Judge -0.033 | 丢失重复 fact 的"投票"信号，single-hop 下降 |

## 待优化方向

当前最弱项：**Temporal（71.6%）**，与 Backboard（91.9%）差距最大。

- **Temporal 提升**：时序推理仍不足，考虑更精确的时间范围提取和跨对话时间对齐
- **逼近 Backboard（90%）**：Single-Hop（87.1%）接近，Multi-Hop（80.9%）和 Open-Domain（81.9%）还有空间
- 写时记忆去重（解决冗余率，每条仅增加 ~10ms）
- 换用 GPT-4o-mini 作为 Judge 进行公平对比
- 提升 extraction 质量（更精确的 fact/episode 提取）
