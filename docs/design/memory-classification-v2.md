# 记忆分类体系 V2 设计文档

> **状态**: V2 核心已实施完成，P2 记忆增强 5/7 项已实现（2026-03-02），P1 演进待实施
> **创建日期**: 2026-02-28
> **更新日期**: 2026-03-02（P2-1~P2-5 已实现，更新 §8.3）
> **参与者**: Jacky + Claude
> **关联**: `docs/memory-architecture.md`（现有架构）
> **调研报告**: `docs/design/research/01~05`（5 份独立调研，覆盖认知心理学/学术研究/MemGPT/商业系统/Personal AI）

---

## 1. 设计动机

### 1.1 现有体系的问题

当前 neuromem 的记忆分类为 5 种：`fact`、`episodic`、`insight`、`general`、`document`。

核心问题有两个：

**问题一**：`fact` 类型承载了两种本质不同的信息：

- 离散客观事实："用户在 Google 工作"
- 抽象行为特质："用户是效率驱动型人格"

这两者的产生机制、更新频率、置信度模型完全不同，不应混为一类。

**问题二**：`insight` 作为独立记忆类型定位模糊，在 Tulving 记忆框架中没有理论锚点，与 `trait` 的边界不清晰。几乎所有"最近X"的趋势表述，要么最终固化为 trait（如果持续），要么消失（如果暂时）。insight 本质是 trait 的前置中间态，不应是独立类型。

### 1.2 认知心理学基础

参考 Atkinson-Shiffrin 多重记忆模型和 Tulving 长时记忆分类：

```
人脑记忆系统
├── 感觉记忆 (Sensory)           ← 毫秒级，SDK 不涉及
├── 短期/工作记忆 (Working Memory) ← 对话上下文，由应用层管理
└── 长期记忆 (Long-term)          ← neuromem 的核心领域
    ├── 陈述性记忆 (Declarative)
    │   ├── 语义记忆 (Semantic)   ≈ fact
    │   └── 情景记忆 (Episodic)   ≈ episodic
    ├── 程序性记忆 (Procedural)   ← 当前缺失，对应行为模式
    └── 情绪记忆 (Emotional)      ← emotion_profiles 部分覆盖
```

### 1.3 关键洞察（来自 Gemini 讨论）

三个核心质疑推动了本次重新设计：

1. **人机对话的表演性**：用户对 LLM 展现"人机交互面具"，单次对话提取的特征可能只是"数字替身"而非真实人格。**应对**：特质必须经过多次验证才能确立。

2. **记忆不等于存储**：人类记忆是建构性和动态衰退的，只增不减会导致"上下文污染"和信噪比崩溃。**应对**：需要遗忘/衰减机制。

3. **事实与特质不能一次性提取**：事实是离散客观数据，特质是连续主观抽象，特质必须经过从情景到语义的长期沉淀。**应对**：trait 只能由 reflection 引擎产生，不能从单次对话直接提取。

### 1.4 业界参考

| 项目 | 关键贡献 |
|------|----------|
| Stanford Generative Agents (UIST 2023) | 检索公式：Recency + Importance + Relevance；观察→规划→反思链路；重要度累积触发反思 |
| MemGPT / Letta (UC Berkeley, 2023→2026) | OS-inspired 内存分页，LLM 自主记忆读写；演进为 AI Memory SDK + Learning SDK |
| Mem0 | 向量 + 图 + KV 混合架构，批量提取（ADD/UPDATE/DELETE/NOOP 四操作模式） |
| Zep AI / Graphiti | 时态知识图谱，Episode/Entity/Community 三层子图，双时间线模型 |
| RGMem (2025) | 重整化群启发的多尺度记忆，快慢变量分离（与 V2 三层衰减率独立吻合） |
| A-MEM (NeurIPS 2025) | Zettelkasten 自组织记忆网络，记忆间横向关联 |
| MemoryBank (AAAI 2024) | 将 Ebbinghaus 遗忘曲线引入 AI 记忆系统 |
| Memoria (Amazon, 2025) | traits/preferences/behaviors 概念，但无显式升级链 |
| Second Me (2025) | 人格建模通过模型参数化实现（黑盒，不可解释） |

### 1.5 全球调研验证（2026-02-28）

对 V2 设计进行了 5 个方向的独立调研（认知心理学、学术研究、MemGPT/Letta、商业系统、Personal AI），核心结论：

1. **trait 三层子类（behavior→preference→core）在全球范围内独一无二**：所有调研的学术项目和商业产品中，无一实现类似的结构化升级链
2. **V2 的设计有坚实的理论支撑**：fact/episodic 映射 Tulving 语义/情景记忆（强支撑）；三层升级映射 Conway SMS 层级抽象和 Allport 特质理论（强支撑）；情境化 trait 映射 Mischel CAPS if-then 模式（强支撑）
3. **"trait 只能由 reflection 产生"的核心决策得到数据验证**：最新研究显示 LLM 从单次对话推断 Big Five 人格的最高相关性仅 r=0.27
4. **V2 的遗忘三重机制（衰减+矛盾反思+dissolved 归档）是所有调研系统中最完善的**

基于调研结果和后续讨论，以下改进已合入本设计：
- `[P0-调研]` §3.2：情境标注前置
- `[P0-调研]` §4.2：证据质量分级 + 衰减模型增强（间隔效应）
- `[P0-调研]` §4.5：反思触发机制
- `[架构精简]` §2.1/§4.1：insight 降级为 trait 的 `trend` 阶段，分类体系从 5 类精简为 4 类

详细调研报告见 `docs/design/research/01~05`。

---

## 2. 新分类体系

### 2.1 总览

```
记忆分类（业务层）— 4 类
│
├── fact (事实记忆)
│   来源：单次对话 LLM 提取
│   特征：离散、客观、可验证
│   示例："用户在 Google 工作"、"用户养了一只猫叫 Mimi"
│
├── episodic (情景记忆)
│   来源：单次对话 LLM 提取
│   特征：一次性事件，强绑定时间/地点/人物
│   示例："2024-02-15 用户参加了 Python meetup"
│
├── trait (特质记忆)  ← 新增
│   来源：reflection 引擎从多条 fact/episodic 中归纳（永远不从单次对话直接提取）
│   特征：连续、主观、需要多次验证
│   子类：behavior / preference / core（详见 §3）
│   生命周期含 trend 阶段（吸收原 insight 的趋势检测职责，详见 §4.1）
│
└── document (文档记忆)
    来源：文件上传（RAG 场景）
    不变
```

#### insight 降级决策（原 5 类 → 4 类）

原设计中 `insight` 作为独立 memory_type 存在，经审查后**降级为 trait 的 `trend` 阶段**。

**考虑过的方案**：

| 方案 | 内容 | 优劣 |
|------|------|------|
| A. 删除 insight | 趋势检测合并到 trait candidate | 最简洁，但丢失"趋势 vs 特质"的语义区分 |
| **B. 降级为 trait 属性** | **trait_stage 增加 `trend`（在 candidate 之前）** | **统一类型体系，保留语义，消除跨类型升级** |
| C. 保留但重定义 | insight 保留为独立类型，增加 valid_window | 保守，但类型数量多，跨类型升级逻辑复杂 |

**选择方案 B 的理由**：

1. **消除类型膨胀**：分类从 5 种精简为 4 种，reflection prompt 更简洁，recall 管道更少分支
2. **消除跨类型升级**：原设计需要 insight→trait 的跨类型跳转逻辑，方案 B 只需 trait 内部的阶段流转（trend→candidate），更干净
3. **保留趋势语义**：`trait_stage = "trend"` 明确标记"这还只是近期趋势，不是稳定特质"，recall 时 trend 不参与（同 candidate）
4. **trait 生命周期天然容纳**：trend 是 candidate 之前的"观察期"，如果趋势持续则自然升级，如果消失则自动过期清除

### 2.2 记忆产生的流转路径

```
对话 → [LLM 提取] → fact / episodic
                          │
                          ↓ (reflection 定期扫描)
                          │
                     ┌────┴────┐
                     ↓         ↓
              trait [trend]   trait [candidate]
             (时间窗口趋势)    (初步行为模式)
                     │         │
                     ↓         ↓
              trait [candidate] → trait [emerging] → trait [established] → trait [core]
                              (behavior)          (preference)          (core)
```

**关键**：reflection 引擎扫描 fact/episodic 时，判断发现的模式是"近期趋势"还是"有一定积累的行为模式"：
- 证据跨度短（< 2 周）、数量少（< 3 条）→ 创建 trend 阶段 trait（带 valid_window）
- 证据跨度长或数量足 → 直接创建 candidate 阶段 trait（走正常升级流程）

### 2.3 各类型对比

| 维度 | fact | episodic | trait | document |
|------|------|----------|-------|----------|
| **产生方式** | 单次对话 LLM 提取 | 单次对话 LLM 提取 | reflection 归纳 | 文件上传 |
| **稳定性** | 可变但离散 | 不可变 (append-only) | 高度稳定（trend 阶段除外） | 不变 |
| **置信度模型** | 一次确认即可 | 无需置信度 | 需要 N 条证据累积 | 无需 |
| **更新方式** | 新事实覆盖旧版本 (supersede) | 不更新 | 渐进式置信度升降 | 不更新 |
| **衰减** | 不自动衰减 | recency_bonus 自然衰减 | 按子类不同速率衰减 | 不衰减 |

> **注**：原 `insight` 类型已降级为 trait 的 `trend` 阶段（详见 §2.1 和 §4.1）。原 `general` 类型已废弃。

---

## 3. Trait 子类设计

### 3.1 选型决策

**考虑过的方案**：

| 方案 | 层级 | 优劣 |
|------|------|------|
| 四层：behavior / preference / personality / value | 最精细 | reflection 复杂度高，早期数据量不足以区分 personality 和 value |
| **三层：behavior / preference / core** | **采纳** | 实用主义，core 合并 personality+value，未来可拆分 |
| 两层：behavioral / dispositional | 最简洁 | 丢失内部层次，不支持有意义的升级链 |

**选择三层的理由**：

1. 支持自动升级（用户明确要求），三层提供两级升级路径，足够丰富。
2. personality 和 value 在应用层差异不大（都用于"理解这个人是什么样的人"），早期合并不影响效果。
3. 未来数据量足够后，`core` 可拆分为 `personality` + `value`，只需加一个字段，不影响已有数据。

### 3.2 三层定义

```
稳定性（高→低）    可观测性（低→高）

  core               难以直接观测，从多个 preference 推断
    ↑                  "高尽责性"、"重视自由与自主"
  preference         可通过选择行为观测
    ↑                  "偏好数据驱动决策"、"喜欢极简设计"
  behavior           直接可观测
                       "深夜活跃"、"决策前必查数据"
```

#### `[P0-调研]` 情境标注前置

**原设计**：情境标签（work/personal/social 等）仅在矛盾分裂时才被动产生。
**改进**：从 behavior 层级开始就主动附带情境标签。

**理由**（来自认知心理学调研 #01 + Personal AI 调研 #05）：
- Mischel 的 CAPS 理论（Cognitive-Affective Personality System）指出，人的行为本质上是 **if-then 情境模式**（"如果在工作中，则严谨"），而非跨情境一致的
- 在 behavior 层就标注情境，可以在升级为 preference 时自然继承情境信息，而非等到矛盾出现才被动分裂
- 情境标签也为后续 recall 提供了过滤维度（如：构建工作场景的 prompt 时优先召回 work 情境的 trait）

**情境标签体系**（可扩展）：

| 标签 | 含义 | 示例 |
|------|------|------|
| `work` | 工作/专业场景 | "开会时总是要求看数据" |
| `personal` | 私人/生活场景 | "周末喜欢独处" |
| `social` | 社交场景 | "聚会时话不多" |
| `learning` | 学习/成长场景 | "学新技术时偏好先看文档" |
| `general` | 跨情境通用 | "做决策前必须收集信息"（多个情境均观测到） |

**标注规则**：
- reflection 引擎生成 behavior 时，根据来源 fact/episodic 的上下文推断情境
- 如果同一行为模式在多个情境中均被观测到 → 标注为 `general`（跨情境一致性更高，升级置信度加成更大）
- 升级为 preference/core 时，继承子 trait 的情境标签集合

**从表层到内核的推断链示例**：

```
behavior [work]:  "每次讨论方案时都会要求看数据"
behavior [work]:  "写代码前总是先画架构图"
behavior [work]:  "拒绝了两次未经测试就上线的请求"
    ↓ 归纳
preference [work]: "偏好数据驱动的决策方式"
    ↓ 抽象
core [work]: "高尽责性（Conscientiousness）"
```

```
behavior [work]:   "工作中反复检查细节"
behavior [personal]: "生活中随手放东西、不拘小节"
    ↓ 归纳（情境分歧，无需等矛盾触发）
preference [work]:    "注重专业品质"
preference [personal]: "生活中追求轻松随性"
    ↓ 抽象
core [contextual]: "工作场景中严谨细致，私人场景中随性自由"
```

### 3.3 升级触发条件

```
fact/episodic → behavior:
  条件：≥3 条 fact/episodic 呈现相同行为模式
  动作：创建 behavior trait (初始 confidence=0.4)
  示例：3 次对话都在深夜 → behavior:"深夜活跃"

behavior → preference:
  条件：≥2 条 behavior 指向同一倾向 + 各自 confidence≥0.5
  动作：创建 preference trait，继承子证据
  示例：behavior:"决策前查数据" + behavior:"要求 AB 测试"
        → preference:"数据驱动型决策者"

preference → core:
  条件：≥2 条 preference 指向同一人格维度 + 各自 confidence≥0.6
  动作：创建 core trait
  示例：preference:"数据驱动决策" + preference:"注重流程规范"
        → core:"高尽责性"

trend → candidate（趋势固化）:
  条件：valid_window 期间内被 ≥2 次 reflection 强化
  动作：trend 升级为 candidate (confidence=0.3)，移除 valid_window
  示例：trend:"最近频繁讨论跳槽"（2 周内反复出现）
        → candidate behavior:"关注职业发展机会"

trend 过期清除：
  条件：valid_window 结束时无强化
  动作：直接标记为 dissolved
  示例：trend:"最近对摄影感兴趣"（窗口结束后再无提及）→ dissolved
```

---

## 4. Trait 生命周期

### 4.1 阶段定义

```
  ┌──────────┐    ┌──────────┐     ┌──────────┐    ┌──────────┐    ┌──────────┐
  │  trend    │───▶│ candidate │────▶│ emerging  │───▶│established│───▶│  core    │
  │ 时间窗口  │    │ conf<0.3  │     │ 0.3-0.6  │    │ 0.6-0.85 │    │  >0.85   │
  └──────────┘    └──────────┘     └──────────┘    └──────────┘    └──────────┘
       │               │                │               │               │
       ▼               ▼                ▼               ▼               ▼
  ┌──────────┐    ┌──────────────────────────────────────────────────────┐
  │ dissolved │◀───│               矛盾/衰减/过期/修正                     │
  └──────────┘    └──────────────────────────────────────────────────────┘
```

| 阶段 | 管理方式 | 含义 | recall 行为 |
|------|---------|------|------------|
| **trend** | valid_window（时间窗口） | 近期趋势，尚不确定是否会固化为特质 | **不参与** recall |
| **candidate** | confidence < 0.3 | 有初步模式，可能偶然 | **不参与** recall |
| **emerging** | confidence 0.3 - 0.6 | 有一定模式但不确定 | 低权重参与 |
| **established** | confidence 0.6 - 0.85 | 可信的特质 | 正常权重 |
| **core** | confidence > 0.85 | 高度稳定的核心特质 | 高权重，优先召回 |
| **dissolved** | — | 被推翻、过期或长期无强化 | 归档，不参与 |

#### trend 阶段详细说明（原 insight 的替代）

trend 是 trait 生命周期的最早期阶段，用于捕捉"近期趋势"。它吸收了原 `insight` memory_type 的全部职责。

**与 candidate 的区别**：
- trend 用 `valid_window`（时间窗口）管理，不用 confidence — 因为趋势的本质是"时效性观察"，不适合用置信度量化
- candidate 用 confidence 管理 — 因为已经跨越了"趋势→模式"的认知门槛

**trend 的行为**：

```python
# trend 创建
trait_stage = "trend"
valid_window = {"start": now, "end": now + timedelta(days=30)}  # 默认 30 天观察窗口
# 窗口长度可根据趋势的性质调整（如情绪相关趋势窗口更短：14 天）

# trend 在每次 reflection 中的处理
if trait_stage == "trend":
    if now > valid_window["end"]:
        # 窗口过期
        if reinforcement_count >= 2:
            # 趋势被多次强化 → 升级为 candidate
            trait_stage = "candidate"
            confidence = 0.3
            del valid_window  # 转为 confidence 管理
        else:
            # 趋势未被强化 → 清除
            trait_stage = "dissolved"
    else:
        # 窗口内：检查是否有新证据强化
        # 每次强化 reinforcement_count += 1
        pass
```

### 4.2 置信度计算模型

#### `[P0-调研]` 证据质量分级

**原设计**：reinforcement_factor 仅区分"同对话/跨对话"二分（0.05 vs 0.15）。
**改进**：引入四级证据质量分级，替代简单二分。

**理由**（来自 Personal AI 调研 #05）：
- 用户显式陈述（"我是程序员"）和隐式行为信号（多次在深夜活跃）的证据强度有本质差异
- 跨情境一致性是特质可信度的关键指标（Mischel CAPS 理论），应给予最高权重

**四级证据质量**：

| 级别 | 类型 | reinforcement_factor | 说明 |
|------|------|---------------------|------|
| **A** | 跨情境行为一致性 | 0.25 | 在不同情境（work+personal）中观测到相同模式 |
| **B** | 显式陈述 | 0.20 | 用户明确说出的自我描述（"我是个急性子"） |
| **C** | 跨对话行为 | 0.15 | 不同对话中观测到相同模式（同一情境） |
| **D** | 同对话/隐式信号 | 0.05 | 同一对话内的信号，或从行为间接推断 |

```python
# 1. 强化（新证据支持）
new_confidence = old_confidence + (1 - old_confidence) * reinforcement_factor
# reinforcement_factor 取决于证据质量等级：
#   A 级（跨情境一致） → 0.25
#   B 级（显式陈述）   → 0.20
#   C 级（跨对话行为） → 0.15
#   D 级（同对话/隐式） → 0.05

# 2. 矛盾（新证据反对）
new_confidence = old_confidence * (1 - contradiction_factor)
# contradiction_factor: 0.2（单条矛盾）~ 0.4（强矛盾+多条）
```

#### `[P0-调研]` 衰减模型增强（间隔效应）

**原设计**：λ 为固定常数，仅按子类区分。
**改进**：λ 随强化次数递减，模拟 Ebbinghaus 间隔效应（spacing effect）。

**理由**（来自认知心理学调研 #01）：
- 心理学研究表明，经过多次间隔重复巩固的记忆更不易遗忘
- 被反复验证的 trait 应该比初次形成的 trait 衰减更慢
- MemoryBank (AAAI 2024) 已成功将此机制引入 AI 记忆系统

```python
# 3. 时间衰减（长期无强化）— 增强版
base_lambda = {
    "behavior": 0.005,
    "preference": 0.002,
    "core": 0.001,
}

# 间隔效应：强化次数越多，衰减越慢
# reinforcement_count 为累计强化次数
effective_lambda = base_lambda[subtype] / (1 + 0.1 * reinforcement_count)
# 示例：
#   behavior 首次形成（count=1）: lambda = 0.005 / 1.1 = 0.0045
#   behavior 强化 5 次（count=5）: lambda = 0.005 / 1.5 = 0.0033
#   behavior 强化 10 次（count=10）: lambda = 0.005 / 2.0 = 0.0025（衰减速度减半）

decayed = confidence * exp(-effective_lambda * days_since_last_reinforced)
```

**衰减速率的设计理由**：
- behavior 是表层行为模式，人的行为变化相对频繁（换工作、换环境都会改变），需要持续强化
- preference 是中层偏好，相对稳定但也会随阅历变化
- core 是深层人格，心理学研究表明人格特质在成年后高度稳定
- `[P0-调研]` 间隔效应叠加：无论哪个子类，被多次验证的 trait 都比新生 trait 更抗衰减，与 RGMem (2025) 的快慢变量分离原理一致

### 4.3 升级后处理

**决策：保留所有层级（不压缩底层）**

behavior 被升级为 preference 后，原始 behavior 继续存在，通过 `child_traits` / `parent_trait` 双向引用关联。

**选择理由**：

1. **多粒度 recall 需求**：有时需要具体行为（"用户总是深夜活跃"用于推送时间决策），有时需要抽象偏好（"用户是数据驱动型"用于回复风格调整）。压缩掉底层就丢失了具体性。

2. **可回溯性**：如果 preference 被矛盾证据否定，需要回溯到原始 behavior 证据重新评估。压缩后无法回溯。

3. **工程简单**：不需要判断"何时压缩"的阈值逻辑，只维护双向引用即可。

4. **存储代价可接受**：trait 的数量级远小于 fact/episodic（一个用户的 trait 通常在数十到百量级），冗余存储的代价完全可忽略。

### 4.4 矛盾处理机制

**决策：触发专项反思（而非静默衰减或直接分裂）**

```
新证据与已有 trait 矛盾
    ↓
矛盾计数 +1
    ↓
矛盾数 / 总证据数 > 阈值？（建议阈值：0.3）
    ↓ 是
触发专项 reflection
    ↓
综合所有证据（supporting + contradicting），LLM 判断：
    │
    ├── 修正 trait（原判断有误，更新 content 和 confidence）
    │   示例："偏好独立工作" → 修正为 "偏好独立思考，但享受团队讨论"
    │
    ├── 分裂为情境化双面 trait（不同情境下展现不同面）
    │   示例：工作中严谨 + 生活中随性 → 带情境标注的复合 trait
    │
    └── 废弃 trait（证据太弱，不足以成立）
        trait 标记为 dissolved，归档
```

**选择理由**：

1. **静默衰减太被动**：人的复杂性经常表现为"看似矛盾的特质共存"（工作中严谨、生活中随性），机械衰减会丢失这些有价值的洞察。

2. **直接分裂太激进**：不是所有矛盾都代表"两个对立面共存"，有些只是证据不足或语境差异。

3. **专项反思最合理**：由 LLM 综合判断矛盾的性质，灵活选择修正/分裂/废弃。

**情境化双面 trait**（矛盾分裂的产物）：

```json
{
  "content": "工作场景中严谨细致，私人场景中随性自由",
  "metadata": {
    "trait_subtype": "core",
    "contexts": {
      "work": {"tendency": "严谨细致", "confidence": 0.8},
      "personal": {"tendency": "随性自由", "confidence": 0.65}
    }
  }
}
```

这呼应了认知心理学中的**情境性（Situationality）**— 人在不同情境下展现不同面，这不是矛盾，而是人的完整图谱。

### 4.5 反思触发机制

#### `[P0-调研]` 混合触发策略

**原设计**：reflection 的触发条件未明确定义（仅提及"定期扫描"和"重要性阈值"）。
**改进**：定义三种互补的触发条件，任一满足即触发。

**理由**（来自 Generative Agents 调研 #02）：
- Stanford Generative Agents 使用"重要度累积阈值"触发反思，效果显著
- 纯定时触发会浪费算力（空闲期无新信息也触发）或错过关键时刻（密集对话期积累大量未处理信息）
- 混合策略兼顾效率和及时性

**三种触发条件**：

| 触发类型 | 条件 | 适用场景 |
|----------|------|----------|
| **重要度累积** | 自上次反思以来，新增 fact/episodic 的 importance 总和 ≥ 阈值（建议：30） | 密集对话期：大量高价值信息需要及时处理 |
| **定时兜底** | 距离上次反思 ≥ T 时间（建议：24 小时） | 避免长时间无反思导致信息堆积 |
| **会话结束** | 用户主动结束会话，或会话空闲超过阈值（建议：30 分钟） | 自然的认知边界，类似"睡眠巩固" |

**重要度累积的计算**：

```python
# 反思触发检查（每次 ingest 后执行）
accumulated_importance = sum(
    m.metadata.get("importance", 5)
    for m in new_memories_since_last_reflection
)

should_trigger = (
    accumulated_importance >= 30                    # 重要度累积
    or time_since_last_reflection >= timedelta(hours=24)  # 定时兜底
    or session_just_ended                           # 会话结束
)
```

**反思的执行内容**（每次触发时按顺序执行）：

```
1. 扫描自上次反思以来的所有新 fact/episodic
2. 检测短期趋势 → 生成 trend 阶段 trait（带 valid_window）
3. 检查已有 trend → 过期清除或升级为 candidate
4. 检测行为模式 → 生成/强化 behavior trait (candidate+)
5. 检测 behavior 聚类 → 升级为 preference
6. 检测 preference 聚类 → 升级为 core
7. 检测已有 trait 的矛盾证据 → 触发矛盾处理（§4.4）
8. 应用时间衰减 → 降级/dissolved 过期 trait
9. 记录本次反思的水位线（last_reflected_at）
```

**与 Generative Agents 的两阶段反思对比**：

Generative Agents 采用"先提问再检索验证"的两阶段模式（如："关于 Alice，最近最显著的变化是什么？"→ 检索相关记忆 → 生成反思）。V2 的反思流程可在中期借鉴此模式，让 LLM 先生成"关于该用户的关键问题"，再针对性检索验证，以提高反思质量。当前版本采用全量扫描模式，实现更简单。

---

## 5. Trait 数据结构

### 5.1 metadata 扩展

```json
{
  "memory_type": "trait",
  "content": "偏好数据驱动的决策方式",
  "metadata": {
    // === trait 专属字段 ===
    "trait_subtype": "preference",        // behavior | preference | core
    "trait_stage": "established",          // trend | candidate | emerging | established | core | dissolved

    "confidence": 0.72,                    // trend 阶段无此字段，用 valid_window 管理

    // === trend 阶段专属（仅 trait_stage="trend" 时存在） ===
    // "valid_window": {"start": "2024-02-15", "end": "2024-03-15"},

    // === [P0-调研] 情境标注（从 behavior 开始就附带） ===
    "context": "work",                     // work | personal | social | learning | general
    // 说明：
    //   - behavior 层：由 reflection 根据来源 fact/episodic 的上下文推断
    //   - preference/core 层：继承子 trait 的情境标签集合
    //   - "general" 表示跨情境一致（置信度加成更大）
    //   - 情境化双面 trait 使用 contexts 字段替代单一 context（见下方）

    // === 证据链 ===
    "evidence": {
      "supporting": [                      // 支持该 trait 的证据（带质量分级）
        {"id": "uuid-1", "quality": "C"},  // C 级：跨对话行为
        {"id": "uuid-2", "quality": "A"},  // A 级：跨情境一致
        {"id": "uuid-5", "quality": "B"}   // B 级：显式陈述
      ],
      "contradicting": [
        {"id": "uuid-3", "quality": "D"}   // D 级：同对话隐式信号
      ],
      "child_traits": ["uuid-behavior-1", "uuid-behavior-2"],  // 下层 trait（被归纳者）
      "parent_trait": null                  // 上层 trait（归纳产物）
    },

    // === 时间线 ===
    "first_observed": "2024-01-15",        // 首次观测到模式
    "last_reinforced": "2024-02-20",       // 最近一次被强化
    "reinforcement_count": 5,              // 累计强化次数（影响衰减速率，间隔效应）
    "contradiction_count": 1,              // 累计矛盾次数

    // === 来源追溯 ===
    "derived_from": "reflection",          // 产生方式：reflection | trend_promotion
    "reflection_cycle_ids": ["cycle-12", "cycle-15", "cycle-18"],

    // === 情境化双面（可选，情境分歧或矛盾分裂的产物） ===
    // 注意：当存在 contexts 时，顶层 context 字段设为 "contextual"
    "contexts": {
      "work": {"tendency": "严谨细致", "confidence": 0.8},
      "personal": {"tendency": "随性自由", "confidence": 0.65}
    },

    // === 通用字段（与 fact/episodic 共享） ===
    "importance": 8,
    "emotion": {
      "valence": 0.3,
      "arousal": 0.4,
      "label": "平静、认可"
    }
  }
}
```

### 5.2 与现有表结构的关系

trait 复用现有 `embeddings` 表（`memory_type = "trait"`），无需建新表。理由：

1. trait 同样需要 embedding 向量用于语义检索
2. trait 同样需要 version/valid_from/valid_until 用于版本管理
3. 所有 trait 专属字段通过 `metadata_` JSONB 存储，不需要改表结构
4. recall 的混合检索管道（向量 + BM25 + RRF）可无缝适配

需要的索引扩展：
- `ix_emb_trait_subtype`: `(user_id, memory_type, metadata_->>'trait_subtype')` — 按子类查询
- `ix_emb_trait_stage`: `(user_id, memory_type, metadata_->>'trait_stage')` — 按阶段查询

---

## 6. Recall 中的 Trait 使用

### 6.1 权重策略

trait 在 recall 评分中的权重应高于普通 fact/episodic，因为 trait 是经过验证的高价值信息：

```python
# trait 的 recall 评分加成
trait_boost = {
    "trend": 0.0,           # 不参与 recall
    "candidate": 0.0,       # 不参与 recall
    "emerging": 0.05,       # 微弱加成
    "established": 0.15,    # 显著加成
    "core": 0.25,           # 最高加成
}

final_score = base_score * (1 + recency + importance + trait_boost[stage])
```

### 6.2 trait 在 prompt 构建中的角色

应用层（如 Me2）构建 system prompt 时，trait 应独立于 fact/episodic 展示：

```
[System Prompt 结构]
1. 基础人设指令
2. 用户核心特质（core traits）     ← 始终包含
3. 用户偏好（preference traits）   ← 始终包含
4. 用户行为模式（behavior traits） ← 按相关性选择性包含
5. 召回的事实和情景（fact/episodic）← 按 query 相关性排序
```

---

## 7. 对 Gemini 三个质疑的回应

| 质疑 | 本设计的应对 |
|------|------------|
| **人机对话的表演性** | trait 的置信度模型天然应对。单次对话中的"表演"只产生 fact/episodic，只有跨多次对话反复验证的模式才能升级为 trait，自动过滤偶发的人设表演 |
| **记忆只增不减** | 四重遗忘机制：(1) trait 时间衰减 (2) 矛盾触发专项反思可废弃 (3) dissolved 归档不参与 recall (4) trend 阶段 valid_window 过期自动清除 |
| **事实与特质不能一次性提取** | LLM 提取层只产出 fact + episodic，trait 由独立的 reflection 引擎异步产生，天然分离 |

---

## 8. 未来演进方向

### 8.1 近期（V2 实施）— ✅ 已全部完成（2026-03-01 确认）

- ✅ trait memory_type 和三层子类（`models/memory.py`, `services/trait_engine.py`）
- ✅ `[P0]` 情境标注前置（`trait_context` 字段，reflection LLM 推断）
- ✅ `[P0]` 证据质量四级分级（`models/trait_evidence.py`, `_QUALITY_FACTORS`）
- ✅ `[P0]` 反思混合触发机制（重要度累积≥30 / 定时24h / 会话结束 / 强制）
- ✅ `[P0]` 衰减间隔效应（`_BASE_LAMBDA` + `reinforcement_count`）
- ✅ reflection 引擎 9 步管道（`services/reflection.py`）
- ✅ 矛盾检测和专项反思机制（`trait_engine.resolve_contradiction`）
- ✅ recall 中的 trait 权重和阶段过滤（`services/search.py`）
- ✅ insight 降级为 trait trend + general 类型废弃（向后兼容映射）
- ✅ trait 生命周期全 6 阶段（trend/candidate/emerging/established/core/dissolved）
- ✅ valid_window 时间窗口管理（`trait_window_start/end`）
- ✅ child_traits/parent_trait 引用（`trait_parent_id` 字段，反向通过 SQL 查询）

### 8.2 中期（P1 调研建议）

- **召回即强化**：recall 命中 trait 时微弱强化置信度（+0.02），模拟心理学"测试效应"（来自 Generative Agents 调研 #02）
- **Trait Transparency**：用户可查看"系统认为你是什么样的人" + 证据链 + 编辑/删除权（来自 Personal AI 调研 #05）
- **敏感特质保护**：心理健康/政治/宗教等类别不进行 trait 推断（来自 Personal AI 调研 #05）
- **工作记忆提交接口**：SDK 层提供 `commit_working_memory()` 方法（来自 MemGPT 调研 #03）
- core 拆分为 personality + value（当数据量支撑区分时）
- trait 对 recall 的主动影响（如：检测到用户"偏好简洁"→ 自动调整回复长度）

### 8.3 远期（P2 调研建议 + 原有规划）

- ~~**记忆间横向关联**~~：✅ 已实现 2026-03-02 — digest 时 LLM 识别语义关联，存入 `metadata_.related_memories`，recall 时 1-hop 扩展
- ~~**两阶段反思**~~：✅ 已实现 2026-03-02 — importance_accumulated 触发时先生成问题再检索证据
- ~~**Zep 双时间线**~~：✅ 已实现 2026-03-02 — 提取 `metadata_.event_time`，recency bonus 优先使用事件时间
- ~~**程序性记忆**~~：✅ 已实现 2026-03-02 — category=workflow + `metadata_.procedure_steps`
- ~~**前瞻记忆**~~：✅ 已实现 2026-03-02 — 过期前瞻记忆 0.5x 降权 + digest 自动过期
- 跨用户的 trait 模式发现（群体画像）
- 基于 trait 的主动行为预测

---

## 附录 A：与现有 memory-architecture.md 的关系

本文档是对现有架构的**扩展**而非替代。现有文档描述的存储策略（向量+图+KV 混合）保持不变，本文档在其上增加了：

1. 新的 `trait` memory_type（含 trend/candidate/emerging/established/core 五阶段生命周期）
2. trait 的三层子类（behavior/preference/core）、置信度模型、情境标注
3. reflection 引擎的升级/矛盾处理/趋势检测机制
4. 废弃 `insight` memory_type（降级为 trait 的 trend 阶段）
5. 废弃 `general` memory_type

实施时需同步更新 `memory-architecture.md` 中的记忆类型表。

## 附录 B：全球调研报告索引

| 编号 | 方向 | 文件 | 关键贡献 |
|------|------|------|----------|
| #01 | 认知心理学 | `research/01-cognitive-psychology.md` | Tulving/Conway/Mischel 理论验证；程序性记忆/前瞻记忆遗漏；衰减间隔效应 |
| #02 | Generative Agents 学术研究 | `research/02-generative-agents.md` | 反思触发机制；召回即强化；两阶段反思；RGMem/A-MEM 前沿 |
| #03 | MemGPT / Letta | `research/03-memgpt-letta.md` | 工作记忆提交接口；重要性预评分；Zettelkasten 横向关联 |
| #04 | 商业记忆系统 | `research/04-commercial-systems.md` | Mem0/Zep/Cognee 架构对比；V2 遗忘机制最完善；Zep 双时间线 |
| #05 | Personal AI | `research/05-personal-ai.md` | LLM 人格推断精度 r=0.27；证据质量分级；情境标注前置；敏感特质保护 |
