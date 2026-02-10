# 接口设计

> 返回 [主架构文档](ARCHITECTURE.md)

---

## 目录

- [REST API 接口](#rest-api-接口)
- [CLI 接口](#cli-接口)

---

## REST API 接口 `[✅ 已实现]`

NeuroMemory 提供统一的 REST API 接口，共 9 个端点：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 存活探测 |
| `/process` | POST | 核心接口：处理记忆（生产模式） |
| `/debug` | POST | 调试模式 |
| `/graph/{user_id}` | GET | 获取知识图谱 |
| `/end-session` | POST | 结束会话 |
| `/session-status/{user_id}` | GET | 获取会话状态 |
| `/health` | GET | 健康检查 |
| `/search` | GET | 纯检索（不写 Session） |
| `/ask` | POST | 基于记忆问答 |

> **详细文档**：[用户接口文档](USER_API.md) - 完整的接口文档、请求/响应示例、错误处理、DIFY 集成指南等

---

### 核心接口

#### `POST /process` - 统一处理接口

**核心接口**，系统内部自动判断是查询还是存储。

- **同步路径**：立即检索相关记忆并返回结构化 JSON
- **异步路径**：后台进行隐私分类和记忆存储（通过 Session 管理）
- **适用场景**：DIFY 集成、生产环境、普通用户使用

**请求示例**：

**Bash / Git Bash：**
```bash
# 步骤1: 本地 - 存储记忆
curl -X POST http://localhost:8765/process \
  -H "Content-Type: application/json" \
  -d '{"input": "我女儿叫灿灿，今年5岁了", "user_id": "user_001"}'

# 步骤1: 远程 - 存储记忆
curl -X POST https://<your-app>.up.railway.app/process \
  -H "Content-Type: application/json" \
  -d '{"input": "我女儿叫灿灿，今年5岁了", "user_id": "user_001"}'

# 步骤2: 本地 - 结束会话（⚠️ 必须调用触发存储，否则需等30分钟超时）
curl -X POST http://localhost:8765/end-session \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user_001"}'

# 步骤2: 远程 - 结束会话
curl -X POST https://<your-app>.up.railway.app/end-session \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user_001"}'

# 步骤3: 本地查询（现在可以查询到结果）
curl -X POST http://localhost:8765/process \
  -H "Content-Type: application/json" \
  -d '{"input": "我女儿叫什么名字？", "user_id": "user_001"}'

# 步骤3: 远程查询
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

# 步骤2: 本地 - 结束会话（⚠️ 必须调用触发存储，否则需等30分钟超时）
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

> **重要提示**：调用 `/process` 后，记忆存储是异步的。必须显式调用 `/end-session` 才能触发系统将短期记忆整合为长期记忆，否则需等待 30 分钟会话超时后才能查询到结果。

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

---

### 辅助接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `POST /end-session` | POST | **结束会话（触发记忆存储）** ⚠️ 重要：调用 `/process` 后需显式调用此接口才能将记忆持久化 |
| `GET /graph/{user_id}` | GET | 获取用户知识图谱 |
| `GET /session-status/{user_id}` | GET | 获取会话状态 |
| `GET /health` | GET | 健康检查（含 components） |
| `GET /search` | GET | 纯检索（不写 Session，只读查询） |
| `POST /ask` | POST | 基于记忆问答（检索 + LLM 生成回答） |

> **详细文档**：完整的接口文档、请求/响应示例、错误处理、DIFY 集成指南等，请参考 [用户接口文档](USER_API.md)。

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
