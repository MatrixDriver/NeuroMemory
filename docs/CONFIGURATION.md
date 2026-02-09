# 配置参考

> 返回 [主架构文档](ARCHITECTURE.md)

---

## 目录

- [环境变量](#环境变量)
- [模型切换配置](#模型切换配置)
- [LLM 模型配置](#llm-模型配置)
- [Embedding 模型配置](#embedding-模型配置)
- [数据库连接配置](#数据库连接配置)
- [Collection 命名规则](#collection-命名规则)
- [Docker Compose 服务配置](#docker-compose-服务配置)

---

## 环境变量

| 变量名 | 必填 | 默认值 | 说明 |
|--------|------|--------|------|
| `DEEPSEEK_API_KEY` | 是* | - | DeepSeek API 密钥 |
| `GOOGLE_API_KEY` | 是* | - | Google Gemini API 密钥 |
| `SILICONFLOW_API_KEY` | 是* | - | SiliconFlow API 密钥（用于 bge-m3 Embedding） |

> \* 根据 `LLM_PROVIDER` 和 `EMBEDDING_PROVIDER` 设置，至少需要其中一个
>
> - 使用 DeepSeek LLM: 需要 `DEEPSEEK_API_KEY`
> - 使用 Gemini LLM/Embedding: 需要 `GOOGLE_API_KEY`
> - 使用 SiliconFlow Embedding: 需要 `SILICONFLOW_API_KEY`

---

## 模型切换配置

在 `config.py` 中修改以下变量：

```python
# LLM 提供商选择
LLM_PROVIDER = "deepseek"  # 可选: "deepseek" | "gemini"

# Embedding 提供商选择
EMBEDDING_PROVIDER = "siliconflow"  # 可选: "local" | "gemini" | "siliconflow"

# 图谱存储开关
ENABLE_GRAPH_STORE = True  # True: 启用 Neo4j | False: 仅向量存储
```

---

## LLM 模型配置

| 提供商 | 模型 | 用途 | 温度 |
|--------|------|------|------|
| DeepSeek | deepseek-chat | 对话推理 | 0.7 |
| DeepSeek | deepseek-chat | 实体提取 (Mem0) | 0.0 |
| Gemini | gemini-2.0-flash | 对话推理 | 0.7 |
| Gemini | gemini-2.0-flash | 实体提取 (Mem0) | 0.0 |

---

## Embedding 模型配置

| 提供商 | 模型 | 维度 | 说明 |
|--------|------|------|------|
| Local (HuggingFace) | paraphrase-multilingual-MiniLM-L12-v2 | 384 | 本地运行，无 API 成本 |
| Gemini | text-embedding-004 | 768 | Google 云端 API |
| SiliconFlow | BAAI/bge-m3 | 1024 | 国内云端，高精度，OpenAI 兼容接口 |

### SiliconFlow 配置详情

```python
SILICONFLOW_EMBEDDING_CONFIG = {
    "provider": "openai",  # 使用 OpenAI 兼容接口
    "config": {
        "model": "BAAI/bge-m3",
        "embedding_dims": 1024,
        "openai_base_url": "https://api.siliconflow.cn/v1",
        "api_key": SILICONFLOW_API_KEY,
    },
}
```

---

## 数据库连接配置

### Neo4j 配置

```python
# 在 MEM0_CONFIG 中
"graph_store": {
    "provider": "neo4j",
    "config": {
        "url": "bolt://localhost:17687",  # 单实例使用 bolt://，集群使用 neo4j://
        "username": "neo4j",
        "password": "railway2025",
    },
}
```

### Qdrant 配置

```python
# 在 MEM0_CONFIG 中
"vector_store": {
    "provider": "qdrant",
    "config": {
        "host": "localhost",
        "port": 6400,  # 统一使用 6400 端口
        "collection_name": "neuro_memory_huggingface_384",  # 自动生成
    },
}
```

---

## Collection 命名规则

向量数据库的 Collection 名称根据 Embedding 配置自动生成：

```
neuro_memory_{provider}_{dims}
```

示例：
- 本地 HuggingFace: `neuro_memory_huggingface_384`
- Gemini: `neuro_memory_gemini_768`
- SiliconFlow (bge-m3): `neuro_memory_openai_1024`

> 这确保了不同 Embedding 模型的向量不会混在同一个 Collection 中
>
> 注意：SiliconFlow 使用 OpenAI 兼容接口，因此 provider 名称为 `openai`

---

## Docker Compose 服务配置

```yaml
# docker-compose.yml 关键配置

services:
  neo4j:
    image: neo4j:5.26.0
    ports:
      - "7474:7474"   # Browser UI
      - "17687:7687"  # Bolt 协议 (注意: 映射到 17687)
    environment:
      - NEO4J_AUTH=neo4j/railway2025
      - NEO4J_PLUGINS=["apoc", "graph-data-science"]

  qdrant:
    image: qdrant/qdrant:latest
    environment:
      - QDRANT__SERVICE__HTTP_PORT=6400
    ports:
      - "6400:6400"   # REST API + Dashboard（统一使用 6400 端口）
```

---

## 相关文档

- [快速开始](GETTING_STARTED.md) - 安装和运行指南
- [部署架构](DEPLOYMENT.md) - 详细部署配置
