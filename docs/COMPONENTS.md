# 核心组件设计

> 返回 [主架构文档](ARCHITECTURE.md)
>
> **最后更新**: 2026-01-24

---

## 目录

- [组件总览](#组件总览)
- [配置模块 (config.py)](#配置模块-configpy)
- [核心处理引擎 (private_brain.py)](#核心处理引擎-private_brainpy)
  - [检索流程](#检索流程)
  - [Session 管理集成](#session-管理集成)
- [Session 管理器 (session_manager.py)](#session-管理器-session_managerpy)
- [指代消解器 (coreference.py)](#指代消解器-coreferencepy)
- [Session 整合器 (consolidator.py)](#session-整合器-consolidatorpy)
- [隐私过滤器 (privacy_filter.py)](#隐私过滤器-privacy_filterpy)
- [Mem0 集成层](#mem0-集成层)

---

## 组件总览

```
┌─────────────────────────────────────────────────────────────────┐
│                         组件依赖图                              │
└─────────────────────────────────────────────────────────────────┘

                    ┌───────────────────┐
                    │  http_server.py   │
                    │  mcp_server.py    │
                    │  neuromemory/cli  │
                    │  (接入层)          │
                    └─────────┬─────────┘
                              │
                              ▼
                    ┌───────────────────┐
                    │  private_brain.py │
                    │  (核心处理引擎)    │
                    └─────────┬─────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│session_manager│   │coreference.py │   │privacy_filter │
└───────┬───────┘   └───────┬───────┘   └───────┬───────┘
        │                   │                   │
        │                   └─────────┬─────────┘
        │                             │
        ▼                             ▼
┌───────────────┐           ┌───────────────┐
│consolidator.py│           │  Mem0 Memory  │
│               │           │  (集成层)      │
└───────┬───────┘           └───────┬───────┘
        │                           │
        └───────────┬───────────────┘
                    │
                    ▼
    ┌─────────────────────────────────────────────────────────────┐
    │                    MEM0_CONFIG                              │
    │  ┌─────────────┐ ┌─────────────┐ ┌────────────┐ ┌────────┐ │
    │  │vector_store │ │ graph_store │ │    llm     │ │embedder│ │
    │  │  (Qdrant)   │ │  (Neo4j)    │ │(DeepSeek/  │ │(Local/ │ │
    │  │             │ │             │ │ Gemini)    │ │Gemini/ │ │
    │  │             │ │             │ │            │ │Silicon)│ │
    │  └─────────────┘ └─────────────┘ └────────────┘ └────────┘ │
    └─────────────────────────────────────────────────────────────┘
```

---

## 配置模块 (config.py) `[✅ 已实现]`

**职责**: 集中管理所有配置，提供模型切换能力

```python
# 配置结构
config.py
├── API 密钥管理
│   ├── GOOGLE_API_KEY
│   ├── DEEPSEEK_API_KEY
│   └── SILICONFLOW_API_KEY   # 新增
├── 模型切换开关
│   ├── LLM_PROVIDER: "gemini" | "deepseek"
│   ├── EMBEDDING_PROVIDER: "gemini" | "local" | "siliconflow"  # 新增 siliconflow
│   └── ENABLE_GRAPH_STORE: bool
├── 模型配置详情
│   ├── GEMINI_CONFIG
│   ├── DEEPSEEK_CONFIG
│   ├── LOCAL_EMBEDDING_CONFIG
│   └── SILICONFLOW_EMBEDDING_CONFIG  # 新增
└── 配置生成函数
    ├── _get_llm_config()
    ├── _get_embedder_config()
    ├── _get_collection_name()
    └── get_chat_config()
```

### 关键设计决策

- Collection 名称包含 provider 和维度信息，避免向量维度冲突
- DeepSeek 使用 OpenAI 兼容接口
- SiliconFlow 使用 OpenAI 兼容接口 (BAAI/bge-m3, 1024 维)
- 图谱存储可通过开关禁用

### Embedding 提供商对比

| 提供商 | 模型 | 维度 | 说明 |
|--------|------|------|------|
| local | paraphrase-multilingual-MiniLM-L12-v2 | 384 | 本地 HuggingFace，无 API 成本 |
| gemini | text-embedding-004 | 768 | Google API |
| siliconflow | BAAI/bge-m3 | 1024 | 国内云端，高精度，OpenAI 兼容接口 |

---

## 核心处理引擎 (private_brain.py) `[✅ 已实现]`

**职责**: 实现核心记忆处理逻辑，采用 Y 型分流架构

| 类/方法 | 职责 | 状态 |
|---------|------|------|
| `PrivateBrain` | 核心处理类，封装记忆检索和存储 | ✅ |
| `process()` / `process_async()` | 处理用户输入（生产模式） | ✅ |
| `process_debug()` | 调试模式，返回自然语言报告 | ✅ |
| `search()` | 仅检索，不存储 | ✅ |
| `ask()` | 基于记忆回答问题（检索 + LLM 生成） | ✅ |
| `add()` | 直接添加记忆（跳过隐私过滤） | ✅ |
| `get_user_graph()` | 获取用户知识图谱 | ✅ |
| `end_session()` / `end_session_async()` | 显式结束 Session | ✅ |
| `_retrieve()` | 内部检索方法 | ✅ |

### 检索流程

**处理流程**：

```python
async def process_async(self, input_text: str, user_id: str) -> dict:
    """
    处理流程：
    1. 获取或创建 Session
    2. 获取最近事件进行指代消解
    3. 使用消解后的查询检索长期记忆
    4. 创建 Event 并添加到 Session
    5. 返回格式（memories/relations/resolved_query）
    """
    # 1. Session 管理
    await self.session_manager.get_or_create_session(user_id)
    
    # 2. 指代消解（检索时，规则匹配）
    context_events = await self.session_manager.get_session_events(user_id, limit=5)
    resolved_query = self.coreference_resolver.resolve_query(input_text, context_events)
    
    # 3. 检索长期记忆
    result = self._retrieve(resolved_query, user_id)
    result.resolved_query = resolved_query
    
    # 4. 添加事件到 Session
    event = Event(role="user", content=input_text, ...)
    await self.session_manager.add_event(user_id, event)
    
    return result.to_dict()
```

### Session 管理集成

**Session 管理**：`PrivateBrain` 集成 Session 管理器，自动管理短期记忆：

- 每次 `process()` 调用时自动获取或创建 Session
- 将用户输入作为 Event 添加到 Session
- Session 超时或显式结束时，触发整合流程

---

## Session 管理器 (session_manager.py) `[✅ 已实现]`

**职责**: 管理用户 Session 生命周期，提供短期记忆存储

| 类/方法 | 职责 | 状态 |
|---------|------|------|
| `SessionManager` | Session 生命周期管理器 | ✅ |
| `get_or_create_session()` | 获取或创建用户 Session | ✅ |
| `add_event()` | 向 Session 添加事件 | ✅ |
| `get_session_events()` | 获取最近事件（用于指代消解） | ✅ |
| `end_session()` | 结束 Session，触发整合 | ✅ |
| `_check_timeouts()` | 定期检查超时 Session | ✅ |

**关键特性**：
- 内部自动管理，用户无感知
- 支持超时自动结束（默认 30 分钟）
- 支持最大事件数限制（默认 100 条）
- 支持最大存活时间（默认 24 小时）

---

## 指代消解器 (coreference.py) `[✅ 已实现]`

**职责**: 提供两种消解方式：检索时规则匹配，整合时 LLM 消解

| 类/方法 | 职责 | 状态 |
|---------|------|------|
| `CoreferenceResolver` | 指代消解器 | ✅ |
| `resolve_query()` | 检索时消解（规则匹配，快速） | ✅ |
| `resolve_events()` | 整合时消解（LLM，准确） | ✅ |

**检索时消解**（规则匹配）：
- 从最近事件中提取上下文
- 规则匹配："这个/那个"→名词、"她/他"→人名、"它"→事物
- 快速响应，不调用 LLM

**整合时消解**（LLM）：
- Session 结束时，使用 LLM 对事件进行语义分组和指代消解
- 生成可独立理解的记忆片段
- 支持跨轮次指代（如"这个"→"桔子"）

---

## Session 整合器 (consolidator.py) `[✅ 已实现]`

**职责**: 将 Session 中的短期记忆整合为长期记忆

| 类/方法 | 职责 | 状态 |
|---------|------|------|
| `SessionConsolidator` | Session 整合器 | ✅ |
| `consolidate()` | 整合 Session 到长期记忆 | ✅ |

**整合流程**：
1. 跳过空 Session
2. LLM 指代消解 + 语义分组（`coreference.resolve_events()`）
3. 隐私过滤（`privacy_filter.classify()`）
4. 存储 PRIVATE 数据到长期记忆（Qdrant + Neo4j）

**性能**：后台异步执行，不阻塞用户

---

## 隐私过滤器 (privacy_filter.py) `[✅ 已实现]`

**职责**: 使用 LLM 判断用户输入是否为私有数据

| 类/方法 | 职责 | 状态 |
|---------|------|------|
| `PrivacyFilter` | LLM 驱动的隐私分类器 | ✅ |
| `classify()` | 判断文本是否为私有数据 | ✅ |

**分类规则**：
- **PRIVATE**：个人偏好、经历、私有实体关系、个人计划 → 存储
- **PUBLIC**：通用知识、百科事实、公共信息、问句 → 不存储

**策略**：分类失败时默认按 PRIVATE 处理（宁可多存不漏存）

---

## Mem0 集成层 `[✅ 已实现]`

**职责**: 抽象底层存储，提供统一的记忆操作接口

### Mem0 Framework 提供的核心能力

| 能力 | 说明 |
|------|------|
| **混合存储** | 同时写入 Vector Store 和 Graph Store |
| **实体提取** | 使用 LLM 从文本中提取实体和关系 |
| **混合检索** | 并行查询向量库和图谱，融合结果 |
| **自动去重** | 基于语义相似度的记忆去重 |

### 集成配置示例

```python
MEM0_CONFIG = {
    "vector_store": {
        "provider": "qdrant",
        "config": {
            "host": "localhost",
            "port": 6400,  # 统一使用 6400 端口
            "collection_name": "neuro_memory_openai_1024",  # 自动生成
            "embedding_model_dims": 1024,  # 明确指定向量维度
        }
    },
    "graph_store": {  # 可通过 ENABLE_GRAPH_STORE 开关禁用
        "provider": "neo4j",
        "config": {
            "url": "bolt://localhost:17687",  # 单实例使用 bolt://，集群使用 neo4j://
            "username": "neo4j",
            "password": "railway2025",
        }
    },
    "llm": {
        "provider": "openai",  # DeepSeek 使用 OpenAI 兼容接口
        "config": {
            "model": "deepseek-chat",
            "temperature": 0.0,
            "openai_base_url": "https://api.deepseek.com",
        }
    },
    "embedder": {
        "provider": "openai",  # SiliconFlow 使用 OpenAI 兼容接口
        "config": {
            "model": "BAAI/bge-m3",
            "embedding_dims": 1024,
            "openai_base_url": "https://api.siliconflow.cn/v1",
            "api_key": SILICONFLOW_API_KEY,
        }
    }
}

brain = Memory.from_config(MEM0_CONFIG)
```

---

## 相关文档

- [接口设计](API.md) - 完整 API 定义
- [数据模型](DATA_MODEL.md) - 数据结构说明
- [配置参考](CONFIGURATION.md) - 详细配置选项
- [Session 记忆管理](SESSION_MEMORY_DESIGN.md) - Session 管理设计文档