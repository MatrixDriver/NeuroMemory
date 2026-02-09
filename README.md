# NeuroMemory

**神经符号混合记忆系统 (Neuro-Symbolic Hybrid Memory)**

一个模拟人类大脑海马体和大脑皮层工作方式的 AI 记忆系统，融合知识图谱 (GraphRAG) + 高维向量 (Vector) + 情景记忆 (Episodic Memory)，实现超越传统 RAG 的多跳推理能力。

## 核心特性

- **混合记忆架构**: 结合 Neo4j 知识图谱与 Qdrant 向量数据库，同时处理结构化逻辑和模糊语义
- **多跳推理**: 通过图谱路径实现复杂的实体关系推理，如 `Demis → DeepMind → Gemini`
- **自动知识提取**: 利用 LLM 自动从对话中提取实体关系并构建知识图谱
- **Session 管理**: 内部自动管理短期记忆，超时自动整合为长期记忆
- **指代消解**: 检索时规则匹配，整合时 LLM 消解，支持跨轮次指代
- **隐私过滤**: LLM 分类 PRIVATE/PUBLIC，只存储私有数据
- **灵活的模型切换**: 支持 DeepSeek / Gemini 作为推理引擎，本地 HuggingFace / Gemini / SiliconFlow 作为 Embedding
- **记忆演化**: 知识图谱具有自我纠错能力，随使用时间形成致密的专家知识网络
- **多种接入方式**: REST API、CLI 工具、MCP Server

## 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                    NeuroMemory 三层架构                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐ │
│  │  关联记忆        │  │  语义记忆        │  │  情景流      │ │
│  │  (Graph Layer)  │  │  (Vector Layer) │  │  (Episodic) │ │
│  │                 │  │                 │  │             │ │
│  │  Neo4j 图谱     │  │  Qdrant 向量    │  │  LLM 长窗口  │ │
│  │  存储硬逻辑      │  │  模糊语义检索    │  │  完整对话    │ │
│  │  实体关系       │  │  384/768 维     │  │  上下文      │ │
│  └────────┬────────┘  └────────┬────────┘  └──────┬──────┘ │
│           │                    │                  │        │
│           └────────────────────┼──────────────────┘        │
│                                │                           │
│                    ┌───────────▼───────────┐               │
│                    │      Mem0 Framework   │               │
│                    │    混合检索 & 整合     │               │
│                    └───────────┬───────────┘               │
│                                │                           │
│                    ┌───────────▼───────────┐               │
│                    │   LLM (DeepSeek/Gemini)│               │
│                    │      深度推理引擎       │               │
│                    └───────────────────────┘               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 认知流程

1. **Session 管理**: 自动获取或创建 Session，管理短期记忆
2. **指代消解（检索时）**: 规则匹配，快速消解代词（"这个"→名词、"她/他"→人名）
3. **混合检索**: 并行执行向量搜索和图谱遍历，返回结构化结果
4. **返回结果**: 立即返回 `memories`、`relations`、`resolved_query`
5. **Session 整合（后台）**: Session 超时或显式结束时，LLM 消解 + 隐私过滤 + 存储

## 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| LLM | DeepSeek / Gemini | 可切换，用于推理和实体提取 |
| Embedding | HuggingFace / Gemini / SiliconFlow | 可切换，384/768/1024 维向量 |
| Vector DB | Qdrant | 高性能向量数据库 |
| Graph DB | Neo4j 5.26.0 | 知识图谱存储 |
| Framework | Mem0 + LangChain | 混合记忆管理 |

## 在线演示（Railway 部署）

项目已部署在 [Railway](https://railway.app)，可远程访问：

- **REST API**: https://<your-app>.up.railway.app/
- **API 文档 (Swagger)**: https://<your-app>.up.railway.app/docs
- **健康检查**: https://<your-app>.up.railway.app/health

> Neo4j 和 Qdrant 通过 Railway 内部网络互联，不对外暴露。凭证见 Railway Dashboard 或 `CREDENTIALS.local.md`。

---

## 快速开始

### 环境要求

- Python 3.10+
- Docker & Docker Compose
- 至少 8GB RAM

### 1. 克隆项目

```bash
git clone https://github.com/your-repo/NeuroMemory.git
cd NeuroMemory
```

### 2. 创建虚拟环境

```bash
# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Linux/macOS
python -m venv .venv
source .venv/bin/activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 配置 API 密钥

创建 `.env` 文件：

```env
GOOGLE_API_KEY=your-gemini-api-key
DEEPSEEK_API_KEY=your-deepseek-api-key
SILICONFLOW_API_KEY=your-siliconflow-api-key
```

### 5. 启动数据库服务

```bash
docker-compose up -d
```

服务启动后：
- Neo4j Browser: http://localhost:7474 (用户名: `neo4j`, 密码: `railway2025`)
- Qdrant API: http://localhost:6400

### 6. 运行演示

```bash
python main.py
```

## 配置说明

在 `config.py` 中修改以下变量切换模型：

```python
# LLM 提供商: "gemini" 或 "deepseek"
LLM_PROVIDER = "deepseek"

# Embedding 提供商: "gemini", "local" (本地 HuggingFace), "siliconflow"
EMBEDDING_PROVIDER = "siliconflow"

# 是否启用图谱存储 (Neo4j)
ENABLE_GRAPH_STORE = True
```

### 模型配置详情

| 配置 | Gemini | DeepSeek |
|------|--------|----------|
| LLM 模型 | gemini-2.0-flash | deepseek-chat |
| 温度 | 0.7 | 0.7 |
| API | Google AI | OpenAI 兼容 |

| 配置 | Local | SiliconFlow | Gemini |
|------|-------|-------------|--------|
| Embedding 模型 | paraphrase-multilingual-MiniLM-L12-v2 | BAAI/bge-m3 | text-embedding-004 |
| 向量维度 | 384 | 1024 | 768 |

## 使用示例

### REST API（推荐）

```bash
# 启动服务
uvicorn http_server:app --host 0.0.0.0 --port 8765 --reload

# 存储记忆
curl -X POST http://localhost:8765/process \
  -H "Content-Type: application/json" \
  -d '{"input": "DeepMind 是 Google 的子公司", "user_id": "user_001"}'

# 查询记忆
curl -X POST http://localhost:8765/process \
  -H "Content-Type: application/json" \
  -d '{"input": "Demis Hassabis 和 Gemini 有什么关系？", "user_id": "user_001"}'
```

详细文档请参考 [用户接口文档](docs/USER_API.md)。

### REST API

```bash
# 处理记忆（生产模式）
curl -X POST http://localhost:8765/process \
  -H "Content-Type: application/json" \
  -d '{"input": "我女儿叫灿灿，今年5岁了", "user_id": "user_001"}'

# 查询记忆
curl -X POST http://localhost:8765/process \
  -H "Content-Type: application/json" \
  -d '{"input": "我女儿叫什么名字？", "user_id": "user_001"}'

# 获取知识图谱
curl http://localhost:8765/graph/user_001
```

### CLI 工具

```bash
# 安装后使用
uv pip install -e .

# 检查状态
neuromemory status

# 添加记忆
neuromemory add "DeepMind 是 Google 的子公司" --user user_001

# 检索记忆
neuromemory search "Google 有哪些子公司" --user user_001 --limit 5

# 基于记忆回答问题
neuromemory ask "Demis 和 Gemini 有什么关系" --user user_001

# 导出知识图谱
neuromemory graph export --user user_001 -o graph.json

# 可视化知识图谱
neuromemory graph visualize --user user_001 --open-browser
```

## 项目结构

```
NeuroMemory/
├── config.py              # 配置模块（模型切换、数据库连接）
├── private_brain.py       # 核心处理引擎
├── session_manager.py     # Session 管理器
├── coreference.py         # 指代消解器
├── consolidator.py        # Session 整合器
├── privacy_filter.py      # 隐私过滤器
├── http_server.py         # REST API 服务（FastAPI）
├── mcp_server.py          # MCP Server
├── main.py                # CLI 演示工具
├── neuromemory/           # CLI 工具
│   ├── __init__.py        # 包初始化
│   └── cli.py             # CLI 工具（Typer）
├── docs/                  # 架构文档
│   ├── ARCHITECTURE.md    # 主架构文档
│   ├── API.md             # 接口设计
│   └── ...
├── docker-compose.yml     # 数据库服务配置
└── .env                   # API 密钥（不提交到 Git）
```

## 为什么优于传统 RAG？

| 特性 | 传统向量 RAG | NeuroMemory |
|------|-------------|-------------|
| 逻辑推理 | 只能语义相似度匹配 | 图谱路径多跳推理 |
| 实体关系 | 扁平化存储，关系丢失 | 显式存储 `(A)-[关系]->(B)` |
| 信息更新 | 累加矛盾记录 | 图谱自我纠错，更新边属性 |
| 长期演化 | 噪音增加，Recall 下降 | 知识网络越来越致密 |

## 常用命令

```bash
# 启动数据库服务
docker-compose up -d

# 停止服务
docker-compose down

# 安装 CLI 工具
uv pip install -e .  # 或 pip install -e .

# 启动 HTTP Server（开发模式）
uvicorn http_server:app --host 0.0.0.0 --port 8765 --reload

# 启动 HTTP Server（生产模式）
uvicorn http_server:app --host 0.0.0.0 --port 8765 --workers 4

# 运行 CLI 演示
python main.py

# 运行测试
pytest                    # 全部测试
pytest -m "not slow"      # 跳过 LLM 调用的测试
```

## License

MIT License
