"""
NeuroMemory 配置模块
神经符号混合记忆系统的核心配置
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量
load_dotenv(Path(__file__).parent / ".env")

# =============================================================================
# API 密钥配置
# =============================================================================
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")

# 设置环境变量供 SDK 使用
if GOOGLE_API_KEY:
    os.environ["GOOGLE_API_KEY"] = GOOGLE_API_KEY
if DEEPSEEK_API_KEY:
    os.environ["OPENAI_API_KEY"] = DEEPSEEK_API_KEY

# =============================================================================
# 模型切换开关 (在这里修改来切换模型提供商)
# =============================================================================

# LLM 提供商选择: "gemini" 或 "deepseek"
LLM_PROVIDER = "deepseek"

# Embedding 提供商选择: "gemini", "local" (本地 HuggingFace), "siliconflow"
EMBEDDING_PROVIDER = "siliconflow"

# 是否启用图谱存储 (Neo4j)
ENABLE_GRAPH_STORE = True

# =============================================================================
# 模型配置详情
# =============================================================================

# Gemini 模型配置
GEMINI_CONFIG = {
    "llm": {
        "provider": "gemini",
        "config": {
            "model": "gemini-2.0-flash",
            "temperature": 0.0,
        },
    },
    "embedder": {
        "provider": "gemini",
        "config": {
            "model": "models/text-embedding-004",
            "embedding_dims": 768,
        },
    },
    "chat_model": "gemini-2.0-flash",
    "chat_temperature": 0.7,
    "base_url": None,  # Gemini 不需要 base_url
}

# DeepSeek 模型配置
DEEPSEEK_CONFIG = {
    "llm": {
        "provider": "openai",
        "config": {
            "model": "deepseek-chat",
            "temperature": 0.0,
            "openai_base_url": "https://api.deepseek.com",
        },
    },
    "chat_model": "deepseek-chat",
    "chat_temperature": 0.7,
    "base_url": "https://api.deepseek.com",
}

# 本地 Embedding 配置 (HuggingFace)
LOCAL_EMBEDDING_CONFIG = {
    "provider": "huggingface",
    "config": {
        "model": "paraphrase-multilingual-MiniLM-L12-v2",
        "embedding_dims": 384,
    },
}

# SiliconFlow Embedding 配置 (OpenAI 兼容接口)
SILICONFLOW_EMBEDDING_CONFIG = {
    "provider": "openai",
    "config": {
        "model": "BAAI/bge-m3",
        "embedding_dims": 1024,  # bge-m3 实际维度为 1024
        "openai_base_url": "https://api.siliconflow.cn/v1",
        "api_key": SILICONFLOW_API_KEY,
    },
}

# =============================================================================
# 根据开关生成最终配置
# =============================================================================

def _get_llm_config() -> dict:
    """根据 LLM_PROVIDER 返回对应的 LLM 配置"""
    if LLM_PROVIDER == "gemini":
        return GEMINI_CONFIG["llm"]
    elif LLM_PROVIDER == "deepseek":
        return DEEPSEEK_CONFIG["llm"]
    else:
        raise ValueError(f"未知的 LLM 提供商: {LLM_PROVIDER}")


def _get_embedder_config() -> dict:
    """根据 EMBEDDING_PROVIDER 返回对应的 Embedding 配置"""
    if EMBEDDING_PROVIDER == "gemini":
        return GEMINI_CONFIG["embedder"]
    elif EMBEDDING_PROVIDER == "local":
        return LOCAL_EMBEDDING_CONFIG
    elif EMBEDDING_PROVIDER == "siliconflow":
        return SILICONFLOW_EMBEDDING_CONFIG
    else:
        raise ValueError(f"未知的 Embedding 提供商: {EMBEDDING_PROVIDER}")


def _get_collection_name() -> str:
    """根据 Embedding 配置返回对应的 collection 名称"""
    embedder = _get_embedder_config()
    dims = embedder["config"]["embedding_dims"]
    provider = embedder["provider"]
    return f"neuro_memory_{provider}_{dims}"


# Mem0 混合存储配置
MEM0_CONFIG: dict = {
    "vector_store": {
        "provider": "qdrant",
        "config": {
            "host": "localhost",
            "port": 6333,
            "collection_name": _get_collection_name(),
            "embedding_model_dims": _get_embedder_config()["config"]["embedding_dims"],  # 明确指定向量维度
        },
    },
    "llm": _get_llm_config(),
    "embedder": _get_embedder_config(),
}

# 图谱存储配置
if ENABLE_GRAPH_STORE:
    MEM0_CONFIG["graph_store"] = {
        "provider": "neo4j",
        "config": {
            "url": "neo4j://localhost:17687",
            "username": "neo4j",
            "password": "password123",
        },
    }

# =============================================================================
# 对话 LLM 配置 (供 main.py 使用)
# =============================================================================

def get_chat_config() -> dict:
    """获取当前对话 LLM 的配置"""
    if LLM_PROVIDER == "gemini":
        return {
            "model": GEMINI_CONFIG["chat_model"],
            "temperature": GEMINI_CONFIG["chat_temperature"],
            "base_url": GEMINI_CONFIG["base_url"],
            "provider": "gemini",
        }
    elif LLM_PROVIDER == "deepseek":
        return {
            "model": DEEPSEEK_CONFIG["chat_model"],
            "temperature": DEEPSEEK_CONFIG["chat_temperature"],
            "base_url": DEEPSEEK_CONFIG["base_url"],
            "provider": "openai",
        }
    else:
        raise ValueError(f"未知的 LLM 提供商: {LLM_PROVIDER}")


# 为了向后兼容，导出这些变量
_chat_config = get_chat_config()
CHAT_MODEL = _chat_config["model"]
CHAT_TEMPERATURE = _chat_config["temperature"]
DEEPSEEK_BASE_URL = DEEPSEEK_CONFIG["base_url"]
