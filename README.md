# NeuroMemory v2

**Memory-as-a-Service Platform**

为 AI agent 开发者提供记忆管理服务。通过 Python SDK 和 REST API，轻松为您的 AI 应用添加记忆能力。

---

## ⚡ 快速开始

```bash
# 1. 启动服务
docker compose -f docker-compose.v2.yml up -d

# 2. 访问 API 文档
open http://localhost:8765/docs

# 3. 注册租户获取 API Key
curl -X POST http://localhost:8765/v1/tenants/register \
  -H "Content-Type: application/json" \
  -d '{"name": "MyCompany", "email": "admin@example.com"}'

# 4. 使用 Python SDK
pip install -e sdk/
```

```python
from neuromemory_client import NeuroMemoryClient

client = NeuroMemoryClient(api_key="nm_xxx")

# 添加记忆
client.add_memory(
    user_id="alice",
    content="I work at ABC Company as a software engineer",
    memory_type="fact"
)

# 语义检索
results = client.search(
    user_id="alice",
    query="Where does Alice work?",
    limit=5
)

for result in results:
    print(f"[{result['similarity']:.2f}] {result['content']}")
```

**完整指南**: [docs/v2/GETTING_STARTED.md](docs/v2/GETTING_STARTED.md) ⭐

---

## 🎯 核心特性

### 🗄️ 统一存储架构
- **PostgreSQL 16 + pgvector**: 结构化数据 + 向量检索统一存储
- **简化部署**: 从 v1 的 3 个服务（Neo4j + Qdrant + API）简化为 2 个服务
- **ACID 事务**: 保证数据一致性，告别跨库事务难题

### 🔐 多租户隔离
- **API Key 认证**: SHA-256 哈希存储，安全可靠
- **数据隔离**: 按 `tenant_id` 严格隔离，支持 SaaS 模式
- **用户管理**: 每个租户可管理多个用户的记忆

### 🚀 高性能设计
- **异步架构**: FastAPI + SQLAlchemy 2.0 async + asyncpg
- **向量索引**: HNSW 索引，向量检索性能接近专用 VectorDB
- **时序优化**: BRIN 索引，时间范围查询节省 99% 空间

### 🐍 易于集成
- **Python SDK**: 基于 httpx 的同步客户端，简洁易用
- **REST API**: OpenAPI 3.0 规范，自动生成交互式文档
- **类型安全**: Pydantic 模型定义，完整的类型提示

---

## 📚 完整文档

### 核心文档

| 文档 | 说明 |
|------|------|
| **[快速开始](docs/v2/GETTING_STARTED.md)** | 10 分钟上手指南 |
| **[架构设计](docs/v2/ARCHITECTURE.md)** | 系统架构、技术栈、设计原则 |
| **[API 参考](docs/v2/API_REFERENCE.md)** | 完整的 REST API 端点文档 |
| **[SDK 指南](docs/v2/SDK_GUIDE.md)** | Python SDK 详细用法 |
| **[CLAUDE.md](CLAUDE.md)** | Claude Code 工作指南 |

### 在线文档

- **Swagger UI**: http://localhost:8765/docs
- **ReDoc**: http://localhost:8765/redoc
- **文档中心**: [docs/v2/README.md](docs/v2/README.md)

---

## 🏗️ 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                    NeuroMemory v2 架构                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         客户端层 (Client Layer)                       │  │
│  │  • Python SDK (httpx)                                │  │
│  │  • REST API (HTTP/JSON)                              │  │
│  │  • CLI Tool (Typer)                                  │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐  │
│  │         API 服务层 (FastAPI)                          │  │
│  │  • API Key 认证中间件                                 │  │
│  │  • /v1/tenants - 租户管理                            │  │
│  │  • /v1/preferences - 偏好 CRUD                       │  │
│  │  • /v1/memories - 记忆添加                           │  │
│  │  • /v1/search - 语义检索                             │  │
│  │  • /v1/memories/time-range - 时间查询                │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐  │
│  │         服务层 (Service Layer)                        │  │
│  │  • AuthService - 认证和租户隔离                       │  │
│  │  • MemoryService - 时间查询和 CRUD                    │  │
│  │  • SearchService - 向量检索和 embedding              │  │
│  │  • PreferencesService - 偏好管理                     │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐  │
│  │         ORM 层 (SQLAlchemy 2.0 Async)                │  │
│  │  • Tenant, ApiKey, Preference, Embedding             │  │
│  │  • TimestampMixin (created_at, updated_at)           │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐  │
│  │    存储层 (PostgreSQL 16 + pgvector)                  │  │
│  │  • 结构化数据 (租户、偏好、元数据)                     │  │
│  │  • 向量数据 (1024 维 embedding, cosine 距离)         │  │
│  │  • HNSW 向量索引 + BRIN 时序索引                      │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐  │
│  │    外部服务 (SiliconFlow Embedding API)               │  │
│  │  • 模型: BAAI/bge-m3                                  │  │
│  │  • 维度: 1024                                         │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 🛠️ 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| **API 框架** | FastAPI | 高性能异步 Web 框架 |
| **数据库** | PostgreSQL 16 | 统一存储后端 |
| **向量扩展** | pgvector | PostgreSQL 向量插件 |
| **ORM** | SQLAlchemy 2.0 | 异步 ORM，asyncpg 驱动 |
| **Schema** | Pydantic | 请求/响应模型定义 |
| **SDK** | httpx | Python 同步 HTTP 客户端 |
| **Embedding** | SiliconFlow | BAAI/bge-m3 (1024 维) |
| **容器化** | Docker | 服务打包和部署 |

---

## 📦 安装

### 环境要求

- **Python**: 3.10+
- **Docker**: 20.0+
- **内存**: 至少 4GB RAM

### Docker Compose（推荐）

```bash
# 克隆项目
git clone https://github.com/your-repo/NeuroMemory.git
cd NeuroMemory

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，添加 SILICONFLOW_API_KEY

# 启动服务
docker compose -f docker-compose.v2.yml up -d

# 查看日志
docker compose -f docker-compose.v2.yml logs -f api

# 健康检查
curl http://localhost:8765/v1/health
```

### 本地开发

```bash
# 1. 启动数据库
docker compose -f docker-compose.v2.yml up -d db

# 2. 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# 3. 安装依赖
pip install -r requirements.txt
pip install -e sdk/

# 4. 初始化数据库
python -m server.app.db.init_db

# 5. 启动 API 服务
uvicorn server.app.main:app --reload --host 0.0.0.0 --port 8765
```

详见 [快速开始指南](docs/v2/GETTING_STARTED.md)

---

## 🎯 使用示例

### 偏好管理

```python
# 设置用户偏好
client.preferences.set(
    user_id="alice",
    key="language",
    value="zh-CN"
)

# 获取偏好
pref = client.preferences.get(user_id="alice", key="language")
print(pref["value"])  # "zh-CN"
```

### 记忆管理

```python
# 添加事实性记忆
client.add_memory(
    user_id="alice",
    content="I work at ABC Company as a software engineer",
    memory_type="fact"
)

# 添加事件记忆
client.add_memory(
    user_id="alice",
    content="Attended team meeting on project planning",
    memory_type="episodic",
    metadata={"date": "2026-02-10", "participants": ["bob", "charlie"]}
)
```

### 语义检索

```python
# 基础检索
results = client.search(
    user_id="alice",
    query="Where does Alice work?",
    limit=5
)

# 带时间过滤
from datetime import datetime, timezone

results = client.search(
    user_id="alice",
    query="meetings",
    memory_type="episodic",
    created_after=datetime(2026, 1, 1, tzinfo=timezone.utc),
    limit=10
)
```

### 时间查询

```python
from datetime import datetime, date, timezone

# 时间范围查询
result = client.memory.get_by_time_range(
    user_id="alice",
    start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
    end_time=datetime(2026, 1, 31, 23, 59, 59, tzinfo=timezone.utc),
    limit=50
)

# 最近记忆
memories = client.get_recent_memories(
    user_id="alice",
    days=7,
    limit=50
)

# 时间线统计
timeline = client.get_memory_timeline(
    user_id="alice",
    start_date=date(2026, 1, 1),
    end_date=date(2026, 1, 31),
    granularity="day"  # day, week, month
)
```

更多示例见 [SDK 指南](docs/v2/SDK_GUIDE.md)

---

## 🆚 v1 vs v2 对比

| 特性 | v1 (已弃用) | v2 (当前版本) |
|------|-------------|---------------|
| **向量存储** | Qdrant | PostgreSQL + pgvector |
| **图存储** | Neo4j | 移除（未来考虑 AGE 扩展） |
| **认证** | 无 | API Key 多租户认证 |
| **部署复杂度** | 3 个服务 | 2 个服务（简化 33%） |
| **LLM 集成** | Mem0 内置 | 客户端自行集成 |
| **事务支持** | 跨库困难 | 原生 ACID 事务 |
| **运维成本** | 高（3 套监控） | 低（单一数据库） |
| **学习曲线** | 陡峭（Cypher + Qdrant） | 平缓（标准 SQL） |

### 迁移建议

**如果你依赖 v1 的知识图谱功能**:
- 保留 v1 部署，或等待 v2 的 AGE 图数据库支持（Phase 2 计划中）

**如果你只使用向量检索**:
- 可以迁移到 v2，性能更好，部署更简单

详见 [架构文档 - v1 迁移说明](docs/v2/ARCHITECTURE.md#8-v1-迁移说明)

---

## 📖 v1 文档（已弃用）

v1 相关文档已移至 `docs/v1/` 目录，仅作为历史参考：

- [v1 架构文档](docs/v1/ARCHITECTURE.md)
- [v1 API 文档](docs/v1/API.md)
- [v1 工作原理](docs/v1/HOW_IT_WORKS.md)

⚠️ **v1 已停止维护，新项目请使用 v2**。

---

## 🗺️ 路线图

### ✅ Phase 1 (已完成)

- [x] PostgreSQL + pgvector 统一存储
- [x] FastAPI REST API
- [x] Python SDK
- [x] API Key 多租户认证
- [x] 偏好 CRUD
- [x] 向量语义检索
- [x] 时间范围查询
- [x] 时间线聚合

### 🚧 Phase 2 (计划中)

- [ ] OBS 文档存储（华为云 OBS）
- [ ] KV 存储（PostgreSQL jsonb）
- [ ] 图数据库支持（Apache AGE）
- [ ] LLM 记忆分类器
- [ ] 配额管理和计费

### 📋 Phase 3 (规划中)

- [ ] 用户 Console（Web UI）
- [ ] 运维后台
- [ ] 华为云部署
- [ ] 监控和告警（Prometheus + Grafana）

---

## 🤝 贡献

欢迎贡献代码、文档或提出建议！

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交改动 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 提交 Pull Request

---

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

---

## 🔗 相关链接

- **GitHub**: https://github.com/your-repo/NeuroMemory
- **Issues**: https://github.com/your-repo/NeuroMemory/issues
- **文档中心**: [docs/v2/README.md](docs/v2/README.md)

---

## 📧 联系方式

- 提交 Issue: https://github.com/your-repo/NeuroMemory/issues
- 邮箱: your-email@example.com

---

**NeuroMemory v2** - 让您的 AI 拥有记忆 🧠
