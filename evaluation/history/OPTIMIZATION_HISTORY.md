# neuromem LoCoMo 优化历程

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
| 13 | 02-21 | Profile重构：preferences合并进profile namespace | 0.8017 | ≈0% |
| **14** | **02-22** | **自动后台reflect、并行recall优化、Facts/Episodes提取去重修复、中文时序查询修复** | **0.817** | **+1.9%** |
| 15 | 02-23 | R13基线+去重修复(8f51f1b1)+中文时序修复(a231fc1e)+并行recall/SQL优化(558af7fa,无索引) | 0.792 | -3.1% |
| 16 | 02-23 | 后台异步reflect（reflection_interval=20，每20条消息触发）、去掉召回原始对话消息 | 0.804 | +1.5% |
| 17 | 02-23 | GRAPH_ENABLED=1（图谱三元组提取+结构化关系召回）、图谱显示优化（UUID→可读名称，CUSTOM→原始关系词） | 0.790 | -3.3% |
| 18 | 02-24 | 时间语义分拆（facts/timeline分栏）、Level4时间戳fallback、fact双语格式、去重增量reflect、concept节点过滤 | 0.792 | -3.1% |
| 19 | 02-25 | 提取状态追踪（pending/done/failed）、失败重试API、清空重提取全部消息（0失败 vs R18 581失败） | 0.799 | -2.2% |

> 累计提升：0.125 → 0.817（**+554%**）

## 分类成绩对比

| 轮次 | Single-Hop (Cat1) | Temporal (Cat2) | Open-Domain (Cat3) | Multi-Hop (Cat4) | Overall |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 4 (BM25) | 0.645 | 0.574 | 0.417 | 0.612 | 0.610 |
| 7 (画像+图谱) | 0.749 | 0.596 | 0.573 | 0.737 | 0.704 |
| 11 (时序过滤) | ~0.749 | **0.652** | ~0.573 | ~0.786 | 0.714 |
| 13 | 0.871 | 0.716 | 0.819 | 0.809 | 0.8017 |
| **14 (当前最优)** | **0.829** | **0.766** | **0.811** | **0.843** | **0.817** |
| R13→R14 变化 | -0.042 | +0.050 | -0.008 | +0.034 | +0.015 |
| 15 (R13基线+优化组合) | 0.805 | 0.715 | 0.833 | 0.825 | 0.792 |
| R14→R15 变化 | -0.024 | -0.051 | +0.022 | -0.018 | -0.025 |
| 16 (后台reflect+无原始对话) | 0.812 | 0.766 | 0.832 | 0.815 | 0.804 |
| R14→R16 变化 | -0.017 | 0.000 | +0.021 | -0.028 | -0.013 |
| 17 (GRAPH_ENABLED=1) | 0.787 | 0.755 | 0.833 | 0.822 | 0.790 |
| R14→R17 变化 | -0.042 | -0.011 | +0.022 | -0.021 | -0.027 |
| 18 (时间语义分拆+fact格式+reflect去重) | 0.773 | 0.757 | 0.807 | 0.842 | 0.792 |
| R14→R18 变化 | -0.056 | -0.009 | -0.004 | +0.031 | -0.025 |
| 19 (提取状态追踪+清空重提取) | 0.812 | 0.725 | 0.905 | 0.807 | 0.799 |
| R14→R19 变化 | -0.017 | -0.041 | +0.094 | -0.036 | -0.018 |

> R11 分类数据部分为估算（commit message 仅记录 Temporal +0.198、Multi-Hop +0.049）

## 与其他框架对比

| 框架 | Single-Hop | Multi-Hop | Open-Dom | Temporal | Overall | Judge LLM |
|------|:---:|:---:|:---:|:---:|:---:|:---:|
| memU | — | — | — | — | 92.1% | ? |
| Backboard | 89.4% | 75.0% | 91.2% | 91.9% | 90.0% | GPT-4.1 |
| **neuromem (R14)** | **82.9%** | **84.3%** | **81.1%** | **76.6%** | **81.7%** | **GPT-4o-mini** |
| neuromem (R13) | 87.1% | 80.9% | 81.9% | 71.6% | 80.2% | GPT-4o-mini |
| MemOS | — | — | — | — | 75.8% | ? |
| Memobase v0.0.37 | 70.9% | 46.9% | 77.2% | 85.1% | 75.8% | ? |
| Zep | 74.1% | 66.0% | 67.7% | 79.8% | 75.1% | ? |
| Letta (GPT-4o-mini) | — | — | — | — | 74.0% | GPT-4o-mini |
| Mem0-Graph | 65.7% | 47.2% | 75.7% | 58.1% | 68.4% | GPT-4o-mini |
| Mem0 | 67.1% | 51.2% | 72.9% | 55.5% | 66.9% | GPT-4o-mini |
| LangMem | 62.2% | 47.9% | 71.1% | 23.4% | 58.1% | GPT-4o-mini |
| OpenAI Memory | 63.8% | 42.9% | 62.3% | 21.7% | 52.9% | GPT-4o-mini |

> 注：各框架使用不同的 Judge LLM，分数不完全可比。

## 各轮改进详情

### 第2轮：基础设施与性能（02-16）

| 改进 | 说明 |
|------|------|
| 独立评测数据库 | neuromem_eval 隔离，避免污染开发数据 |
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

### 第14轮：Reflect 集成 + 提取质量提升（02-22）

| 改进 | 说明 |
|------|------|
| 自动后台 reflect | `reflection_interval` 参数，每 N 次提取后在后台触发 reflect，insight 记忆立即可用 |
| 并行 recall | vector / conversation / profile 三路并行（asyncio.gather），episodic+fact 子搜索也并行 |
| 并行 embedding | facts 和 episodes 的 embed_batch 并行调用，减少一次 API round-trip |
| Facts/Episodes 去重修复 | 一次性事件只放 Episodes，不再同时生成低质量 Fact 副本；提取 prompt 明确约束 |
| 中文时序查询修复 | TemporalExtractor 新增中文时间词识别，触发 episodic 优先召回分支 |
| 评测 pre-init 修复 | 并行 ingest 前先单独 init，避免多 worker 并发 CREATE TABLE 冲突 |

效果：Overall 0.8017→0.817（+1.9%）。Temporal +7%（0.716→0.766），Multi-Hop +4.2%（0.809→0.843）。Single-Hop 略降（0.871→0.829）。

**注意**：本轮 ingest 更完整（0 写入失败 vs R13 存在 BM25 并发损坏），共写入 14107 条记忆（含 693 条 insights），耗时 2h20min（reflect 约占 1h）。

### 第19轮：提取状态追踪 + 清空重提取（02-25）

| 改进 | 说明 |
|------|------|
| 提取状态追踪 | `extracted: bool` → `extraction_status: str`（pending/done/failed），新增 `extraction_error`、`extraction_retries` 字段 |
| 失败重试 API | `retry_failed_extractions(user_id, max_retries=3)` 公共方法，自动重试失败的提取 |
| 后台任务状态标记 | `_extract_single_message_async` 成功标记 done，失败标记 failed + 记录错误 |
| 清空重提取 | 清空 embeddings 表，重新提取全部 5882 条 user 消息，0 失败（vs R18 约 581 次失败） |
| 评测 pipeline 集成 | locomo ingest 完成后自动调用 `retry_failed_extractions` |

效果：Overall 0.799（vs R18 0.792，+0.9%）。记忆数 11267（vs R18 8708，+29%）。Open-Domain 显著提升（0.807→0.905，+12.1%），但 Temporal 下降（0.757→0.725，-4.2%）。

**分析**：本轮主要是工程改进（提取可靠性），非算法优化。更多记忆对 Open-Domain 有帮助（更全面的事实覆盖），但 Temporal 下降可能与 reflect 缺失有关（本轮清空重提取后未跑 reflect，缺少 insight 记忆）。

| 指标 | R18 (8708 memories) | R19 (11267 memories) | 变化 |
|------|:---:|:---:|:---:|
| F1 | — | 0.256 | — |
| BLEU-1 | — | 0.204 | — |
| Judge | 0.792 | 0.799 | +0.9% |
| 记忆数 | 8708 | 11267 | +29% |
| 提取失败 | ~581 | 0 | -100% |

## 尝试但回退的实验

| 实验 | 测试结果 | 回退原因 |
|------|---------|---------|
| 规则化 Query 分类 | Judge -0.013 | Open-domain BM25 权重 0.3 过激 |
| 读时记忆去重 (cosine>0.92) | Judge -0.033 | 丢失重复 fact 的"投票"信号，single-hop 下降 |
| R13基线+去重/中文时序/并行recall组合（R15） | Judge -0.025 vs R14 | fact 去重修复减少记忆数（9510 vs 14107），single-hop/temporal 均下降；并行recall未带来分数提升 |
| 后台异步reflect + 去掉召回原始对话（R16） | Judge -0.013 vs R14 | ingest 快 55%（63min vs 140min），Temporal 持平，但 Multi-Hop/Single-Hop 略降；部分 insight 在 query 时还未写入 |
| R16数据+去掉insight参与召回（消融） | Judge -0.023 vs R16 | insight 贡献显著：Multi-Hop -3.1%、Single-Hop -2.3%、Temporal -2.1%；insight 应保留 |
| GRAPH_ENABLED=1（R17） | Judge -0.027 vs R14 | 图谱三元组提取影响LLM抽取质量，Open-Domain +2.2% 但其余类别均下降；图谱不建议默认开启 |
| 时间语义分拆+fact格式+reflect去重（R18） | Judge -0.025 vs R14 | Multi-Hop +0.031 有提升，但 Temporal/Single-Hop 略降；新 fact 格式对 Temporal 无帮助，Level4 timestamp fallback 效果不明显 |

## 待优化方向

当前最优：**R14（0.817）**。当前最弱项：**Temporal（76.6%）**，与 Backboard（91.9%）差距最大。

- **Temporal 提升**：分拆 facts/timeline 格式对 Temporal 无效（R18 验证）；根本问题可能是 episodic 提取时时间戳精度不足，或 query 时间窗口过滤未正确命中
- **Single-Hop 下滑**：R18 的 Single-Hop 0.773（vs R14 0.829），新 fact 格式可能让 LLM 难以直接提取简单事实
- **Multi-Hop 有效**：R18 Multi-Hop 0.842（+0.031 vs R14），facts/timeline 分栏对需要多步推理的题目有帮助，保留
- **逼近 Backboard（90%）**：Multi-Hop 已接近，Temporal 和 Single-Hop 仍是主要差距
- **insight 有效**：消融实验证明 insight 贡献 +2.3% Overall，Multi-Hop 贡献最大（+3.1%），应保留
- **图谱（GRAPH_ENABLED）**：R17 证明默认开启有害，暂不启用
- **原始对话消息召回**：R16 去掉后分数未明显变化，暂不恢复；`include_conversations` 开关已实现供需要时使用
- **答案冗长拖低 F1/BLEU**：R19 分析发现预测平均 76 字符 vs gold 30 字符（2.6x），94 个 case gold<20 字符但预测>100 字符；调整 answer prompt 要求简洁直答可显著提升 F1/BLEU
- **R19 缺少 reflect**：清空重提取后未跑 reflect，缺少 insight 记忆，可能是 Temporal 下降原因；下次应在重提取后补跑 reflect
