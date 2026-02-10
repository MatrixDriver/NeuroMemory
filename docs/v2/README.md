# NeuroMemory v2 文档中心

> **Memory-as-a-Service Platform**
>
> 为 AI agent 开发者提供记忆管理服务

---

## 📚 文档导航

### 新手入门

- **[快速开始](GETTING_STARTED.md)** ⭐
  - 10 分钟上手指南
  - Docker 部署
  - 第一个 API 调用

### 核心文档

- **[架构设计](ARCHITECTURE.md)**
  - 系统架构图
  - 技术栈选型
  - 多租户设计
  - 性能指标

- **[API 参考](API_REFERENCE.md)**
  - 完整的 REST API 端点
  - 请求/响应格式
  - 错误代码说明
  - curl 示例

- **[SDK 使用指南](SDK_GUIDE.md)**
  - Python SDK 完整用法
  - 代码示例
  - 错误处理
  - 高级特性

### 开发指南

- **[CLAUDE.md](../../CLAUDE.md)** (项目根目录)
  - Claude Code 工作指南
  - 项目约定
  - 开发流程

---

## 🚀 快速链接

### 立即开始

```bash
# 1. 启动服务
docker compose -f docker-compose.v2.yml up -d

# 2. 注册租户
curl -X POST http://localhost:8765/v1/tenants/register \
  -H "Content-Type: application/json" \
  -d '{"name": "MyCompany", "email": "admin@example.com"}'

# 3. 使用 API Key
curl -X POST http://localhost:8765/v1/memories \
  -H "Authorization: Bearer nm_xxx" \
  -d '{"user_id": "alice", "content": "Hello World"}'
```

### 在线文档

- **Swagger UI**: http://localhost:8765/docs
- **ReDoc**: http://localhost:8765/redoc

---

## 💡 核心特性

### 统一存储
- PostgreSQL 16 + pgvector
- 结构化数据 + 向量检索
- ACID 事务保证

### 多租户隔离
- API Key 认证
- 数据按 tenant_id 严格隔离
- 支持 SaaS 模式

### 高性能
- 异步架构（FastAPI + asyncio）
- HNSW 向量索引
- BRIN 时间序列索引

### 易于集成
- Python SDK（httpx）
- REST API（OpenAPI 3.0）
- 完整的类型提示

---

## 📖 文档结构

```
docs/v2/
├── README.md               # 本文档（文档中心）
├── GETTING_STARTED.md      # 快速开始
├── ARCHITECTURE.md         # 架构设计
├── API_REFERENCE.md        # API 参考
└── SDK_GUIDE.md            # SDK 指南
```

---

## 🆚 v1 vs v2

| 特性 | v1 (已弃用) | v2 (当前版本) |
|------|-------------|---------------|
| 向量存储 | Qdrant | PostgreSQL + pgvector |
| 图存储 | Neo4j | 移除（未来考虑 AGE） |
| 认证 | 无 | API Key 多租户 |
| 部署复杂度 | 3 个服务 | 2 个服务 |
| LLM 集成 | Mem0 内置 | 客户端自行集成 |

**迁移指南**: 见 [ARCHITECTURE.md - v1 迁移说明](ARCHITECTURE.md#8-v1-迁移说明)

---

## 🛠️ 技术栈

| 组件 | 技术 | 版本 |
|------|------|------|
| API 框架 | FastAPI | 0.104+ |
| 数据库 | PostgreSQL | 16+ |
| 向量扩展 | pgvector | 0.5+ |
| ORM | SQLAlchemy | 2.0+ |
| SDK | httpx | 0.25+ |
| Embedding | SiliconFlow | BAAI/bge-m3 (1024维) |

---

## 📦 安装

### Docker Compose（推荐）

```bash
git clone https://github.com/your-repo/NeuroMemory.git
cd NeuroMemory
docker compose -f docker-compose.v2.yml up -d
```

### 本地开发

```bash
# 启动数据库
docker compose -f docker-compose.v2.yml up -d db

# 安装依赖
pip install -r requirements.txt
pip install -e sdk/

# 启动 API
uvicorn server.app.main:app --reload --port 8765
```

详见 [快速开始](GETTING_STARTED.md)

---

## 🎯 使用示例

### Python SDK

```python
from neuromemory_client import NeuroMemoryClient

client = NeuroMemoryClient(api_key="nm_xxx")

# 添加记忆
client.add_memory(
    user_id="alice",
    content="I work at ABC Company",
    memory_type="fact"
)

# 语义检索
results = client.search(
    user_id="alice",
    query="workplace",
    limit=5
)
```

### REST API

```bash
curl -X POST http://localhost:8765/v1/search \
  -H "Authorization: Bearer nm_xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "alice",
    "query": "workplace"
  }'
```

更多示例见 [SDK 指南](SDK_GUIDE.md)

---

## 🔗 相关链接

- **GitHub**: https://github.com/your-repo/NeuroMemory
- **Issues**: https://github.com/your-repo/NeuroMemory/issues
- **v1 文档**: [../v1/](../v1/) (已弃用，仅供参考)

---

## 📄 许可证

MIT License

---

**最后更新**: 2026-02-10
