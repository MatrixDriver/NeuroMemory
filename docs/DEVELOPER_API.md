# NeuroMemory 开发者接口文档

> 面向项目开发者的高级接口文档 | 返回 [主架构文档](ARCHITECTURE.md)
>
> **版本**: v3.0  
> **最后更新**: 2026-01-24
>
> **注意**：本文档面向项目开发者、测试人员和需要细粒度控制的场景。普通用户应使用 [用户接口文档](USER_API.md) 中的 `/process` 接口。

---

## 目录

- [概述](#概述)
- [接口列表](#接口列表)
- [API 端点](#api-端点)
  - [添加记忆](#1-添加记忆)
  - [混合检索](#2-混合检索)
  - [基于记忆问答](#3-基于记忆问答)
  - [获取知识图谱](#4-获取知识图谱)
  - [详细健康检查](#5-详细健康检查)
- [使用场景](#使用场景)
- [注意事项](#注意事项)

---

## 概述

开发者接口（`/api/v1/*`）提供了细粒度的记忆操作接口，适用于：

- **测试和调试**：需要单独测试某个功能模块
- **批量导入**：需要跳过隐私过滤直接存储数据
- **特殊场景**：需要 LLM 生成完整回答而非仅返回记忆上下文
- **系统集成**：需要精确控制每个操作步骤

**与用户接口的区别**：

| 特性 | 用户接口 (`/process`) | 开发者接口 (`/api/v1/*`) |
|------|----------------------|------------------------|
| 隐私过滤 | ✅ 自动执行 | ❌ 跳过（`/api/v1/memory`） |
| Session 管理 | ✅ 自动管理 | ❌ 不涉及 |
| 指代消解 | ✅ 自动执行 | ❌ 不涉及 |
| 存储决策 | ✅ 自动判断 | ⚠️ 需手动调用 |
| 适用场景 | 生产环境、普通用户 | 测试、调试、特殊场景 |

### 基本信息

| 项目 | 说明 |
|------|------|
| **Base URL（本地）** | `http://localhost:8765` |
| **Base URL（ZeaBur 远程）** | `https://neuromemory.zeabur.app` |
| **路径前缀** | `/api/v1` |
| **协议** | HTTP/HTTPS |
| **数据格式** | JSON |

---

## 接口列表

| 端点 | 方法 | 说明 | 用途 |
|------|------|------|------|
| `/api/v1/memory` | POST | 添加记忆（跳过隐私过滤） | 开发者测试、批量导入、强制存储 |
| `/api/v1/memory/search` | GET | 混合检索（只检索，不存储） | 仅需要检索结果的场景 |
| `/api/v1/ask` | POST | 基于记忆回答问题（检索 + LLM 生成） | 需要 LLM 生成完整回答 |
| `/api/v1/graph` | GET | 获取知识图谱 | 与 `/graph/{user_id}` 功能相同 |
| `/api/v1/health` | GET | 详细健康检查（含 components） | 排查数据库与 LLM 配置 |

---

## API 端点

### 1. 添加记忆

直接添加记忆到长期存储，**跳过隐私过滤**。适用于测试、批量导入等场景。

#### 请求

```
POST /api/v1/memory
Content-Type: application/json
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `content` | string | ✅ | 要记忆的文本内容 |
| `user_id` | string | ⚠️ | 用户标识（默认: "default"） |
| `metadata` | object | ❌ | 可选元数据 |

#### 请求示例

```json
{
    "content": "张三是李四的老板",
    "user_id": "test_user",
    "metadata": {
        "source": "manual_import",
        "timestamp": "2026-01-24T10:00:00Z"
    }
}
```

#### 响应示例

```json
{
    "memory_id": "mem_abc123def456"
}
```

#### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `memory_id` | string | 记忆唯一标识 |

#### 注意事项

- ⚠️ **跳过隐私过滤**：此接口会直接将内容存储，不会进行 PRIVATE/PUBLIC 分类
- ⚠️ **不涉及 Session**：直接写入长期记忆，不会经过 Session 管理流程
- ✅ **适用场景**：测试数据导入、批量迁移、已知安全的数据存储

---

### 2. 混合检索

仅执行检索操作，不进行存储。返回语义检索和知识图谱检索的结果。

#### 请求

```
GET /api/v1/memory/search
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `query` | string | ✅ | 查询文本 |
| `user_id` | string | ⚠️ | 用户标识（默认: "default"） |
| `limit` | integer | ❌ | 返回数量上限（默认: 10） |

#### 请求示例

**Bash / Git Bash：**
```bash
curl "http://localhost:8765/api/v1/memory/search?query=张三管理什么&user_id=test_user&limit=5"
```

**PowerShell 7：**
```powershell
Invoke-RestMethod -Uri "http://localhost:8765/api/v1/memory/search?query=张三管理什么&user_id=test_user&limit=5" -Method Get
```

#### 响应示例

```json
{
    "memories": [
        {
            "content": "张三是技术部门的负责人",
            "score": 0.89,
            "source": "vector"
        },
        {
            "content": "张三负责管理李四和王五",
            "score": 0.85,
            "source": "vector"
        }
    ],
    "relations": [
        {
            "source": "张三",
            "relation": "管理",
            "target": "李四",
            "source": "graph"
        }
    ],
    "metadata": {
        "retrieval_time_ms": 45,
        "vector_count": 2,
        "graph_count": 1
    }
}
```

#### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `memories` | array | 语义检索匹配的记忆片段 |
| `memories[].content` | string | 记忆内容 |
| `memories[].score` | number | 相似度分数 (0-1) |
| `memories[].source` | string | 来源类型：`vector` 或 `graph` |
| `relations` | array | 知识图谱中的关系三元组 |
| `relations[].source` | string | 关系起点实体 |
| `relations[].relation` | string | 关系类型 |
| `relations[].target` | string | 关系终点实体 |
| `metadata.retrieval_time_ms` | number | 检索耗时（毫秒） |
| `metadata.vector_count` | number | 向量检索结果数量 |
| `metadata.graph_count` | number | 图谱检索结果数量 |

#### 注意事项

- ✅ **只检索，不存储**：此接口不会触发任何存储操作
- ✅ **适用场景**：仅需要检索结果的场景，如搜索功能、数据分析

---

### 3. 基于记忆问答

基于记忆检索 + LLM 生成完整回答。与 `/process` 接口的区别是，此接口会调用 LLM 生成完整的自然语言回答。

#### 请求

```
POST /api/v1/ask
Content-Type: application/json
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `question` | string | ✅ | 用户问题 |
| `user_id` | string | ⚠️ | 用户标识（默认: "default"） |

#### 请求示例

```json
{
    "question": "张三管理什么项目？",
    "user_id": "test_user"
}
```

#### 响应示例

```json
{
    "answer": "根据记忆，张三负责管理技术部门，具体管理李四和王五等团队成员。",
    "sources": [
        {
            "content": "张三是技术部门的负责人",
            "score": 0.89,
            "source": "vector"
        },
        {
            "source": "张三",
            "relation": "管理",
            "target": "李四",
            "source": "graph"
        }
    ]
}
```

#### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `answer` | string | LLM 生成的完整回答 |
| `sources` | array | 用于生成回答的记忆来源 |

#### 注意事项

- ⚠️ **需要 LLM 调用**：此接口会调用 LLM 生成回答，需要配置 LLM（DeepSeek/Gemini）
- ⚠️ **响应时间较长**：由于需要 LLM 生成，响应时间比 `/process` 接口更长
- ✅ **适用场景**：需要完整自然语言回答的场景，如问答系统、对话机器人

---

### 4. 获取知识图谱

获取用户的知识图谱结构。与 `/graph/{user_id}` 功能相同，但使用查询参数而非路径参数。

#### 请求

```
GET /api/v1/graph
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_id` | string | ⚠️ | 用户标识（默认: "default"） |
| `depth` | integer | ❌ | 遍历深度（默认: 2，预留参数） |

#### 请求示例

**Bash / Git Bash：**
```bash
curl "http://localhost:8765/api/v1/graph?user_id=test_user&depth=2"
```

**PowerShell 7：**
```powershell
Invoke-RestMethod -Uri "http://localhost:8765/api/v1/graph?user_id=test_user&depth=2" -Method Get
```

#### 响应示例

```json
{
    "status": "success",
    "user_id": "test_user",
    "nodes": [
        {"id": "张三", "name": "张三"},
        {"id": "李四", "name": "李四"},
        {"id": "技术部门", "name": "技术部门"}
    ],
    "edges": [
        {"source": "张三", "relationship": "管理", "target": "李四"},
        {"source": "张三", "relationship": "属于", "target": "技术部门"}
    ],
    "memories": [
        {
            "id": "mem_001",
            "memory": "张三是技术部门的负责人"
        }
    ],
    "graph_relations": [
        {"source": "张三", "relationship": "管理", "target": "李四"}
    ],
    "metadata": {
        "memory_count": 1,
        "relation_count": 1
    }
}
```

#### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `nodes` | array | 图谱节点列表，每个节点包含 `id` 和 `name` |
| `edges` | array | 图谱边列表，每个边包含 `source`、`relationship`、`target` |
| `memories` | array | 相关记忆列表，每个记忆包含 `id` 和 `memory` |
| `graph_relations` | array | 图谱关系三元组，每个关系包含 `source`、`relationship`、`target` |
| `metadata` | object | 统计信息，包含 `memory_count` 和 `relation_count` |

---

### 5. 详细健康检查

返回服务状态及各个组件的健康状态，用于排查数据库与 LLM 配置问题。

#### 请求

```
GET /api/v1/health
```

#### 响应示例

```json
{
    "status": "healthy",
    "service": "neuro-memory",
    "components": {
        "neo4j": true,
        "qdrant": true,
        "llm": true
    }
}
```

#### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | string | 整体状态：`healthy` 或 `unhealthy` |
| `service` | string | 服务名称 |
| `components.neo4j` | boolean | Neo4j 连接状态 |
| `components.qdrant` | boolean | Qdrant 连接状态 |
| `components.llm` | boolean | LLM 配置状态 |

#### 注意事项

- ✅ **详细诊断**：比 `/health` 接口提供更详细的组件状态
- ✅ **适用场景**：排查数据库连接问题、LLM 配置问题

---

## 使用场景

### 场景 1：测试数据导入

```python
import requests

BASE_URL = "http://localhost:8765"

# 批量导入测试数据（跳过隐私过滤）
test_data = [
    "张三是技术部门的负责人",
    "李四是前端开发工程师",
    "王五是后端开发工程师"
]

for content in test_data:
    response = requests.post(
        f"{BASE_URL}/api/v1/memory",
        json={"content": content, "user_id": "test_user"}
    )
    print(f"导入: {content} -> {response.json()['memory_id']}")
```

### 场景 2：仅检索不存储

```python
# 仅需要检索结果，不触发存储
response = requests.get(
    f"{BASE_URL}/api/v1/memory/search",
    params={"query": "张三管理什么", "user_id": "test_user", "limit": 5}
)
results = response.json()
print(f"找到 {len(results['memories'])} 条记忆")
```

### 场景 3：需要 LLM 生成回答

```python
# 需要完整的自然语言回答
response = requests.post(
    f"{BASE_URL}/api/v1/ask",
    json={"question": "张三管理什么项目？", "user_id": "test_user"}
)
result = response.json()
print(f"回答: {result['answer']}")
print(f"来源: {len(result['sources'])} 条记忆")
```

---

## 注意事项

### 1. 隐私过滤

- `/api/v1/memory` **跳过隐私过滤**，直接存储数据
- 生产环境使用需谨慎，确保数据已通过其他方式验证

### 2. Session 管理

- 开发者接口**不涉及 Session 管理**
- 不会自动进行指代消解
- 不会触发记忆整合流程

### 3. 性能考虑

- `/api/v1/ask` 需要 LLM 调用，响应时间较长
- 生产环境建议使用 `/process` 接口，性能更优

### 4. 错误处理

所有接口遵循统一的错误处理策略：

- HTTP 状态码：`200`（成功）、`422`（参数验证失败）、`500`（服务器错误）
- 错误响应格式：包含 `error` 字段的错误信息

---

## 相关文档

- [用户接口文档](USER_API.md) - 面向普通客户的接口文档
- [接口总览](API.md) - 查看所有接口类型（REST API、CLI）
- [快速开始](GETTING_STARTED.md) - 环境配置和启动

---

*文档结束*
