# NeuroMemory v2 快速开始指南

> **版本**: v2.0
> **预计时间**: 10 分钟
> **最后更新**: 2026-02-10

---

## 目录

1. [环境要求](#1-环境要求)
2. [安装部署](#2-安装部署)
3. [获取 API Key](#3-获取-api-key)
4. [使用 Python SDK](#4-使用-python-sdk)
5. [使用 REST API](#5-使用-rest-api)
6. [下一步](#6-下一步)
7. [常见问题](#7-常见问题)

---

## 1. 环境要求

### 1.1 系统要求

- **操作系统**: Linux / macOS / Windows
- **Python**: 3.10 或更高版本
- **Docker**: 20.0 或更高版本（推荐）
- **内存**: 至少 4GB RAM

### 1.2 检查环境

```bash
# 检查 Python 版本
python --version  # 应该是 3.10+

# 检查 Docker 版本
docker --version  # 应该是 20.0+
docker compose version
```

---

## 2. 安装部署

### 2.1 克隆项目

```bash
git clone https://github.com/your-repo/NeuroMemory.git
cd NeuroMemory
```

### 2.2 配置环境变量

创建 `.env` 文件：

```bash
# 复制模板
cp .env.example .env

# 编辑配置
nano .env
```

`.env` 文件内容：
```bash
# 数据库配置（Docker Compose 会自动使用）
DATABASE_URL=postgresql+asyncpg://neuromemory:neuromemory@db:5432/neuromemory

# Embedding 服务 API Key
SILICONFLOW_API_KEY=your-siliconflow-api-key

# 日志级别
LOG_LEVEL=INFO
```

**获取 SiliconFlow API Key**:
1. 访问 [SiliconFlow](https://siliconflow.cn)
2. 注册账号并创建 API Key
3. 复制 Key 到 `.env` 文件

### 2.3 启动服务

#### 方式 1: Docker Compose（推荐）

```bash
# 启动所有服务（数据库 + API）
docker compose -f docker-compose.v2.yml up -d

# 查看日志
docker compose -f docker-compose.v2.yml logs -f api

# 检查服务状态
curl http://localhost:8765/v1/health
```

#### 方式 2: 本地开发

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

### 2.4 验证部署

访问 API 文档：
- **Swagger UI**: http://localhost:8765/docs
- **ReDoc**: http://localhost:8765/redoc

健康检查：
```bash
curl http://localhost:8765/v1/health
```

预期响应：
```json
{
  "status": "healthy",
  "database": "connected",
  "embedding_service": "available",
  "version": "2.0.0"
}
```

---

## 3. 获取 API Key

### 3.1 注册租户

使用 curl 注册：

```bash
curl -X POST http://localhost:8765/v1/tenants/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "MyCompany",
    "email": "admin@example.com"
  }'
```

或使用 Python：

```python
import httpx

response = httpx.post(
    "http://localhost:8765/v1/tenants/register",
    json={
        "name": "MyCompany",
        "email": "admin@example.com"
    }
)
data = response.json()
print(f"Your API Key: {data['api_key']}")
```

### 3.2 保存 API Key

**响应示例**:
```json
{
  "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
  "api_key": "nm_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "message": "Registration successful. Please save your API key securely."
}
```

**⚠️ 重要**:
- API Key 只显示一次，请妥善保存
- 如果丢失，需要重新注册新租户
- 不要将 API Key 提交到 Git 仓库

---

## 4. 使用 Python SDK

### 4.1 安装 SDK

```bash
pip install -e sdk/
```

### 4.2 快速示例

创建 `demo.py`:

```python
from neuromemory_client import NeuroMemoryClient

# 初始化客户端（替换为你的 API Key）
client = NeuroMemoryClient(
    api_key="nm_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    base_url="http://localhost:8765"
)

# 1. 设置用户偏好
print("1. Setting preference...")
client.preferences.set(
    user_id="alice",
    key="language",
    value="zh-CN"
)
print("✓ Preference set: language=zh-CN\n")

# 2. 添加记忆
print("2. Adding memories...")
client.add_memory(
    user_id="alice",
    content="I work at ABC Company as a software engineer",
    memory_type="fact"
)
client.add_memory(
    user_id="alice",
    content="My favorite programming language is Python",
    memory_type="preference"
)
client.add_memory(
    user_id="alice",
    content="Attended team meeting on project planning",
    memory_type="episodic"
)
print("✓ Added 3 memories\n")

# 3. 语义检索
print("3. Searching memories...")
results = client.search(
    user_id="alice",
    query="What does Alice do for work?",
    limit=3
)
print(f"Found {len(results)} results:")
for i, result in enumerate(results, 1):
    print(f"  {i}. [{result['similarity']:.2f}] {result['content']}")
print()

# 4. 查询偏好
print("4. Listing preferences...")
prefs = client.preferences.list(user_id="alice")
for pref in prefs:
    print(f"  {pref['key']}: {pref['value']}")
print()

# 5. 获取最近记忆
print("5. Getting recent memories...")
recent = client.get_recent_memories(user_id="alice", days=7)
print(f"✓ Found {len(recent)} memories in the last 7 days\n")

# 6. 用户概览
print("6. User memory overview...")
overview = client.get_user_memories(user_id="alice")
print(f"  Total: {overview['total_memories']} memories")
print(f"  Types: {overview['memory_types']}")

# 关闭客户端
client.close()
print("\n✓ Demo completed!")
```

运行示例：

```bash
python demo.py
```

预期输出：
```
1. Setting preference...
✓ Preference set: language=zh-CN

2. Adding memories...
✓ Added 3 memories

3. Searching memories...
Found 3 results:
  1. [0.89] I work at ABC Company as a software engineer
  2. [0.72] Attended team meeting on project planning
  3. [0.65] My favorite programming language is Python

4. Listing preferences...
  language: zh-CN

5. Getting recent memories...
✓ Found 3 memories in the last 7 days

6. User memory overview...
  Total: 3 memories
  Types: {'fact': 1, 'preference': 1, 'episodic': 1}

✓ Demo completed!
```

---

## 5. 使用 REST API

### 5.1 设置偏好

```bash
curl -X POST http://localhost:8765/v1/preferences \
  -H "Authorization: Bearer nm_xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "alice",
    "key": "language",
    "value": "zh-CN"
  }'
```

### 5.2 添加记忆

```bash
curl -X POST http://localhost:8765/v1/memories \
  -H "Authorization: Bearer nm_xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "alice",
    "content": "I work at ABC Company",
    "memory_type": "fact"
  }'
```

### 5.3 语义检索

```bash
curl -X POST http://localhost:8765/v1/search \
  -H "Authorization: Bearer nm_xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "alice",
    "query": "workplace",
    "limit": 5
  }'
```

### 5.4 查询偏好

```bash
curl http://localhost:8765/v1/preferences?user_id=alice \
  -H "Authorization: Bearer nm_xxx"
```

### 5.5 时间范围查询

```bash
curl -X POST http://localhost:8765/v1/memories/time-range \
  -H "Authorization: Bearer nm_xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "alice",
    "start_time": "2026-02-01T00:00:00Z",
    "end_time": "2026-02-10T23:59:59Z",
    "limit": 50
  }'
```

---

## 6. 下一步

### 6.1 深入学习

- 📖 [架构文档](ARCHITECTURE.md) - 了解系统设计
- 📚 [API 参考](API_REFERENCE.md) - 完整的 API 端点文档
- 🐍 [SDK 指南](SDK_GUIDE.md) - Python SDK 详细用法
- 🔒 [安全最佳实践](#) - API Key 管理、数据隔离

### 6.2 功能探索

**偏好管理**:
```python
# 存储复杂对象
client.preferences.set(
    user_id="alice",
    key="ui_settings",
    value={
        "theme": "dark",
        "sidebar": "collapsed",
        "notifications": {"email": True, "push": False}
    }
)
```

**时间查询**:
```python
from datetime import datetime, timezone

# 查询特定月份的记忆
results = client.memory.get_by_time_range(
    user_id="alice",
    start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
    end_time=datetime(2026, 1, 31, 23, 59, 59, tzinfo=timezone.utc)
)
```

**时间线统计**:
```python
from datetime import date

# 按周统计记忆
timeline = client.get_memory_timeline(
    user_id="alice",
    start_date=date(2026, 1, 1),
    end_date=date(2026, 12, 31),
    granularity="week"
)
```

### 6.3 生产部署

准备将服务部署到生产环境？

1. **环境变量**:
   - 使用强密码配置数据库
   - 配置生产级的 `DATABASE_URL`
   - 设置 `LOG_LEVEL=WARNING` 或 `ERROR`

2. **HTTPS 配置**:
   - 使用 Nginx 或 Traefik 作为反向代理
   - 配置 SSL 证书（Let's Encrypt）

3. **数据库**:
   - 使用云托管 PostgreSQL（AWS RDS、阿里云 RDS 等）
   - 启用自动备份
   - 配置连接池

4. **监控**:
   - 配置日志聚合（ELK、Loki）
   - 设置健康检查和告警

---

## 7. 常见问题

### 7.1 服务无法启动

**问题**: Docker Compose 启动失败

**解决方案**:
```bash
# 检查端口占用
lsof -i :8765  # API 端口
lsof -i :5432  # PostgreSQL 端口

# 查看详细日志
docker compose -f docker-compose.v2.yml logs

# 重新构建镜像
docker compose -f docker-compose.v2.yml build --no-cache
docker compose -f docker-compose.v2.yml up -d
```

### 7.2 数据库连接失败

**问题**: `connection refused` 或 `database does not exist`

**解决方案**:
```bash
# 检查数据库容器状态
docker compose -f docker-compose.v2.yml ps

# 初始化数据库
docker compose -f docker-compose.v2.yml exec api \
  python -m server.app.db.init_db

# 检查环境变量
docker compose -f docker-compose.v2.yml exec api env | grep DATABASE_URL
```

### 7.3 Embedding 服务不可用

**问题**: `503 Service Unavailable` 或 `Embedding service unavailable`

**解决方案**:
1. 检查 `.env` 文件中的 `SILICONFLOW_API_KEY` 是否正确
2. 验证 API Key 是否有效：
   ```bash
   curl https://api.siliconflow.cn/v1/embeddings \
     -H "Authorization: Bearer YOUR_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"model": "BAAI/bge-m3", "input": "test"}'
   ```
3. 检查网络连接（防火墙、代理）

### 7.4 API Key 丢失

**问题**: 忘记保存 API Key

**解决方案**:
- API Key 无法恢复，需要重新注册新租户
- 或者直接查询数据库（仅开发环境）：
  ```bash
  docker compose -f docker-compose.v2.yml exec db psql -U neuromemory -d neuromemory \
    -c "SELECT id, name, email FROM tenants;"
  ```

### 7.5 搜索结果为空

**问题**: `client.search()` 返回空列表

**可能原因**:
1. 没有添加记忆数据
2. `user_id` 不匹配
3. 时间过滤条件过于严格
4. Embedding 生成失败

**调试步骤**:
```python
# 1. 检查记忆总数
overview = client.get_user_memories(user_id="alice")
print(overview)

# 2. 列出最近记忆
recent = client.get_recent_memories(user_id="alice", days=30)
print(f"Recent memories: {len(recent)}")

# 3. 不使用过滤条件
results = client.search(user_id="alice", query="test", limit=100)
print(f"Total results: {len(results)}")
```

### 7.6 性能问题

**问题**: API 响应慢

**优化建议**:
1. **数据库索引**: 确保已运行 `migrations/001_add_time_indexes.sql`
2. **限制结果数**: 使用合理的 `limit` 参数（默认 5-50）
3. **分页查询**: 使用 `offset` 避免一次性加载大量数据
4. **连接池**: 增加数据库连接池大小（生产环境）

---

## 附录

### A. 环境变量完整列表

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `DATABASE_URL` | 是 | - | PostgreSQL 连接字符串 |
| `SILICONFLOW_API_KEY` | 是 | - | SiliconFlow API Key |
| `EMBEDDING_PROVIDER` | 否 | `siliconflow` | Embedding 提供商 |
| `LOG_LEVEL` | 否 | `INFO` | 日志级别 (DEBUG/INFO/WARNING/ERROR) |

### B. 端口说明

| 服务 | 端口 | 说明 |
|------|------|------|
| API Server | 8765 | REST API 端点 |
| PostgreSQL | 5432 | 数据库（内部网络） |

### C. 数据目录

```
.
├── .env                # 环境变量配置
├── docker-compose.v2.yml  # Docker Compose 配置
├── server/             # API 服务端代码
├── sdk/                # Python SDK 代码
└── postgres_data/      # PostgreSQL 数据卷（Docker 创建）
```

### D. 有用的命令

```bash
# 查看所有容器
docker compose -f docker-compose.v2.yml ps

# 重启 API 服务
docker compose -f docker-compose.v2.yml restart api

# 查看 API 日志
docker compose -f docker-compose.v2.yml logs -f api

# 进入数据库容器
docker compose -f docker-compose.v2.yml exec db psql -U neuromemory

# 停止所有服务
docker compose -f docker-compose.v2.yml down

# 清理数据（⚠️ 会删除所有数据）
docker compose -f docker-compose.v2.yml down -v
```

---

**需要帮助？**
- 📧 提交 Issue: https://github.com/your-repo/NeuroMemory/issues
- 📖 查看完整文档: [docs/v2/](.)

**祝使用愉快！** 🎉
