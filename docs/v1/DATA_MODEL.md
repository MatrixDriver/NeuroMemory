# 数据模型

> 返回 [主架构文档](ARCHITECTURE.md)

---

## 目录

- [向量存储数据模型 (Qdrant)](#向量存储数据模型-qdrant)
- [图谱存储数据模型 (Neo4j)](#图谱存储数据模型-neo4j)
- [用户隔离模型](#用户隔离模型)

---

## 向量存储数据模型 (Qdrant) `[✅ 已实现]`

```
Collection: neuro_memory_{provider}_{dims}
例如: 
  - neuro_memory_huggingface_384  (本地 HuggingFace)
  - neuro_memory_gemini_768       (Google Gemini)
  - neuro_memory_openai_1024      (SiliconFlow bge-m3)

Document Schema:
┌─────────────────────────────────────────────────────────────────┐
│  {                                                              │
│    "id": "uuid-v4",                                             │
│    "vector": [0.12, -0.34, ...],  // 384/768/1024 维            │
│    "payload": {                                                 │
│      "memory": "DeepMind 是 Google 的子公司",                    │
│      "user_id": "user_001",                                     │
│      "created_at": "2026-01-12T10:00:00Z",                      │
│      "metadata": { ... }                                        │
│    }                                                            │
│  }                                                              │
└─────────────────────────────────────────────────────────────────┘
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID | 记忆唯一标识 |
| `vector` | float[] | 嵌入向量 (384/768/1024 维) |
| `payload.memory` | string | 原始文本内容 |
| `payload.user_id` | string | 用户标识 |
| `payload.created_at` | datetime | 创建时间 |
| `payload.metadata` | object | 可选扩展元数据 |

### Embedding 维度对照

| 提供商 | 模型 | 维度 |
|--------|------|------|
| Local (HuggingFace) | paraphrase-multilingual-MiniLM-L12-v2 | 384 |
| Gemini | text-embedding-004 | 768 |
| SiliconFlow | BAAI/bge-m3 | 1024 |

---

## 图谱存储数据模型 (Neo4j) `[✅ 已实现]`

### 节点 (Nodes)

```
┌─────────────────────────────────────────────────────────────────┐
│  (:Entity {                                                     │
│    name: "DeepMind",                                            │
│    type: "Organization",                                        │
│    user_id: "user_001",                                         │
│    created_at: datetime()                                       │
│  })                                                             │
└─────────────────────────────────────────────────────────────────┘
```

| 属性 | 类型 | 说明 |
|------|------|------|
| `name` | string | 实体名称 |
| `type` | string | 实体类型 (Person, Organization, etc.) |
| `user_id` | string | 所属用户 |
| `created_at` | datetime | 创建时间 |

### 关系 (Relationships)

```
┌─────────────────────────────────────────────────────────────────┐
│  (:Entity {name: "DeepMind"})                                   │
│       -[:SUBSIDIARY_OF {                                        │
│           user_id: "user_001",                                  │
│           source: "user input"                                  │
│         }]->                                                    │
│  (:Entity {name: "Google"})                                     │
└─────────────────────────────────────────────────────────────────┘
```

| 属性 | 类型 | 说明 |
|------|------|------|
| `user_id` | string | 所属用户 |
| `source` | string | 关系来源 |

### 示例图谱

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   (Demis Hassabis)──[CEO_OF]──►(DeepMind)──[SUBSIDIARY_OF]──►(Google)
│                                    │                            │
│                                    │                            │
│                               [CREATED]                         │
│                                    │                            │
│                                    ▼                            │
│                               (Gemini)                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 用户隔离模型 `[✅ 已实现]`

```
┌─────────────────────────────────────────────────────────────────┐
│                      用户数据隔离策略                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  方式: 基于 user_id 字段的逻辑隔离                               │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Qdrant: payload.user_id 过滤                           │   │
│  │  Neo4j: 节点/边属性 user_id 过滤                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  查询示例:                                                       │
│  • Qdrant: filter={"user_id": "user_001"}                      │
│  • Neo4j: MATCH (n {user_id: "user_001"})                      │
│                                                                 │
│  注意: 这是逻辑隔离，不是物理隔离。适用于单租户或信任环境。        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 隔离机制说明

| 存储 | 隔离方式 | 查询过滤 |
|------|----------|----------|
| Qdrant | payload.user_id | `filter={"user_id": "xxx"}` |
| Neo4j | 节点/边属性 | `MATCH (n {user_id: "xxx"})` |

### 适用场景

- ✅ 单租户应用
- ✅ 信任环境下的多用户
- ❌ 多租户 SaaS（需要物理隔离）

---

## 相关文档

- [接口设计](API.md) - 如何操作数据
- [配置参考](CONFIGURATION.md) - 数据库连接配置
