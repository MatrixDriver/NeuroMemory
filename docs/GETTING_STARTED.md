# neuromem 快速开始指南

> **预计时间**: 10 分钟
> **最后更新**: 2026-02-24

---

## 目录

1. [环境要求](#1-环境要求)
2. [安装](#2-安装)
3. [基础用法](#3-基础用法)
4. [功能模块示例](#4-功能模块示例)
5. [下一步](#5-下一步)
6. [常见问题](#6-常见问题)

---

## 1. 环境要求

- **Python**: 3.12+
- **Docker**: 20.0+（用于运行 PostgreSQL）
- **内存**: 至少 4GB RAM

```bash
python --version   # 3.12+
docker --version   # 20.0+
```

---

## 2. 安装

### 2.1 启动 PostgreSQL

neuromem 使用 PostgreSQL + pgvector 作为存储后端。提供了预配置的 Docker Compose 文件：

```bash
git clone https://github.com/your-repo/neuromem.git
cd neuromem

# 启动 PostgreSQL（含 pgvector 扩展）
docker compose -f docker-compose.yml up -d db
```

验证数据库：
```bash
docker compose -f docker-compose.yml ps db
# STATUS 应为 healthy
```

### 2.2 安装 neuromem

```bash
# 安装核心依赖
pip install -e .

# 或安装全部可选依赖（推荐）
pip install -e ".[all]"
```

可选依赖说明：

| 依赖组 | 命令 | 用途 |
|--------|------|------|
| 核心 | `pip install -e .` | 基础功能（记忆、KV、对话、图） |
| S3 存储 | `pip install -e ".[s3]"` | 文件上传到 MinIO/S3 |
| PDF 解析 | `pip install -e ".[pdf]"` | PDF 文本提取 |
| Word 解析 | `pip install -e ".[docx]"` | Word 文档文本提取 |
| 开发 | `pip install -e ".[dev]"` | pytest、pytest-asyncio 等测试工具 |
| 全部 | `pip install -e ".[all]"` | 以上全部 |

### 2.3 获取 Embedding API Key

neuromem 需要 Embedding 服务将文本转为向量。支持两种 Provider：

**SiliconFlow**（推荐，支持中英文）：
1. 访问 [SiliconFlow](https://siliconflow.cn) 注册
2. 创建 API Key

**OpenAI**：
1. 访问 [OpenAI Platform](https://platform.openai.com)
2. 创建 API Key

---

## 3. 基础用法

### 3.1 最小示例

创建 `demo.py`：

```python
import asyncio
from neuromem import NeuroMemory, SiliconFlowEmbedding, OpenAILLM

async def main():
    async with NeuroMemory(
        database_url="postgresql+asyncpg://neuromem:neuromem@localhost:5432/neuromem",
        embedding=SiliconFlowEmbedding(api_key="your-siliconflow-key"),
        llm=OpenAILLM(api_key="your-llm-key", model="deepseek-chat"),
    ) as nm:
        # 添加对话消息（自动提取记忆）
        await nm.ingest(
            user_id="alice",
            role="user",
            content="I work at ABC Company as a software engineer",
        )
        print("Message added, memories auto-extracted")

        # 混合检索
        result = await nm.recall(user_id="alice", query="Where does Alice work?")
        for r in result["merged"]:
            print(f"  [{r['score']:.2f}] {r['content']}")

asyncio.run(main())
```

运行：
```bash
python demo.py
```

### 3.2 使用上下文管理器（推荐）

```python
async with NeuroMemory(
    database_url="postgresql+asyncpg://neuromem:neuromem@localhost:5432/neuromem",
    embedding=SiliconFlowEmbedding(api_key="your-key"),
    llm=OpenAILLM(api_key="your-llm-key", model="deepseek-chat"),
) as nm:
    await nm.ingest(user_id="alice", role="user", content="I love Python")
    result = await nm.recall(user_id="alice", query="programming")
    # 退出 with 块时自动关闭连接
```

### 3.3 使用 OpenAI Embedding

```python
from neuromem import NeuroMemory, OpenAIEmbedding, OpenAILLM

async with NeuroMemory(
    database_url="...",
    embedding=OpenAIEmbedding(api_key="your-openai-key"),
    llm=OpenAILLM(api_key="your-llm-key", model="deepseek-chat"),
) as nm:
    await nm.ingest(user_id="alice", role="user", content="Hello world")
```

---

## 4. 功能模块示例

### 4.1 KV 存储

通用键值存储，适合存储用户配置等：

```python
# 存储
await nm.kv.set("alice", "config", "language", "zh-CN")
await nm.kv.set("alice", "config", "theme", {"mode": "dark", "color": "blue"})

# 读取
value = await nm.kv.get("alice", "config", "language")
print(value)  # "zh-CN"

# 列出
items = await nm.kv.list("alice", "config")
for item in items:
    print(f"  {item.key}: {item.value}")

# 删除
await nm.kv.delete("alice", "config", "language")

# 注：用户偏好由 LLM 自动提取到 profile namespace
# prefs = await nm.kv.get("alice", "profile", "preferences")
```

### 4.2 对话管理

存储和管理会话消息：

```python
# 添加单条消息
msg = await nm.ingest(
    user_id="alice", role="user", content="Hello!"
)
print(f"Session: {msg.session_id}")

# 批量添加
session_id, ids = await nm.conversations.add_messages_batch(
    user_id="alice",
    messages=[
        {"role": "user", "content": "What's the weather?"},
        {"role": "assistant", "content": "It's sunny today!"},
    ],
)

# 获取会话历史
messages = await nm.conversations.get_session_messages(
    user_id="alice", session_id=session_id
)

# 列出所有会话
sessions = await nm.conversations.list_sessions(user_id="alice")
```

### 4.3 文件管理

需要配置 S3/MinIO 存储：

```python
from neuromem import NeuroMemory, SiliconFlowEmbedding, S3Storage

async with NeuroMemory(
    database_url="...",
    embedding=SiliconFlowEmbedding(api_key="..."),
    storage=S3Storage(
        endpoint="http://localhost:9000",
        access_key="neuromem",
        secret_key="neuromem123",
        bucket="neuromem",
    ),
) as nm:
    # 上传文件（自动提取文本和生成 embedding）
    doc = await nm.files.upload(
        user_id="alice",
        filename="report.pdf",
        file_data=open("report.pdf", "rb").read(),
        category="work",
    )
    print(f"Uploaded: {doc.filename}, extracted text: {len(doc.extracted_text)} chars")

    # 列出文件
    docs = await nm.files.list(user_id="alice")

    # 删除文件
    await nm.files.delete(user_id="alice", file_id=doc.id)
```

启动 MinIO：
```bash
docker compose -f docker-compose.yml up -d minio
```

### 4.4 图数据库

图数据库（PostgreSQL 关系表实现）：

```python
from neuromem.models.graph import NodeType, EdgeType

# 创建节点
await nm.graph.create_node(
    NodeType.USER, "alice", properties={"name": "Alice", "age": 30}
)
await nm.graph.create_node(
    NodeType.ENTITY, "google", properties={"name": "Google"}
)

# 创建关系
await nm.graph.create_edge(
    NodeType.USER, "alice",
    EdgeType.WORKS_AT,
    NodeType.ENTITY, "google",
)

# 查询邻居
neighbors = await nm.graph.get_neighbors(NodeType.USER, "alice")

# 查找路径
path = await nm.graph.find_path(
    NodeType.USER, "alice",
    NodeType.ENTITY, "google",
    max_depth=3,
)
```

### 4.5 记忆提取（需要 LLM）

配置 `llm` 后，`ingest()` 默认自动提取记忆（`auto_extract=True`）：

```python
from neuromem import OpenAILLM

async with NeuroMemory(
    database_url="...",
    embedding=SiliconFlowEmbedding(api_key="..."),
    llm=OpenAILLM(api_key="...", model="deepseek-chat"),
    reflection_interval=20,  # 每 20 条消息后台自动 digest，生成洞察（默认值）
) as nm:
    # ingest 自动提取记忆
    await nm.ingest(
        user_id="alice", role="user",
        content="I just started working at Google as a ML engineer"
    )
    # → 自动提取: fact "在 Google 担任 ML 工程师", 偏好存入 profile

    # 召回记忆（立即可用）
    result = await nm.recall(user_id="alice", query="Where does Alice work?")
    for mem in result["merged"]:
        print(f"[{mem['score']:.2f}] {mem['content']}")
```

---

## 5. 下一步

- **[架构设计](ARCHITECTURE.md)** — 了解 Provider 模式、数据模型、设计原则
- **[使用指南](SDK_GUIDE.md)** — 完整 API 参考和高级用法
- **[CLAUDE.md](../../CLAUDE.md)** — 开发约定和项目结构

---

## 6. 常见问题

### 6.1 数据库连接失败

**问题**: `connection refused`

**解决**:
```bash
# 检查容器状态
docker compose -f docker-compose.yml ps db

# 重启数据库
docker compose -f docker-compose.yml restart db

# 查看日志
docker compose -f docker-compose.yml logs db
```

### 6.2 表不存在

**问题**: `relation "embeddings" does not exist`

**解决**: `nm.init()` 会自动创建表。确保在使用前调用了 `await nm.init()`（使用 `async with` 会自动调用）。

### 6.3 向量维度不匹配

**问题**: `expected 1024 dimensions, got 1536`

**原因**: 切换了 Embedding Provider 但数据库中已有旧维度的表。

**解决**: 删除旧表重建（开发环境）：
```sql
DROP TABLE IF EXISTS embeddings CASCADE;
```
然后重新运行 `await nm.init()`。

### 6.4 Embedding API 报错

**问题**: `401 Unauthorized` 或 API 调用失败

**解决**:
1. 检查 API Key 是否正确
2. 测试 API Key 是否有效（SiliconFlow 或 OpenAI 控制台）
3. 检查网络连接

### 6.5 文件上传失败

**问题**: `Storage not configured`

**解决**: 文件功能需要配置 `S3Storage`：
```python
nm = NeuroMemory(
    ...,
    storage=S3Storage(endpoint="http://localhost:9000", ...),
)
```
确保 MinIO 已启动：`docker compose -f docker-compose.yml up -d minio`

---

## 附录

### A. 环境变量配置

推荐使用环境变量管理敏感信息：

```python
import os
from neuromem import NeuroMemory, SiliconFlowEmbedding

nm = NeuroMemory(
    database_url=os.environ["DATABASE_URL"],
    embedding=SiliconFlowEmbedding(api_key=os.environ["SILICONFLOW_API_KEY"]),
)
```

### B. 服务端口

| 服务 | 端口 | 说明 |
|------|------|------|
| PostgreSQL | 5432 | 数据库 |
| MinIO API | 9000 | 对象存储 |
| MinIO Console | 9001 | MinIO 管理界面 |

### C. 常用命令

```bash
# 启动全部服务
docker compose -f docker-compose.yml up -d

# 只启动数据库
docker compose -f docker-compose.yml up -d db

# 停止全部服务
docker compose -f docker-compose.yml down

# 清理数据（会删除所有数据）
docker compose -f docker-compose.yml down -v

# 运行测试
pytest tests/ -v --timeout=30
```

---

**需要帮助？** 提交 Issue: https://github.com/your-repo/neuromem/issues
