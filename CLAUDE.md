# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

NeuroMemory 是一个神经符号混合记忆系统（Neuro-Symbolic Hybrid Memory），实现类人脑的三层记忆架构：

- **关联记忆 (Graph Layer)**: Neo4j 知识图谱，存储实体关系和硬逻辑
- **语义记忆 (Vector Layer)**: Qdrant 向量数据库，负责语义检索
- **情景流 (Episodic Stream)**: LLM 长窗口，保留完整对话历史

## 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| LLM | DeepSeek / Gemini | 可切换，用于推理和实体提取 |
| Embedding | 本地 HuggingFace / Gemini | 可切换，384/768 维向量 |
| Vector DB | Qdrant | localhost:6333 |
| Graph DB | Neo4j 5.26.0 | localhost:7474 (Web), localhost:17687 (Bolt) |
| Framework | Mem0 + LangGraph | 混合记忆管理 |

## 常用命令

```bash
# 启动数据库服务
docker-compose up -d

# 停止服务
docker-compose down

# 查看服务状态
docker-compose ps

# 激活虚拟环境 (PowerShell)
.\.venv\Scripts\Activate.ps1

# 运行主程序
python main.py
```

## 服务访问

- Neo4j Browser: http://localhost:7474 (用户名: `neo4j`, 密码: `password123`)
- Qdrant API: http://localhost:6333

## 环境变量

在 `.env` 文件中配置：
```
GOOGLE_API_KEY=your-gemini-api-key
DEEPSEEK_API_KEY=your-deepseek-api-key
```

## 模型切换配置

在 `config.py` 中修改以下变量切换模型：

```python
# LLM 提供商: "gemini" 或 "deepseek"
LLM_PROVIDER = "deepseek"

# Embedding 提供商: "gemini" 或 "local" (本地 HuggingFace)
EMBEDDING_PROVIDER = "local"

# 是否启用图谱存储
ENABLE_GRAPH_STORE = True
```

## 架构模式

系统使用 Mem0 的混合存储配置，核心认知流程：

1. **混合检索**: 并行执行向量搜索和图谱遍历
2. **深度推理**: LLM 基于知识网络进行多跳推理
3. **记忆整合**: 自动提取实体关系并更新图谱

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
└── qdrant_data/       # Qdrant 数据持久化
```

详细架构设计参见 `架构文档.md`。
