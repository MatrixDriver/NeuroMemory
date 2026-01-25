# 接口设计

> 返回 [主架构文档](ARCHITECTURE.md)

---

## 目录

- [REST API 接口](#rest-api-接口)
- [CLI 接口](#cli-接口)

---

## REST API 接口 `[✅ 已实现]`

NeuroMemory 提供两类 REST API 接口：

- **用户接口（推荐）**：`POST /process` - 统一处理接口，系统内部自动判断是查询还是存储，适用于生产环境和普通用户
- **开发者接口（高级）**：`/api/v1/*` - 细粒度接口，用于特殊场景、测试和开发调试

> **详细文档**：
> - [用户接口文档](USER_API.md) - 面向普通客户的接口文档（`/process`、`/graph` 等）
> - [开发者接口文档](DEVELOPER_API.md) - 面向项目开发者的高级接口文档（`/api/v1/*`）

---

### 用户接口（推荐）

#### `POST /process` - 统一处理接口

**核心接口**，系统内部自动判断是查询还是存储。

- **同步路径**：立即检索相关记忆并返回结构化 JSON（v3 格式）
- **异步路径**：后台进行隐私分类和记忆存储（通过 Session 管理）
- **适用场景**：DIFY 集成、生产环境、普通用户使用

**请求示例**：

**Bash / Git Bash：**
```bash
# 存储记忆（系统会自动判断是否为私有数据）
curl -X POST http://localhost:8765/process \
  -H "Content-Type: application/json" \
  -d '{"input": "我女儿叫灿灿，今年5岁了", "user_id": "user_001"}'

# 查询记忆（同样使用 /process 接口）
curl -X POST http://localhost:8765/process \
  -H "Content-Type: application/json" \
  -d '{"input": "我女儿叫什么名字？", "user_id": "user_001"}'
```

**PowerShell 7：**
```powershell
# 存储记忆
$body = @{
    input = "我女儿叫灿灿，今年5岁了"
    user_id = "user_001"
} | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:8765/process" -Method Post -ContentType "application/json" -Body $body

# 查询记忆（使用 curl.exe）
curl.exe -X POST http://localhost:8765/process `
  -H "Content-Type: application/json" `
  -d '{"input": "我女儿叫什么名字？", "user_id": "user_001"}'
```

**响应格式（v3）**：
```json
{
    "status": "success",
    "resolved_query": "我女儿叫什么名字？",
    "memories": [
        {"content": "灿灿还有一个弟弟，叫帅帅", "score": 0.87}
    ],
    "relations": [
        {"source": "小朱", "relation": "女儿", "target": "灿灿"}
    ],
    "metadata": {
        "retrieval_time_ms": 123,
        "has_memory": true
    }
}
```

**其他用户接口**：
- `GET /graph/{user_id}` - 获取用户知识图谱
- `POST /end-session` - 结束会话（触发记忆整合）
- `GET /session-status/{user_id}` - 获取会话状态
- `GET /health` - 基础健康检查

> **详细文档**：完整的用户接口文档、请求/响应示例、错误处理、DIFY 集成指南等，请参考 [用户接口文档](USER_API.md)。

---

### 开发者接口（高级）

细粒度接口，用于特殊场景、测试和开发调试。**普通用户无需使用这些接口**。

```yaml
# OpenAPI 3.0 风格定义

POST /api/v1/memory  # 已实现
  description: 直接添加记忆（跳过隐私过滤）
  用途: 开发者测试、批量导入、特殊场景需要强制存储
  request:
    body:
      content: string (required)
      user_id: string (default: "default")
      metadata: object
  response:
    memory_id: string

GET /api/v1/memory/search  # 已实现
  description: 混合检索（只检索，不存储）
  用途: 仅需要检索结果的场景
  parameters:
    query: string (required)
    user_id: string
    limit: integer (default: 10)
  response:
    memories: array[MemoryResult]
    relations: array[Relation]
    metadata: object

POST /api/v1/ask  # 已实现
  description: 基于记忆回答问题（检索 + LLM 生成完整回答）
  用途: 需要 LLM 生成回答而非仅返回记忆上下文
  request:
    body:
      question: string (required)
      user_id: string
  response:
    answer: string
    sources: array[MemoryResult]

GET /api/v1/graph  # 已实现
  description: 获取知识图谱（与 /graph/{user_id} 功能相同）
  parameters:
    user_id: string
    depth: integer (default: 2)
  response:
    nodes: array[Node]
    edges: array[Edge]

GET /api/v1/health  # 已实现
  description: 详细健康检查（包含 components 状态）
  response:
    status: "healthy" | "unhealthy"
    components:
      neo4j: boolean
      qdrant: boolean
      llm: boolean
```

> **详细文档**：完整的开发者接口文档、使用场景、注意事项等，请参考 [开发者接口文档](DEVELOPER_API.md)。

---

## CLI 接口 `[✅ 已实现]`

`uv pip install -e .` 或 `pip install -e .` 后使用 `neuromemory` 命令。

```bash
# 命令行示例

neuromemory status                                    # 检查 Neo4j、Qdrant、LLM 状态
neuromemory add "DeepMind 是 Google 的子公司" --user user_001
neuromemory search "Google 有哪些子公司" --user user_001 --limit 5
neuromemory ask "Demis 和 Gemini 有什么关系" --user user_001
neuromemory graph export --user user_001               # JSON 到 stdout
neuromemory graph export --user user_001 -o out.json  # 输出到文件
neuromemory graph visualize --user user_001 --open-browser
```

---

## 相关文档

- [数据模型](DATA_MODEL.md) - 了解数据结构
- [核心组件](COMPONENTS.md) - 了解内部实现
