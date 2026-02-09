# 部署架构

> 返回 [主架构文档](ARCHITECTURE.md)

---

## 目录

- [本地开发部署](#本地开发部署)
- [Railway 云部署](#railway-云部署-已上线)
- [生产部署架构](#生产部署架构)

---

## 本地开发部署 `[✅ 当前方式]`

```
┌─────────────────────────────────────────────────────────────────┐
│                     本地开发环境                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Host Machine                                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Python Application (.venv)                             │   │
│  │  • main.py                                              │   │
│  │  • config.py                                            │   │
│  └─────────────────────────────────────────────────────────┘   │
│           │                                                     │
│           ▼                                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Docker Compose                                         │   │
│  │  ┌─────────────────────┐  ┌─────────────────────┐      │   │
│  │  │ memory_graph_db     │  │ memory_vector_db    │      │   │
│  │  │ (Neo4j 5.26.0)      │  │ (Qdrant latest)     │      │   │
│  │  │                     │  │                     │      │   │
│  │  │ :7474 (Browser)     │  │ :6400 (API)         │      │   │
│  │  │ :17687 (Bolt)       │  │                     │      │   │
│  │  │                     │  │                     │      │   │
│  │  │ ./neo4j_data:/data  │  │ ./qdrant_data:      │      │   │
│  │  │                     │  │   /qdrant/storage   │      │   │
│  │  └─────────────────────┘  └─────────────────────┘      │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  外部服务                                                        │
│  ┌─────────────────────┐  ┌─────────────────────┐              │
│  │ DeepSeek API        │  │ Google Gemini API   │              │
│  │ api.deepseek.com    │  │ (备选)              │              │
│  └─────────────────────┘  └─────────────────────┘              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 启动命令

```bash
# 启动数据库服务
docker-compose up -d

# 停止服务
docker-compose down

# 查看服务状态
docker-compose ps
```

### 数据持久化

| 服务 | 本地目录 | 容器目录 |
|------|----------|----------|
| Neo4j | `./neo4j_data` | `/data` |
| Qdrant | `./qdrant_data` | `/qdrant/storage` |

---

## Railway 云部署 `[✅ 已上线]`

项目已在 [Railway](https://railway.app) 上部署，可通过以下地址远程访问。

### 服务与数据库管理界面

| 服务 | 地址 | 说明 |
|------|------|------|
| **REST API 根路径** | https://<your-app>.up.railway.app/ | 主接口 |
| **API 文档 (Swagger UI)** | https://<your-app>.up.railway.app/docs | 在线调试 |
| **健康检查** | https://<your-app>.up.railway.app/health | 存活探测 |
| **Neo4j Browser** | 通过 Railway 内部网络访问 | 图数据库，无外部公开 URL |
| **Qdrant Web UI** | 通过 Railway 内部网络访问 | 向量数据库，无外部公开 URL |

### Neo4j（Railway，当前部署）

| 项目 | 值 |
|------|-----|
| 用户名 | `neo4j` |
| 密码 | 在 Railway 的应用或 Neo4j 服务变量 `Neo4jPassword` 中配置；可集中记录于 `CREDENTIALS.local.md`（已加入 .gitignore，不提交）。*当前部署示例：`railway2025`* |
| Bolt 端口（应用连接） | **7687**（Railway 标准 Neo4j） |
| 内部地址 | 由 Railway 注入，通过内部网络访问 |
| Neo4j Browser (7474) | 通过 Railway 内部网络访问（无外部公开 URL） |

**访问步骤（Neo4j Browser）：** Railway 上 Neo4j 仅通过内部网络访问，不提供外部公开 URL。如需管理，可通过 Railway 控制台或本地端口转发。

### Qdrant Web UI（Railway）

| 项目 | 值 |
|------|-----|
| URL | 通过 Railway 内部网络访问（无外部公开 URL） |
| 认证 | 无（当前未启用） |
| HTTP 端口（服务间） | `6400` |
| gRPC 端口（服务间） | `6334` |

**访问步骤：** Railway 上 Qdrant 仅通过内部网络访问。如需管理，可通过 Railway 控制台或本地端口转发。

部署配置见项目根目录 `railway.toml`，包含主应用、Neo4j 与 Qdrant 的完整编排。各环境账号与密码可集中记录于 `CREDENTIALS.local.md`（已加入 .gitignore，不纳入版本库）。

### Railway 数据库连接与排错

**`[Errno 111] Connection refused`（Neo4j / Qdrant 连不上）**

- **原因**：应用未拿到正确的数据库 host，或 Neo4j/Qdrant 未与 API 服务正确链接。
- **处理**：
  1. 在 Railway 项目中确保 `neuromemory-api` 的 **depends_on / 链接** 包含 `neo4j-neuromemory`、`qdrant-neuromemory`，Railway 会注入 `NEO4J_NEUROMEMORY_HOST`、`QDRANT_NEUROMEMORY_HOST`；`config.py` 会自动使用。
  2. 在 **Networking → Private** 中查看 Neo4j、Qdrant 的 host。若未注入，可在 API 服务的 **Variables** 中手动添加：  
     `NEO4J_URL=neo4j://<Neo4j host>:7687`（Railway 标准 Neo4j 使用 Bolt **7687**），`QDRANT_HOST=<Qdrant host>`，`QDRANT_PORT=6400`。
  3. 确认 `Neo4jPassword` 已设且与 Neo4j 服务的 `NEO4J_AUTH` 一致（如 `railway2025`）。

**`422 Unprocessable Content`（POST /process）**

- **原因**：请求体 JSON 格式错误或字段缺失（例如 PowerShell 下 `curl -d` 引号转义不当）。
- **处理**：用 `Content-Type: application/json` 发送合法 JSON，必须包含 `input`、`user_id`。示例（PowerShell）：  
  `$body = '{"input":"我女儿叫灿灿","user_id":"u1"}; Invoke-RestMethod -Uri "https://<your-app>.up.railway.app/process" -Method POST -Body $body -ContentType "application/json"`

**健康检查**

- `GET /health`：仅表示进程就绪，用于 Railway 存活探测。
- `GET /health`：返回 `components: {neo4j, qdrant, llm}`，用于排查数据库与 LLM 配置。

---

## 生产部署架构 `[📋 规划]`

```
┌─────────────────────────────────────────────────────────────────┐
│                     生产环境部署架构                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Load Balancer                        │   │
│  │                    (Nginx / Traefik)                    │   │
│  └─────────────────────────────┬───────────────────────────┘   │
│                                │                                │
│         ┌──────────────────────┼──────────────────────┐        │
│         ▼                      ▼                      ▼        │
│  ┌─────────────┐        ┌─────────────┐        ┌─────────────┐ │
│  │ API Server  │        │ API Server  │        │ API Server  │ │
│  │ (Replica 1) │        │ (Replica 2) │        │ (Replica N) │ │
│  └──────┬──────┘        └──────┬──────┘        └──────┬──────┘ │
│         │                      │                      │        │
│         └──────────────────────┼──────────────────────┘        │
│                                │                                │
│         ┌──────────────────────┼──────────────────────┐        │
│         ▼                      ▼                      ▼        │
│  ┌─────────────┐        ┌─────────────┐        ┌─────────────┐ │
│  │   Neo4j     │        │   Qdrant    │        │   Redis     │ │
│  │  (Primary)  │        │  (Cluster)  │        │  (Cache)    │ │
│  └─────────────┘        └─────────────┘        └─────────────┘ │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                  可观测性平台                             │   │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐           │   │
│  │  │Prometheus │  │  Jaeger   │  │   Loki    │           │   │
│  │  │ (Metrics) │  │ (Tracing) │  │ (Logging) │           │   │
│  │  └───────────┘  └───────────┘  └───────────┘           │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 生产环境组件

| 组件 | 用途 | 状态 |
|------|------|------|
| Load Balancer | 流量分发、SSL 终止 | 📋 规划 |
| API Server | 无状态应用服务 | 📋 规划 |
| Neo4j Primary | 图谱存储 | 📋 规划 |
| Qdrant Cluster | 向量存储集群 | 📋 规划 |
| Redis | 缓存层 | 📋 规划 |
| 可观测性平台 | 监控告警 | 📋 规划 |

### 扩展考虑

- **水平扩展**: API Server 无状态，可按需增加副本
- **数据库扩展**: Qdrant 支持分片，Neo4j 支持读副本
- **缓存策略**: Redis 缓存热点查询结果

---

## 相关文档

- [快速开始](GETTING_STARTED.md) - 本地环境搭建
- [配置参考](CONFIGURATION.md) - 详细配置选项
- [可观测性设计](OBSERVABILITY.md) - 监控告警设计
