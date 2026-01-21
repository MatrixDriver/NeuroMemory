# NeuroMemory

**神经符号混合记忆系统 (Neuro-Symbolic Hybrid Memory)**

一个模拟人类大脑海马体和大脑皮层工作方式的 AI 记忆系统，融合知识图谱 (GraphRAG) + 高维向量 (Vector) + 情景记忆 (Episodic Memory)，实现超越传统 RAG 的多跳推理能力。

## 核心特性

- **混合记忆架构**: 结合 Neo4j 知识图谱与 Qdrant 向量数据库，同时处理结构化逻辑和模糊语义
- **多跳推理**: 通过图谱路径实现复杂的实体关系推理，如 `Demis → DeepMind → Gemini`
- **自动知识提取**: 利用 LLM 自动从对话中提取实体关系并构建知识图谱
- **灵活的模型切换**: 支持 DeepSeek / Gemini 作为推理引擎，本地 HuggingFace / Gemini / SiliconFlow 作为 Embedding
- **记忆演化**: 知识图谱具有自我纠错能力，随使用时间形成致密的专家知识网络

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

1. **混合检索 (Hybrid Retrieval)**: 并行执行向量搜索和图谱遍历
2. **深度推理 (System 2 Thinking)**: LLM 基于知识网络进行多跳推理
3. **记忆整合 (Consolidation)**: 自动提取实体关系并更新图谱

## 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| LLM | DeepSeek / Gemini | 可切换，用于推理和实体提取 |
| Embedding | HuggingFace / Gemini / SiliconFlow | 可切换，384/512/768 维向量 |
| Vector DB | Qdrant | 高性能向量数据库 |
| Graph DB | Neo4j 5.26.0 | 知识图谱存储 |
| Framework | Mem0 + LangChain | 混合记忆管理 |

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
- Neo4j Browser: http://localhost:7474 (用户名: `neo4j`, 密码: `password123`)
- Qdrant API: http://localhost:6333

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
| 向量维度 | 384 | 512 | 768 |

## 使用示例

```python
from mem0 import Memory
from config import MEM0_CONFIG

# 初始化混合记忆系统
brain = Memory.from_config(MEM0_CONFIG)

# 添加知识
brain.add("DeepMind 是 Google 的子公司。", user_id="user_001")
brain.add("Demis Hassabis 是 DeepMind 的 CEO。", user_id="user_001")
brain.add("Gemini 是 DeepMind 团队研发的。", user_id="user_001")

# 混合检索 - 同时查询向量库和知识图谱
results = brain.search("Demis Hassabis 和 Gemini 有什么关系？", user_id="user_001")

# 系统会通过图谱路径推理出:
# Demis Hassabis → CEO of → DeepMind → Created → Gemini
```

## 项目结构

```
NeuroMemory/
├── config.py          # 配置模块（模型切换、数据库连接）
├── main.py            # 主程序（认知流程实现）
├── requirements.txt   # Python 依赖
├── docker-compose.yml # 数据库服务配置
├── .env               # API 密钥（不提交到 Git）
├── .venv/             # Python 虚拟环境
├── neo4j_data/        # Neo4j 数据持久化
├── qdrant_data/       # Qdrant 数据持久化
└── 架构文档.md         # 详细架构设计文档
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
# 启动服务
docker-compose up -d

# 停止服务
docker-compose down

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f

# 运行主程序
python main.py
```

## License

MIT License
