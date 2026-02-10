# NeuroMemory v2 API 参考文档

> **版本**: v2.0
> **最后更新**: 2026-02-10
> **API 地址**: http://localhost:8765 (开发环境)

---

## 目录

1. [认证](#1-认证)
2. [租户管理](#2-租户管理)
3. [偏好管理](#3-偏好管理)
4. [记忆管理](#4-记忆管理)
5. [语义检索](#5-语义检索)
6. [时间查询](#6-时间查询)
7. [用户概览](#7-用户概览)
8. [健康检查](#8-健康检查)
9. [错误响应](#9-错误响应)

---

## 1. 认证

所有需要认证的端点使用 **Bearer Token** 认证方式。

### 请求头格式

```http
Authorization: Bearer nm_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 获取 API Key

通过 [租户注册](#21-注册租户) 接口获取 API Key。

---

## 2. 租户管理

### 2.1 注册租户

创建新租户并获取 API Key。

**端点**: `POST /v1/tenants/register`

**认证**: 无需认证

**请求体**:
```json
{
  "name": "MyCompany",
  "email": "admin@example.com"
}
```

**参数说明**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 是 | 租户名称 |
| email | string | 是 | 租户邮箱（唯一） |

**成功响应** (200):
```json
{
  "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
  "api_key": "nm_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "message": "Registration successful. Please save your API key securely."
}
```

**错误响应** (409):
```json
{
  "detail": "Email already registered"
}
```

**示例**:
```bash
curl -X POST http://localhost:8765/v1/tenants/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "MyCompany",
    "email": "admin@example.com"
  }'
```

---

## 3. 偏好管理

### 3.1 设置偏好

设置或更新用户偏好（Upsert 操作）。

**端点**: `POST /v1/preferences`

**认证**: 需要

**请求体**:
```json
{
  "user_id": "alice",
  "key": "language",
  "value": "zh-CN"
}
```

**参数说明**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| user_id | string | 是 | 用户 ID |
| key | string | 是 | 偏好键名 |
| value | any | 是 | 偏好值（支持字符串、数字、对象） |

**成功响应** (200):
```json
{
  "id": "uuid",
  "user_id": "alice",
  "key": "language",
  "value": "zh-CN",
  "created_at": "2026-02-10T08:00:00Z",
  "updated_at": "2026-02-10T08:00:00Z"
}
```

**示例**:
```bash
curl -X POST http://localhost:8765/v1/preferences \
  -H "Authorization: Bearer nm_xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "alice",
    "key": "theme",
    "value": {"mode": "dark", "color": "blue"}
  }'
```

### 3.2 获取单个偏好

**端点**: `GET /v1/preferences/{key}`

**认证**: 需要

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| user_id | string | 是 | 用户 ID |

**成功响应** (200):
```json
{
  "id": "uuid",
  "user_id": "alice",
  "key": "language",
  "value": "zh-CN",
  "created_at": "2026-02-10T08:00:00Z",
  "updated_at": "2026-02-10T08:00:00Z"
}
```

**错误响应** (404):
```json
{
  "detail": "Preference not found"
}
```

**示例**:
```bash
curl http://localhost:8765/v1/preferences/language?user_id=alice \
  -H "Authorization: Bearer nm_xxx"
```

### 3.3 列出所有偏好

**端点**: `GET /v1/preferences`

**认证**: 需要

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| user_id | string | 是 | 用户 ID |

**成功响应** (200):
```json
[
  {
    "id": "uuid",
    "user_id": "alice",
    "key": "language",
    "value": "zh-CN",
    "created_at": "2026-02-10T08:00:00Z",
    "updated_at": "2026-02-10T08:00:00Z"
  },
  {
    "id": "uuid",
    "user_id": "alice",
    "key": "theme",
    "value": {"mode": "dark"},
    "created_at": "2026-02-10T08:00:00Z",
    "updated_at": "2026-02-10T08:00:00Z"
  }
]
```

**示例**:
```bash
curl http://localhost:8765/v1/preferences?user_id=alice \
  -H "Authorization: Bearer nm_xxx"
```

### 3.4 删除偏好

**端点**: `DELETE /v1/preferences/{key}`

**认证**: 需要

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| user_id | string | 是 | 用户 ID |

**成功响应** (200):
```json
{
  "message": "Preference deleted successfully"
}
```

**示例**:
```bash
curl -X DELETE http://localhost:8765/v1/preferences/language?user_id=alice \
  -H "Authorization: Bearer nm_xxx"
```

---

## 4. 记忆管理

### 4.1 添加记忆

添加新的记忆并自动生成 embedding。

**端点**: `POST /v1/memories`

**认证**: 需要

**请求体**:
```json
{
  "user_id": "alice",
  "content": "I work at ABC Company as a software engineer",
  "memory_type": "fact",
  "metadata": {
    "source": "conversation",
    "confidence": 0.95
  }
}
```

**参数说明**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| user_id | string | 是 | 用户 ID |
| content | string | 是 | 记忆内容 |
| memory_type | string | 否 | 记忆类型（默认: "general"） |
| metadata | object | 否 | 附加元数据 |

**成功响应** (200):
```json
{
  "id": "uuid",
  "user_id": "alice",
  "content": "I work at ABC Company as a software engineer",
  "memory_type": "fact",
  "metadata": {
    "source": "conversation",
    "confidence": 0.95
  },
  "created_at": "2026-02-10T08:00:00Z"
}
```

**示例**:
```bash
curl -X POST http://localhost:8765/v1/memories \
  -H "Authorization: Bearer nm_xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "alice",
    "content": "My favorite color is blue",
    "memory_type": "preference"
  }'
```

---

## 5. 语义检索

### 5.1 搜索记忆

基于语义相似度搜索记忆。

**端点**: `POST /v1/search`

**认证**: 需要

**请求体**:
```json
{
  "user_id": "alice",
  "query": "Where does Alice work?",
  "limit": 5,
  "memory_type": "fact",
  "created_after": "2026-01-01T00:00:00Z",
  "created_before": "2026-02-10T23:59:59Z"
}
```

**参数说明**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| user_id | string | 是 | 用户 ID |
| query | string | 是 | 查询文本 |
| limit | integer | 否 | 返回结果数（默认: 5，最大: 100） |
| memory_type | string | 否 | 过滤记忆类型 |
| created_after | datetime | 否 | 过滤创建时间（开始） |
| created_before | datetime | 否 | 过滤创建时间（结束） |

**成功响应** (200):
```json
{
  "results": [
    {
      "id": "uuid",
      "user_id": "alice",
      "content": "I work at ABC Company as a software engineer",
      "memory_type": "fact",
      "metadata": {"source": "conversation"},
      "created_at": "2026-02-10T08:00:00Z",
      "similarity": 0.89
    },
    {
      "id": "uuid",
      "user_id": "alice",
      "content": "ABC Company is a tech startup",
      "memory_type": "fact",
      "created_at": "2026-02-09T10:00:00Z",
      "similarity": 0.72
    }
  ]
}
```

**示例**:
```bash
curl -X POST http://localhost:8765/v1/search \
  -H "Authorization: Bearer nm_xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "alice",
    "query": "workplace",
    "limit": 3
  }'
```

---

## 6. 时间查询

### 6.1 时间范围查询

查询指定时间范围内的记忆。

**端点**: `POST /v1/memories/time-range`

**认证**: 需要

**请求体**:
```json
{
  "user_id": "alice",
  "start_time": "2026-01-01T00:00:00Z",
  "end_time": "2026-01-31T23:59:59Z",
  "memory_type": "fact",
  "limit": 50,
  "offset": 0
}
```

**参数说明**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| user_id | string | 是 | 用户 ID |
| start_time | datetime | 是 | 开始时间（ISO 8601 格式，含时区） |
| end_time | datetime | 否 | 结束时间（默认: 当前时间） |
| memory_type | string | 否 | 过滤记忆类型 |
| limit | integer | 否 | 每页数量（1-500，默认: 100） |
| offset | integer | 否 | 偏移量（默认: 0） |

**成功响应** (200):
```json
{
  "user_id": "alice",
  "total": 123,
  "limit": 50,
  "offset": 0,
  "time_range": {
    "start": "2026-01-01T00:00:00Z",
    "end": "2026-01-31T23:59:59Z"
  },
  "memories": [
    {
      "id": "uuid",
      "user_id": "alice",
      "content": "...",
      "memory_type": "fact",
      "metadata": {},
      "created_at": "2026-01-15T10:30:00Z"
    }
  ]
}
```

**示例**:
```bash
curl -X POST http://localhost:8765/v1/memories/time-range \
  -H "Authorization: Bearer nm_xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "alice",
    "start_time": "2026-01-01T00:00:00+00:00",
    "end_time": "2026-01-31T23:59:59+00:00",
    "limit": 20
  }'
```

### 6.2 最近记忆查询

查询最近 N 天的记忆。

**端点**: `POST /v1/memories/recent`

**认证**: 需要

**请求体**:
```json
{
  "user_id": "alice",
  "days": 7,
  "memory_types": ["fact", "episodic"],
  "limit": 50
}
```

**参数说明**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| user_id | string | 是 | 用户 ID |
| days | integer | 否 | 天数（1-90，默认: 7） |
| memory_types | array | 否 | 过滤记忆类型列表 |
| limit | integer | 否 | 返回数量（1-500，默认: 50） |

**成功响应** (200):
```json
[
  {
    "id": "uuid",
    "user_id": "alice",
    "content": "...",
    "memory_type": "fact",
    "metadata": {},
    "created_at": "2026-02-09T15:00:00Z"
  }
]
```

**示例**:
```bash
curl -X POST http://localhost:8765/v1/memories/recent \
  -H "Authorization: Bearer nm_xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "alice",
    "days": 30,
    "limit": 100
  }'
```

### 6.3 时间线聚合

按日/周/月聚合记忆统计。

**端点**: `POST /v1/memories/timeline`

**认证**: 需要

**请求体**:
```json
{
  "user_id": "alice",
  "start_date": "2026-01-01",
  "end_date": "2026-01-31",
  "granularity": "day",
  "memory_type": null
}
```

**参数说明**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| user_id | string | 是 | 用户 ID |
| start_date | date | 是 | 开始日期（YYYY-MM-DD） |
| end_date | date | 否 | 结束日期（默认: 今天） |
| granularity | string | 否 | 粒度（day/week/month，默认: day） |
| memory_type | string | 否 | 过滤记忆类型 |

**成功响应** (200):
```json
{
  "user_id": "alice",
  "start_date": "2026-01-01",
  "end_date": "2026-01-31",
  "granularity": "day",
  "total_memories": 245,
  "data": [
    {
      "date": "2026-01-01",
      "count": 5,
      "memory_types": {
        "fact": 3,
        "episodic": 2
      }
    },
    {
      "date": "2026-01-02",
      "count": 8,
      "memory_types": {
        "fact": 5,
        "preference": 3
      }
    }
  ]
}
```

**示例**:
```bash
curl -X POST http://localhost:8765/v1/memories/timeline \
  -H "Authorization: Bearer nm_xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "alice",
    "start_date": "2026-01-01",
    "end_date": "2026-01-31",
    "granularity": "week"
  }'
```

---

## 7. 用户概览

### 7.1 获取用户记忆概览

**端点**: `GET /v1/users/{user_id}/memories`

**认证**: 需要

**路径参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| user_id | string | 用户 ID |

**成功响应** (200):
```json
{
  "user_id": "alice",
  "total_memories": 123,
  "memory_types": {
    "fact": 45,
    "episodic": 32,
    "preference": 28,
    "general": 18
  },
  "earliest_memory": "2025-12-01T08:00:00Z",
  "latest_memory": "2026-02-10T15:30:00Z"
}
```

**示例**:
```bash
curl http://localhost:8765/v1/users/alice/memories \
  -H "Authorization: Bearer nm_xxx"
```

---

## 8. 健康检查

### 8.1 存活探测

**端点**: `GET /`

**认证**: 无需认证

**成功响应** (200):
```json
{
  "status": "ok",
  "message": "NeuroMemory API v2"
}
```

### 8.2 健康检查

**端点**: `GET /v1/health`

**认证**: 无需认证

**成功响应** (200):
```json
{
  "status": "healthy",
  "database": "connected",
  "embedding_service": "available",
  "version": "2.0.0"
}
```

**错误响应** (503):
```json
{
  "status": "unhealthy",
  "database": "disconnected",
  "embedding_service": "unavailable"
}
```

---

## 9. 错误响应

### 9.1 通用错误格式

所有错误响应遵循统一格式：

```json
{
  "detail": "Error message description"
}
```

### 9.2 HTTP 状态码

| 状态码 | 说明 | 场景 |
|--------|------|------|
| 200 | 成功 | 请求成功处理 |
| 400 | 请求错误 | 参数验证失败、时间范围无效 |
| 401 | 未认证 | 缺少或无效的 API Key |
| 404 | 未找到 | 资源不存在 |
| 409 | 冲突 | 邮箱已注册、资源已存在 |
| 500 | 服务器错误 | 内部错误、数据库连接失败 |
| 503 | 服务不可用 | 依赖服务（embedding）不可用 |

### 9.3 错误示例

**认证失败** (401):
```json
{
  "detail": "Invalid or missing API key"
}
```

**参数验证失败** (400):
```json
{
  "detail": "start_time must be before end_time"
}
```

**记忆未找到** (404):
```json
{
  "detail": "Memory not found"
}
```

**Embedding 服务不可用** (503):
```json
{
  "detail": "Embedding service unavailable. Please try again later."
}
```

---

## 附录

### A. 时间格式

所有时间参数使用 **ISO 8601 格式**，必须包含时区信息：

```
2026-02-10T08:00:00Z           # UTC 时区
2026-02-10T16:00:00+08:00      # 北京时区
```

服务端内部统一转换为 UTC 时区存储。

### B. 分页

支持分页的端点使用 `limit` 和 `offset` 参数：

```json
{
  "limit": 50,    // 每页数量
  "offset": 100   // 跳过前 N 条记录
}
```

计算页码：`page = offset / limit + 1`

### C. 速率限制

**当前版本暂无速率限制**。未来版本可能引入：
- 免费版: 1000 请求/小时
- 付费版: 10000 请求/小时

### D. OpenAPI 文档

访问 **Swagger UI** 查看交互式 API 文档：

- 开发环境: http://localhost:8765/docs
- 生产环境: https://api.yourdomain.com/docs

---

**维护**: 本文档与 API 代码同步更新。如有问题，请提交 Issue。
