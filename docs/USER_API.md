# NeuroMemory 用户接口文档

> 面向普通客户的用户接口文档 | 返回 [主架构文档](ARCHITECTURE.md)
>
> **最后更新**: 2026-01-24
>
> **注意**：本文档涵盖所有 REST API 端点。

---

## 目录

- [概述](#概述)
- [快速开始](#快速开始)
- [API 端点](#api-端点)
  - [处理记忆 (生产模式)](#1-处理记忆生产模式)
  - [处理记忆 (调试模式)](#2-处理记忆调试模式)
  - [获取用户知识图谱](#3-获取用户知识图谱)
  - [结束会话](#4-结束会话)
  - [获取会话状态](#5-获取会话状态)
  - [健康检查](#6-健康检查)
  - [纯检索](#7-纯检索)
  - [基于记忆问答](#8-基于记忆问答)
- [响应格式](#响应格式)
- [错误处理](#错误处理)
- [使用示例](#使用示例)
- [DIFY 集成指南](#dify-集成指南)

---

## 概述

NeuroMemory 用户接口提供了简单易用的记忆服务接口，基于 FastAPI 构建。该服务将用户输入视为"刺激"，通过 Y 型分流架构同时执行：

- **同步路径**: 立即检索相关记忆，返回结构化上下文
- **异步路径**: 后台进行隐私分类和记忆存储

**核心特点**：
- **统一接口**：`POST /process` 接口自动判断是查询还是存储，无需区分
- **智能处理**：系统内部自动进行隐私分类、指代消解、记忆整合
- **即插即用**：适合集成到 DIFY、LangChain 等 LLM 工作流中

### 基本信息

| 项目 | 说明 |
|------|------|
| **Base URL（本地）** | `http://localhost:8765` |
| **Base URL（Railway 远程）** | `https://<your-app>.up.railway.app` |
| **协议** | HTTP/HTTPS |
| **数据格式** | JSON |
| **认证** | 无（建议在生产环境中通过网关添加认证） |

### 启动服务

```bash
# 开发模式（自动重载）
uvicorn http_server:app --host 0.0.0.0 --port 8765 --reload

# 生产模式
uvicorn http_server:app --host 0.0.0.0 --port 8765 --workers 4
```

---

## 快速开始

### 1. 存储一条记忆并查询

**Bash / Git Bash：**
```bash
# 步骤1: 本地 - 存储记忆（系统会自动判断是否为私有数据）
curl -X POST http://localhost:8765/process \
  -H "Content-Type: application/json" \
  -d '{"input": "我女儿叫灿灿，今年5岁了", "user_id": "user_001"}'

# 步骤1: 远程 - 存储记忆
curl -X POST https://<your-app>.up.railway.app/process \
  -H "Content-Type: application/json" \
  -d '{"input": "我女儿叫灿灿，今年5岁了", "user_id": "user_001"}'

# 步骤2: 本地 - 结束会话（⚠️ 必须调用此接口触发存储，否则需等30分钟超时）
curl -X POST http://localhost:8765/end-session \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user_001"}'

# 步骤2: 远程 - 结束会话
curl -X POST https://<your-app>.up.railway.app/end-session \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user_001"}'

# 步骤3: 本地 - 查询记忆（现在可以查询到刚才存储的记忆）
curl -X POST http://localhost:8765/process \
  -H "Content-Type: application/json" \
  -d '{"input": "我女儿叫什么名字？", "user_id": "user_001"}'

# 步骤3: 远程 - 查询记忆
curl -X POST https://<your-app>.up.railway.app/process \
  -H "Content-Type: application/json" \
  -d '{"input": "我女儿叫什么名字？", "user_id": "user_001"}'
```

**PowerShell 7：**
```powershell
# 步骤1: 本地 - 存储记忆
$body = @{
    input = "我女儿叫灿灿，今年5岁了"
    user_id = "user_001"
} | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:8765/process" -Method Post -ContentType "application/json" -Body $body

# 步骤1: 远程 - 存储记忆
$body = @{
    input = "我女儿叫灿灿，今年5岁了"
    user_id = "user_001"
} | ConvertTo-Json
Invoke-RestMethod -Uri "https://<your-app>.up.railway.app/process" -Method Post -ContentType "application/json" -Body $body

# 步骤2: 本地 - 结束会话（⚠️ 必须调用此接口触发存储，否则需等30分钟超时）
$body = @{ user_id = "user_001" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:8765/end-session" -Method Post -ContentType "application/json" -Body $body

# 步骤2: 远程 - 结束会话
$body = @{ user_id = "user_001" } | ConvertTo-Json
Invoke-RestMethod -Uri "https://<your-app>.up.railway.app/end-session" -Method Post -ContentType "application/json" -Body $body

# 步骤3: 本地 - 查询记忆（使用 curl.exe）
curl.exe -X POST http://localhost:8765/process `
  -H "Content-Type: application/json" `
  -d '{"input": "我女儿叫什么名字？", "user_id": "user_001"}'

# 步骤3: 远程 - 查询记忆（使用 curl.exe）
curl.exe -X POST https://<your-app>.up.railway.app/process `
  -H "Content-Type: application/json" `
  -d '{"input": "我女儿叫什么名字？", "user_id": "user_001"}'
```

> **重要提示**：`/process` 接口的记忆存储是异步的。必须显式调用 `/end-session` 接口才能触发系统将短期记忆整合为长期记忆。如果不调用此接口，需要等待 30 分钟会话超时后才能查询到结果。

### 2. 查看用户知识图谱

**Bash / Git Bash：**
```bash
# 本地
curl http://localhost:8765/graph/user_001

# 远程
curl https://<your-app>.up.railway.app/graph/user_001
```

**PowerShell 7：**
```powershell
# 本地
Invoke-RestMethod -Uri "http://localhost:8765/graph/user_001" -Method Get

# 远程
Invoke-RestMethod -Uri "https://<your-app>.up.railway.app/graph/user_001" -Method Get
```

---

## API 端点

### 1. 处理记忆（生产模式）

处理用户输入，检索相关记忆并异步存储。返回结构化 JSON，适合注入到 LLM prompt 中。

**这是核心接口**，系统内部自动判断是查询还是存储，无需区分。

#### 请求

```
POST /process
Content-Type: application/json
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `input` | string | ✅ | 用户输入（查询或陈述） |
| `user_id` | string | ✅ | 用户唯一标识 |

#### 请求示例

```json
{
    "input": "小朱的女儿叫什么？",
    "user_id": "user_001"
}
```

#### 响应示例（有记忆）

```json
{
    "status": "success",
    "resolved_query": "小朱的女儿叫什么？",
    "memories": [
        {
            "content": "灿灿还有一个弟弟，叫帅帅",
            "score": 0.87
        },
        {
            "content": "小朱有两个孩子",
            "score": 0.82
        }
    ],
    "relations": [
        {
            "source": "小朱",
            "relation": "女儿",
            "target": "灿灿"
        },
        {
            "source": "灿灿",
            "relation": "弟弟",
            "target": "帅帅"
        }
    ],
    "metadata": {
        "retrieval_time_ms": 123,
        "has_memory": true
    }
}
```

#### 响应示例（无记忆）

```json
{
    "status": "success",
    "resolved_query": "小朱的女儿叫什么？",
    "memories": [],
    "relations": [],
    "metadata": {
        "retrieval_time_ms": 15,
        "has_memory": false
    }
}
```

#### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | string | 处理状态：`success` 或 `error` |
| `resolved_query` | string | 指代消解后的查询（便于调试） |
| `memories` | array | 语义检索匹配的记忆片段 |
| `memories[].content` | string | 记忆内容 |
| `memories[].score` | number | 相似度分数 (0-1) |
| `relations` | array | 知识图谱中的关系三元组 |
| `relations[].source` | string | 关系起点实体 |
| `relations[].relation` | string | 关系类型 |
| `relations[].target` | string | 关系终点实体 |
| `metadata.retrieval_time_ms` | number | 检索耗时（毫秒） |
| `metadata.has_memory` | boolean | 是否检索到相关记忆 |

---

### 2. 处理记忆（调试模式）

返回详细的处理过程报告（自然语言格式），用于开发调试和验证系统行为。

**注意：** 调试模式走**旧版流程**，不与生产模式一致：**不写 Session、不做指代消解**，仅演示「检索 + 隐私分类 + 存储决策」；用于观察分类与存储行为时使用。生产级流程（Session、指代消解）请使用 `POST /process`。

#### 请求

```
POST /debug
Content-Type: application/json
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `input` | string | ✅ | 用户输入 |
| `user_id` | string | ✅ | 用户唯一标识 |

#### 请求示例

```json
{
    "input": "小朱的儿子叫什么",
    "user_id": "user_001"
}
```

#### 响应示例

```json
{
    "report": "=== 检索过程 ===\n[向量检索] 查询: \"小朱的儿子叫什么\"\n  - 匹配: \"灿灿还有一个弟弟，叫帅帅\" (score: 0.87)\n  - 匹配: \"小朱有两个孩子\" (score: 0.82)\n\n[图谱检索] 起始节点: 小朱\n  - 路径1: 小朱 --[女儿]--> 灿灿 --[弟弟]--> 帅帅\n  - 路径2: 小朱 --[有孩子]--> 帅帅\n\n=== 存储决策 ===\n[LLM 分类] 输入类型: 问题查询\n[决策] 不存储 - 这是查询而非新知识\n\n=== 性能统计 ===\n- 向量检索: 45ms\n- 图谱检索: 78ms\n- 总耗时: 123ms"
}
```

#### 报告内容说明

报告包含以下部分：

1. **检索过程**
   - 向量检索：语义匹配结果及分数
   - 图谱检索：实体关系路径

2. **存储决策**
   - LLM 分类结果（PRIVATE/PUBLIC）
   - 存储决策及原因

3. **性能统计**
   - 各阶段耗时
   - 总处理时间

4. **原始数据**（可选）
   - 向量 ID
   - 完整图谱三元组

---

### 3. 获取用户知识图谱

获取指定用户的完整知识图谱结构。

#### 请求

```
GET /graph/{user_id}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_id` | path | ✅ | 用户唯一标识 |

#### 响应示例

```json
{
    "status": "success",
    "user_id": "user_001",
    "memories": [
        {
            "id": "mem_001",
            "memory": "小朱有两个孩子"
        },
        {
            "id": "mem_002",
            "memory": "灿灿是小朱的女儿"
        }
    ],
    "graph_relations": [
        {"source": "小朱", "relationship": "女儿", "target": "灿灿"},
        {"source": "小朱", "relationship": "儿子", "target": "帅帅"},
        {"source": "灿灿", "relationship": "弟弟", "target": "帅帅"}
    ],
    "nodes": [
        {"id": "小朱", "name": "小朱"},
        {"id": "灿灿", "name": "灿灿"},
        {"id": "帅帅", "name": "帅帅"}
    ],
    "edges": [
        {"source": "小朱", "relationship": "女儿", "target": "灿灿"},
        {"source": "小朱", "relationship": "儿子", "target": "帅帅"},
        {"source": "灿灿", "relationship": "弟弟", "target": "帅帅"}
    ],
    "metadata": {
        "memory_count": 2,
        "relation_count": 3
    }
}
```

---

### 4. 结束会话

显式结束用户的当前会话，后台触发短期记忆整合为长期记忆。接口立即返回，整合过程异步执行。

#### 请求

```
POST /end-session
Content-Type: application/json
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_id` | string | ✅ | 用户唯一标识 |

#### 请求示例

```json
{
    "user_id": "user_001"
}
```

#### 响应示例（有活跃会话）

```json
{
    "status": "success",
    "message": "Session ending, consolidation started",
    "session_info": {
        "session_id": "sess_abc123",
        "event_count": 5,
        "duration_seconds": 300,
        "created_at": "2026-01-23T10:00:00",
        "ended_at": "2026-01-23T10:05:00"
    }
}
```

#### 响应示例（无活跃会话）

```json
{
    "status": "success",
    "message": "No active session",
    "session_info": null
}
```

---

### 5. 获取会话状态

获取用户当前会话状态（调试用）。

#### 请求

```
GET /session-status/{user_id}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_id` | path | ✅ | 用户唯一标识 |

#### 响应示例（有活跃会话）

```json
{
    "status": "success",
    "has_active_session": true,
    "session_info": {
        "event_count": 3,
        "created_at": "2026-01-23T10:00:00",
        "last_active_at": "2026-01-23T10:05:00",
        "time_until_timeout_seconds": 1500
    }
}
```

#### 响应示例（无活跃会话）

```json
{
    "status": "success",
    "has_active_session": false,
    "session_info": null
}
```

---

### 6. 健康检查

检查服务运行状态，用于负载均衡器和容器编排的健康探测。

#### 请求

```
GET /health
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

---

### 7. 纯检索

仅执行检索操作，不进行存储，也不写 Session。返回语义检索和知识图谱检索的结果。

适用于只读查询场景，如搜索功能、数据分析。

#### 请求

```
GET /search
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `query` | string | ✅ | 查询文本 |
| `user_id` | string | ⚠️ | 用户标识（默认: "default"） |
| `limit` | integer | ❌ | 返回数量上限（默认: 10） |

#### 请求示例

**Bash / Git Bash：**
```bash
# 本地
curl "http://localhost:8765/search?query=张三管理什么&user_id=test_user&limit=5"

# 远程
curl "https://<your-app>.up.railway.app/search?query=张三管理什么&user_id=test_user&limit=5"
```

**PowerShell 7：**
```powershell
# 本地
Invoke-RestMethod -Uri "http://localhost:8765/search?query=张三管理什么&user_id=test_user&limit=5" -Method Get

# 远程
Invoke-RestMethod -Uri "https://<your-app>.up.railway.app/search?query=张三管理什么&user_id=test_user&limit=5" -Method Get
```

#### 响应示例

```json
{
    "memories": [
        {
            "content": "张三是技术部门的负责人",
            "score": 0.89
        },
        {
            "content": "张三负责管理李四和王五",
            "score": 0.85
        }
    ],
    "relations": [
        {
            "source": "张三",
            "relation": "管理",
            "target": "李四"
        }
    ],
    "metadata": {
        "retrieval_time_ms": 45,
        "has_memory": true
    }
}
```

#### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `memories` | array | 语义检索匹配的记忆片段 |
| `memories[].content` | string | 记忆内容 |
| `memories[].score` | number | 相似度分数 (0-1) |
| `relations` | array | 知识图谱中的关系三元组 |
| `metadata.retrieval_time_ms` | number | 检索耗时（毫秒） |
| `metadata.has_memory` | boolean | 是否检索到相关记忆 |

---

### 8. 基于记忆问答

基于记忆检索 + LLM 生成完整回答。与 `/process` 接口的区别是，此接口会调用 LLM 生成完整的自然语言回答。

#### 请求

```
POST /ask
Content-Type: application/json
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `question` | string | ✅ | 用户问题 |
| `user_id` | string | ⚠️ | 用户标识（默认: "default"） |

#### 请求示例

**Bash / Git Bash：**
```bash
# 本地
curl -X POST http://localhost:8765/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "张三管理什么项目？", "user_id": "test_user"}'

# 远程
curl -X POST https://<your-app>.up.railway.app/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "张三管理什么项目？", "user_id": "test_user"}'
```

**PowerShell 7：**
```powershell
# 本地
$body = @{
    question = "张三管理什么项目？"
    user_id = "test_user"
} | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:8765/ask" -Method Post -ContentType "application/json" -Body $body

# 远程
$body = @{
    question = "张三管理什么项目？"
    user_id = "test_user"
} | ConvertTo-Json
Invoke-RestMethod -Uri "https://<your-app>.up.railway.app/ask" -Method Post -ContentType "application/json" -Body $body
```

#### 响应示例

```json
{
    "answer": "根据记忆，张三负责管理技术部门，具体管理李四和王五等团队成员。",
    "sources": [
        {
            "content": "张三是技术部门的负责人",
            "score": 0.89
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

## 响应格式

### 通用响应结构

所有 API 响应均为 JSON 格式，包含以下通用字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | string | `success` 或 `error` |

### HTTP 状态码

| 状态码 | 说明 |
|--------|------|
| `200` | 请求成功 |
| `422` | 请求参数验证失败 |
| `500` | 服务器内部错误 |

---

## 错误处理

NeuroMemory 采用**静默降级**策略，确保不影响主流程 LLM 的运行。

### 错误响应示例

```json
{
    "status": "error",
    "resolved_query": "用户原始输入",
    "memories": [],
    "relations": [],
    "metadata": {
        "retrieval_time_ms": 0,
        "has_memory": false,
        "error": "Database connection timeout"
    }
}
```

### 错误处理策略

| 错误类型 | 处理方式 |
|----------|----------|
| 检索失败 | 返回空 context，不抛出异常 |
| 存储失败 | 记录日志，不影响响应 |
| LLM 分类失败 | 默认按 PRIVATE 处理（宁可多存不漏存） |

---

## 使用示例

### cURL

**Bash / Git Bash：**
```bash
# 本地 - 处理记忆（生产模式）
curl -X POST http://localhost:8765/process \
  -H "Content-Type: application/json" \
  -d '{
    "input": "我最喜欢的颜色是蓝色",
    "user_id": "user_001"
  }'

# 远程 - 处理记忆
curl -X POST https://<your-app>.up.railway.app/process \
  -H "Content-Type: application/json" \
  -d '{
    "input": "我最喜欢的颜色是蓝色",
    "user_id": "user_001"
  }'

# ⚠️ 重要：结束会话（触发记忆持久化，否则需等30分钟超时）
# 本地
curl -X POST http://localhost:8765/end-session \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user_001"}'
# 远程
curl -X POST https://<your-app>.up.railway.app/end-session \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user_001"}'

# 本地 - 调试模式
curl -X POST http://localhost:8765/debug \
  -H "Content-Type: application/json" \
  -d '{
    "input": "我喜欢什么颜色？",
    "user_id": "user_001"
  }'

# 远程 - 调试模式
curl -X POST https://<your-app>.up.railway.app/debug \
  -H "Content-Type: application/json" \
  -d '{
    "input": "我喜欢什么颜色？",
    "user_id": "user_001"
  }'

# 本地 - 获取知识图谱
curl http://localhost:8765/graph/user_001

# 远程 - 获取知识图谱
curl https://<your-app>.up.railway.app/graph/user_001

# 本地 - 获取会话状态
curl http://localhost:8765/session-status/user_001

# 远程 - 获取会话状态
curl https://<your-app>.up.railway.app/session-status/user_001

# 本地 - 健康检查
curl http://localhost:8765/health

# 远程 - 健康检查
curl https://<your-app>.up.railway.app/health
```

**PowerShell 7：**
```powershell
# 本地 - 处理记忆（生产模式）
$body = @{
    input = "我最喜欢的颜色是蓝色"
    user_id = "user_001"
} | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:8765/process" -Method Post -ContentType "application/json" -Body $body

# 远程 - 处理记忆
$body = @{
    input = "我最喜欢的颜色是蓝色"
    user_id = "user_001"
} | ConvertTo-Json
Invoke-RestMethod -Uri "https://<your-app>.up.railway.app/process" -Method Post -ContentType "application/json" -Body $body

# ⚠️ 重要：结束会话（触发记忆持久化，否则需等30分钟超时）
# 本地
$body = @{ user_id = "user_001" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:8765/end-session" -Method Post -ContentType "application/json" -Body $body
# 远程
$body = @{ user_id = "user_001" } | ConvertTo-Json
Invoke-RestMethod -Uri "https://<your-app>.up.railway.app/end-session" -Method Post -ContentType "application/json" -Body $body

# 本地 - 调试模式
$body = @{
    input = "我喜欢什么颜色？"
    user_id = "user_001"
} | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:8765/debug" -Method Post -ContentType "application/json" -Body $body

# 远程 - 调试模式
$body = @{
    input = "我喜欢什么颜色？"
    user_id = "user_001"
} | ConvertTo-Json
Invoke-RestMethod -Uri "https://<your-app>.up.railway.app/debug" -Method Post -ContentType "application/json" -Body $body

# 本地 - 获取知识图谱
Invoke-RestMethod -Uri "http://localhost:8765/graph/user_001" -Method Get

# 远程 - 获取知识图谱
Invoke-RestMethod -Uri "https://<your-app>.up.railway.app/graph/user_001" -Method Get

# 本地 - 获取会话状态
Invoke-RestMethod -Uri "http://localhost:8765/session-status/user_001" -Method Get

# 远程 - 获取会话状态
Invoke-RestMethod -Uri "https://<your-app>.up.railway.app/session-status/user_001" -Method Get

# 本地 - 健康检查
Invoke-RestMethod -Uri "http://localhost:8765/health" -Method Get

# 远程 - 健康检查
Invoke-RestMethod -Uri "https://<your-app>.up.railway.app/health" -Method Get
```

### Python (requests) - 完整工作流示例

```python
import requests

# 本地: http://localhost:8765
# 远程: https://<your-app>.up.railway.app
BASE_URL = "http://localhost:8765"

def process_memory(input_text: str, user_id: str) -> dict:
    response = requests.post(
        f"{BASE_URL}/process",
        json={"input": input_text, "user_id": user_id}
    )
    return response.json()

def end_session(user_id: str) -> dict:
    """结束会话，触发记忆持久化（必须调用）"""
    response = requests.post(
        f"{BASE_URL}/end-session",
        json={"user_id": user_id}
    )
    return response.json()

# 使用示例 - 完整流程
user_id = "user_001"

# 1. 存储记忆
result = process_memory("我女儿灿灿今年5岁了", user_id)
print(f"处理结果: {result['status']}")

# 2. ⚠️ 重要：结束会话触发记忆持久化
session_result = end_session(user_id)
print(f"会话结束: {session_result['message']}")

# 3. 查询记忆（现在可以查询到结果）
result = process_memory("我女儿叫什么名字？", user_id)

if result["metadata"]["has_memory"]:
    print("找到相关记忆:")
    for m in result["memories"]:
        print(f"  - {m['content']} (score: {m['score']})")
    for rel in result["relations"]:
        print(f"  - {rel['source']} --[{rel['relation']}]--> {rel['target']}")
else:
    print("没有找到相关记忆")
```

### Python (httpx async) - 完整工作流示例

```python
import httpx
import asyncio

# 本地: http://localhost:8765
# 远程: https://<your-app>.up.railway.app
BASE_URL = "http://localhost:8765"

async def process_memory_async(input_text: str, user_id: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/process",
            json={"input": input_text, "user_id": user_id}
        )
        return response.json()

async def end_session_async(user_id: str) -> dict:
    """结束会话，触发记忆持久化（必须调用）"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/end-session",
            json={"user_id": user_id}
        )
        return response.json()

# 使用示例 - 完整流程
async def main():
    user_id = "user_001"

    # 1. 存储记忆
    result = await process_memory_async("小朱的儿子叫帅帅", user_id)
    print(f"处理结果: {result['status']}")

    # 2. ⚠️ 重要：结束会话触发记忆持久化
    session_result = await end_session_async(user_id)
    print(f"会话结束: {session_result['message']}")

    # 3. 查询记忆（现在可以查询到结果）
    result = await process_memory_async("小朱的儿子叫什么？", user_id)
    print(f"查询结果: {result}")

asyncio.run(main())
```

### JavaScript (fetch) - 完整工作流示例

```javascript
// 本地: http://localhost:8765
// 远程: https://<your-app>.up.railway.app
const BASE_URL = "http://localhost:8765";

async function processMemory(input, userId) {
    const response = await fetch(`${BASE_URL}/process`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            input: input,
            user_id: userId
        })
    });
    return response.json();
}

async function endSession(userId) {
    // ⚠️ 重要：结束会话触发记忆持久化（必须调用）
    const response = await fetch(`${BASE_URL}/end-session`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            user_id: userId
        })
    });
    return response.json();
}

// 使用示例 - 完整流程
async function main() {
    const userId = 'user_001';

    // 1. 存储记忆
    const result1 = await processMemory('我儿子今年3岁', userId);
    console.log('处理结果:', result1);

    // 2. ⚠️ 重要：结束会话触发记忆持久化
    const sessionResult = await endSession(userId);
    console.log('会话结束:', sessionResult);

    // 3. 查询记忆（现在可以查询到结果）
    const result2 = await processMemory('我儿子几岁了？', userId);
    console.log('查询结果:', result2);
}

main();
```

---

## DIFY 集成指南

### 在 DIFY 工作流中调用 NeuroMemory

NeuroMemory 可以作为 DIFY 工作流的外部 HTTP 节点使用，为对话注入私有记忆上下文。

### 配置步骤

1. **添加 HTTP 请求节点**
   - 方法：`POST`
   - URL（本地）：`http://localhost:8765/process`
   - URL（远程）：`https://<your-app>.up.railway.app/process`
   - Headers：`Content-Type: application/json`

2. **添加结束会话节点**（⚠️ 必须添加）
   - 方法：`POST`
   - URL（本地）：`http://localhost:8765/end-session`
   - URL（远程）：`https://<your-app>.up.railway.app/end-session`
   - Headers：`Content-Type: application/json`
   - Body：`{"user_id": "{{user_id}}"}`

3. **配置请求体**

```json
{
    "input": "{{user_input}}",
    "user_id": "{{user_id}}"
}
```

4. **处理响应**

在后续的 LLM 节点中，使用返回的记忆上下文：

```
{% if http_result.metadata.has_memory %}
以下是用户的相关记忆，请参考这些信息回答：

记忆：
{% for m in http_result.memories %}
- {{ m.content }}
{% endfor %}

知识图谱：
{% for rel in http_result.relations %}
- {{ rel.source }} 的 {{ rel.relation }} 是 {{ rel.target }}
{% endfor %}
{% endif %}

用户问题：{{ user_input }}
```

### 典型工作流

```
用户输入 → [NeuroMemory] → 记忆上下文 → [LLM] → 回复用户
                ↓
        (异步存储新记忆)

用户结束对话 → [end-session] → 触发记忆持久化
                ↓
        (短期记忆整合为长期记忆)
```

> **重要**：确保在用户对话结束时调用 `/end-session` 接口，否则记忆需等待 30 分钟会话超时后才能持久化。

---

## 交互式文档

**本地**：服务启动后可通过以下地址访问；**Railway 远程**：可直接使用下述在线地址。

| 文档类型 | 本地 | Railway 远程 |
|----------|------|-------------|
| **Swagger UI** | `http://localhost:8765/docs` | https://<your-app>.up.railway.app/docs |
| **ReDoc** | `http://localhost:8765/redoc` | https://<your-app>.up.railway.app/redoc |

这些文档提供了在线测试接口的功能，方便快速验证 API 行为。

---

## 相关文档

- [快速开始](GETTING_STARTED.md) - 环境配置和启动
- [测试指南](TESTING.md) - 测试用例和方法
- [接口总览](API.md) - 查看所有接口类型（REST API、CLI）

---

*文档结束*
