# NeuroMemory REST API v1 Documentation

Complete reference for NeuroMemory REST API endpoints.

**Base URL:** `http://localhost:8765` (development) or your deployed URL

**API Version:** v1

**Authentication:** Bearer Token (API Key)

---

## Table of Contents

- [Authentication](#authentication)
- [Health & Status](#health--status)
- [Tenant Management](#tenant-management)
- [Preferences](#preferences)
- [Memory & Search](#memory--search)
- [User Overview](#user-overview)
- [Error Responses](#error-responses)

---

## Authentication

All API endpoints (except health checks and tenant registration) require authentication using an API key.

### API Key Format

```
nm_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### Authentication Header

```http
Authorization: Bearer nm_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### Getting an API Key

Register a new tenant to obtain an API key:

```bash
curl -X POST http://localhost:8765/v1/tenants/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Company",
    "email": "admin@example.com"
  }'
```

**Response:**
```json
{
  "tenant_id": "123e4567-e89b-12d3-a456-426614174000",
  "api_key": "nm_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "message": "Save your API key - it won't be shown again."
}
```

⚠️ **Important:** Store the API key securely. It cannot be retrieved later.

---

## Health & Status

### GET `/`

Root endpoint - simple alive check.

**Authentication:** None

**Response:**
```json
{
  "message": "NeuroMemory API v1",
  "status": "ok"
}
```

**Status Codes:**
- `200 OK`: Service is running

---

### GET `/v1/health`

Health check with database status.

**Authentication:** None

**Response:**
```json
{
  "status": "healthy",
  "database": "connected",
  "version": "2.0.0"
}
```

**Status Codes:**
- `200 OK`: All services healthy
- `503 Service Unavailable`: Database or services unavailable

---

## Tenant Management

### POST `/v1/tenants/register`

Register a new tenant and receive an API key.

**Authentication:** None

**Request Body:**
```json
{
  "name": "Company Name",
  "email": "admin@example.com"
}
```

**Parameters:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| name | string | Yes | Tenant/company name |
| email | string | Yes | Admin email (must be unique) |

**Response:** `200 OK`
```json
{
  "tenant_id": "123e4567-e89b-12d3-a456-426614174000",
  "api_key": "nm_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "message": "Save your API key - it won't be shown again."
}
```

**Error Responses:**
- `409 Conflict`: Email already registered
- `422 Unprocessable Entity`: Invalid request body

**Example:**
```bash
curl -X POST http://localhost:8765/v1/tenants/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Acme Corp",
    "email": "admin@acme.com"
  }'
```

---

## Preferences

Preferences are simple key-value pairs for storing user settings and metadata.

### POST `/v1/preferences`

Set or update a preference (upsert operation).

**Authentication:** Required

**Request Body:**
```json
{
  "user_id": "user123",
  "key": "language",
  "value": "zh-CN",
  "metadata": {
    "source": "user_settings"
  }
}
```

**Parameters:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| user_id | string | Yes | Unique user identifier |
| key | string | Yes | Preference key |
| value | string | Yes | Preference value |
| metadata | object | No | Additional metadata (JSON) |

**Response:** `200 OK`
```json
{
  "id": "pref-uuid",
  "user_id": "user123",
  "key": "language",
  "value": "zh-CN",
  "metadata": {
    "source": "user_settings"
  },
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

**Example:**
```bash
curl -X POST http://localhost:8765/v1/preferences \
  -H "Authorization: Bearer nm_xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "key": "theme",
    "value": "dark"
  }'
```

---

### GET `/v1/preferences`

List all preferences for a user.

**Authentication:** Required

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| user_id | string | Yes | User identifier |

**Response:** `200 OK`
```json
{
  "user_id": "user123",
  "preferences": [
    {
      "id": "pref-uuid-1",
      "key": "language",
      "value": "zh-CN",
      "metadata": {},
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-15T10:30:00Z"
    },
    {
      "id": "pref-uuid-2",
      "key": "theme",
      "value": "dark",
      "metadata": {},
      "created_at": "2024-01-15T11:00:00Z",
      "updated_at": "2024-01-15T11:00:00Z"
    }
  ]
}
```

**Example:**
```bash
curl -X GET "http://localhost:8765/v1/preferences?user_id=user123" \
  -H "Authorization: Bearer nm_xxx"
```

---

### GET `/v1/preferences/{key}`

Get a specific preference by key.

**Authentication:** Required

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| key | string | Preference key |

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| user_id | string | Yes | User identifier |

**Response:** `200 OK`
```json
{
  "id": "pref-uuid",
  "user_id": "user123",
  "key": "language",
  "value": "zh-CN",
  "metadata": {},
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

**Error Responses:**
- `404 Not Found`: Preference does not exist

**Example:**
```bash
curl -X GET "http://localhost:8765/v1/preferences/language?user_id=user123" \
  -H "Authorization: Bearer nm_xxx"
```

---

### DELETE `/v1/preferences/{key}`

Delete a preference.

**Authentication:** Required

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| key | string | Preference key |

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| user_id | string | Yes | User identifier |

**Response:** `204 No Content`

**Error Responses:**
- `404 Not Found`: Preference does not exist

**Example:**
```bash
curl -X DELETE "http://localhost:8765/v1/preferences/theme?user_id=user123" \
  -H "Authorization: Bearer nm_xxx"
```

---

## Memory & Search

Store and search user memories using semantic embeddings.

### POST `/v1/memories`

Add a memory for semantic search.

**Authentication:** Required

**Request Body:**
```json
{
  "user_id": "user123",
  "content": "I work at ABC Company as a software engineer",
  "metadata": {
    "type": "fact",
    "category": "work"
  }
}
```

**Parameters:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| user_id | string | Yes | User identifier |
| content | string | Yes | Memory content (text) |
| metadata | object | No | Additional metadata (JSON) |

**Response:** `200 OK`
```json
{
  "id": "mem-uuid",
  "user_id": "user123",
  "content": "I work at ABC Company as a software engineer",
  "memory_type": "general",
  "metadata": {
    "type": "fact",
    "category": "work"
  },
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Example:**
```bash
curl -X POST http://localhost:8765/v1/memories \
  -H "Authorization: Bearer nm_xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "content": "My favorite programming language is Python"
  }'
```

**Note:** This endpoint generates embeddings using the configured embedding service (SiliconFlow).

---

### POST `/v1/search`

Search memories using semantic similarity.

**Authentication:** Required

**Request Body:**
```json
{
  "user_id": "user123",
  "query": "where does the user work",
  "limit": 5,
  "min_score": 0.5
}
```

**Parameters:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| user_id | string | Yes | User identifier |
| query | string | Yes | Search query (natural language) |
| limit | integer | No | Max results (default: 10) |
| min_score | float | No | Min similarity score 0.0-1.0 (default: 0.0) |

**Response:** `200 OK`
```json
{
  "query": "where does the user work",
  "results": [
    {
      "id": "mem-uuid",
      "content": "I work at ABC Company as a software engineer",
      "score": 0.89,
      "metadata": {
        "type": "fact",
        "category": "work"
      },
      "created_at": "2024-01-15T10:30:00Z"
    },
    {
      "id": "mem-uuid-2",
      "content": "Started working at ABC Company in 2023",
      "score": 0.72,
      "metadata": {},
      "created_at": "2024-01-15T11:00:00Z"
    }
  ]
}
```

**Example:**
```bash
curl -X POST http://localhost:8765/v1/search \
  -H "Authorization: Bearer nm_xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "query": "what programming languages does user know",
    "limit": 3
  }'
```

**Note:** Results are sorted by similarity score (highest first).

---

## User Overview

### GET `/v1/users/{user_id}/memories`

Get a summary of all memories for a user.

**Authentication:** Required

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| user_id | string | User identifier |

**Response:** `200 OK`
```json
{
  "user_id": "user123",
  "preference_count": 5,
  "embedding_count": 23,
  "recent_preferences": [
    {
      "key": "language",
      "value": "zh-CN",
      "updated_at": "2024-01-15T10:30:00Z"
    }
  ],
  "recent_memories": [
    {
      "content": "Completed Python course",
      "created_at": "2024-01-15T11:00:00Z"
    }
  ]
}
```

**Example:**
```bash
curl -X GET http://localhost:8765/v1/users/user123/memories \
  -H "Authorization: Bearer nm_xxx"
```

---

## Error Responses

All error responses follow this format:

```json
{
  "detail": "Error message description"
}
```

### Common Status Codes

| Code | Meaning | Description |
|------|---------|-------------|
| 200 | OK | Request succeeded |
| 204 | No Content | Delete succeeded (no response body) |
| 400 | Bad Request | Invalid request format |
| 401 | Unauthorized | Missing or invalid API key |
| 403 | Forbidden | Valid authentication but insufficient permissions |
| 404 | Not Found | Resource does not exist |
| 409 | Conflict | Resource already exists (e.g., duplicate email) |
| 422 | Unprocessable Entity | Validation error in request body |
| 500 | Internal Server Error | Server-side error |
| 503 | Service Unavailable | Service temporarily unavailable |

### Example Error Response

**Request:**
```bash
curl -X GET http://localhost:8765/v1/preferences/missing?user_id=user123 \
  -H "Authorization: Bearer nm_xxx"
```

**Response:** `404 Not Found`
```json
{
  "detail": "Preference not found"
}
```

---

## Rate Limiting

Currently, there are no rate limits. Rate limiting will be implemented in Phase 2.

---

## Pagination

For endpoints returning lists, pagination is not yet implemented. All results are returned in a single response. This will be added in Phase 2.

---

## Versioning

The API is versioned through the URL path (`/v1/`). Breaking changes will result in a new version (`/v2/`, etc.).

Current version: **v1**

---

## Interactive API Documentation

When the server is running, you can access interactive API documentation:

- **Swagger UI**: http://localhost:8765/docs
- **ReDoc**: http://localhost:8765/redoc

These provide:
- Interactive API testing
- Complete schema definitions
- Request/response examples
- Authentication testing

---

## SDK Libraries

Instead of calling the REST API directly, you can use official SDK libraries:

- **Python SDK**: See [SDK Documentation](../sdk/README.md)

---

## Examples

### Complete Workflow Example

```bash
# 1. Register and get API key
API_KEY=$(curl -s -X POST http://localhost:8765/v1/tenants/register \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Corp", "email": "test@example.com"}' \
  | jq -r '.api_key')

echo "API Key: $API_KEY"

# 2. Set user preferences
curl -X POST http://localhost:8765/v1/preferences \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "key": "language",
    "value": "zh-CN"
  }'

# 3. Add memories
curl -X POST http://localhost:8765/v1/memories \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "content": "I love hiking in the mountains"
  }'

curl -X POST http://localhost:8765/v1/memories \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "content": "My favorite food is Italian pasta"
  }'

# 4. Search memories
curl -X POST http://localhost:8765/v1/search \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "query": "what outdoor activities does user enjoy",
    "limit": 3
  }'

# 5. Get user overview
curl -X GET http://localhost:8765/v1/users/user123/memories \
  -H "Authorization: Bearer $API_KEY"

# 6. List preferences
curl -X GET "http://localhost:8765/v1/preferences?user_id=user123" \
  -H "Authorization: Bearer $API_KEY"
```

---

## Support

- **Documentation**: [GitHub Wiki](https://github.com/your-repo/wiki)
- **Issues**: [GitHub Issues](https://github.com/your-repo/issues)
- **API Status**: Check `/v1/health` endpoint

---

## Changelog

### v1.0.0 (2024-01-15)

- Initial API release
- Tenant registration
- Preferences CRUD
- Semantic memory search
- API key authentication
