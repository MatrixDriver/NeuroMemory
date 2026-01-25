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
# 兼容本地开发（下划线）和 ZeaBur（驼峰命名）
# =============================================================================
def _get_env_var(*names: str, default: str = "") -> str:
    """按优先级读取环境变量，支持多种命名格式"""
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default

GOOGLE_API_KEY = _get_env_var("GOOGLE_API_KEY", "GoogleApiKey", default="")
DEEPSEEK_API_KEY = _get_env_var("DEEPSEEK_API_KEY", "DeepSeekApiKey", default="")
SILICONFLOW_API_KEY = _get_env_var("SILICONFLOW_API_KEY", "SiliconFlowApiKey", default="")

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

# 配置映射表
_LLM_CONFIG_MAP = {
    "gemini": lambda: GEMINI_CONFIG["llm"],
    "deepseek": lambda: DEEPSEEK_CONFIG["llm"],
}

_EMBEDDER_CONFIG_MAP = {
    "gemini": lambda: GEMINI_CONFIG["embedder"],
    "local": lambda: LOCAL_EMBEDDING_CONFIG,
    "siliconflow": lambda: SILICONFLOW_EMBEDDING_CONFIG,
}


def _get_llm_config() -> dict:
    """根据 LLM_PROVIDER 返回对应的 LLM 配置"""
    if LLM_PROVIDER not in _LLM_CONFIG_MAP:
        raise ValueError(f"未知的 LLM 提供商: {LLM_PROVIDER}，支持: {list(_LLM_CONFIG_MAP.keys())}")
    return _LLM_CONFIG_MAP[LLM_PROVIDER]()


def _get_embedder_config() -> dict:
    """根据 EMBEDDING_PROVIDER 返回对应的 Embedding 配置"""
    if EMBEDDING_PROVIDER not in _EMBEDDER_CONFIG_MAP:
        raise ValueError(f"未知的 Embedding 提供商: {EMBEDDING_PROVIDER}，支持: {list(_EMBEDDER_CONFIG_MAP.keys())}")
    return _EMBEDDER_CONFIG_MAP[EMBEDDING_PROVIDER]()


def _get_collection_name() -> str:
    """根据 Embedding 配置返回对应的 collection 名称"""
    embedder = _get_embedder_config()
    dims = embedder["config"]["embedding_dims"]
    provider = embedder["provider"]
    return f"neuro_memory_{provider}_{dims}"


# Mem0 混合存储配置
# Qdrant：Zeabur 链接 qdrant-neuromemory 后会注入 QDRANT_NEUROMEMORY_HOST；若 QDRANT_HOST 含未解析的 {{ }}，则用其回退
_qh = os.getenv("QDRANT_HOST") or os.getenv("QDRANT_NEUROMEMORY_HOST") or "localhost"
qdrant_host = _qh if "{{" not in str(_qh) else (os.getenv("QDRANT_NEUROMEMORY_HOST") or "localhost")
qdrant_port = int(os.getenv("QDRANT_PORT", "6400"))

MEM0_CONFIG: dict = {
    "vector_store": {
        "provider": "qdrant",
        "config": {
            "host": qdrant_host,
            "port": qdrant_port,
            "collection_name": _get_collection_name(),
            "embedding_model_dims": _get_embedder_config()["config"]["embedding_dims"],  # 明确指定向量维度
        },
    },
    "llm": _get_llm_config(),
    "embedder": _get_embedder_config(),
}

# 图谱存储配置
if ENABLE_GRAPH_STORE:
    # Neo4j 连接配置（支持环境变量）
    # Zeabur：链接 neo4j-neuromemory 后会注入 NEO4J_NEUROMEMORY_HOST；若 NEO4J_URL 含未解析的 {{ }}，则用 _HOST 回退
    _neo4j_url_raw = os.getenv("NEO4J_URL", "")
    if _neo4j_url_raw and "{{" not in _neo4j_url_raw:
        neo4j_url = _neo4j_url_raw
    else:
        _h = os.getenv("NEO4J_NEUROMEMORY_HOST") or os.getenv("NEO4J_HOST") or "localhost"
        _p = int(os.getenv("NEO4J_BOLT_PORT", "17687"))
        neo4j_url = f"neo4j://{_h}:{_p}"

    neo4j_username = os.getenv("NEO4J_USERNAME", "neo4j")
    neo4j_password = _get_env_var("NEO4J_PASSWORD", "Neo4jPassword", default="password123")

    MEM0_CONFIG["graph_store"] = {
        "provider": "neo4j",
        "config": {
            "url": neo4j_url,
            "username": neo4j_username,
            "password": neo4j_password,
        },
    }

# =============================================================================
# 对话 LLM 配置 (供 main.py、private_brain.ask 等使用)
# =============================================================================


def create_chat_llm(temperature: float | None = None):
    """
    根据 LLM_PROVIDER 创建 LLM 实例。

    Args:
        temperature: 温度参数（0.0-1.0）。若为 None，使用配置默认值（0.7）。
                     指代消解、隐私分类等需要确定性输出的场景建议传 0.0。

    Returns:
        LangChain ChatModel 实例（ChatOpenAI 或 ChatGoogleGenerativeAI）
    """
    from langchain_openai import ChatOpenAI

    cfg = get_chat_config()
    model = cfg["model"]
    temp = temperature if temperature is not None else cfg.get("temperature", 0.7)
    provider = cfg.get("provider", "openai")
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model,
            temperature=temp,
            google_api_key=GOOGLE_API_KEY or None,
        )
    return ChatOpenAI(
        model=model,
        temperature=temp,
        base_url=cfg.get("base_url") or DEEPSEEK_CONFIG["base_url"],
        api_key=DEEPSEEK_API_KEY or os.getenv("OPENAI_API_KEY"),
    )


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

# =============================================================================
# HTTP Server 配置
# =============================================================================

HTTP_SERVER_CONFIG = {
    "host": os.getenv("HTTP_HOST", "0.0.0.0"),
    "port": int(os.getenv("HTTP_PORT", "8765")),
    "cors_origins": ["*"],  # DIFY 等跨域调用，生产环境建议限制具体域名
}

# =============================================================================
# Session 管理配置
# =============================================================================

# Session 超时时间（秒），超过此时间无活动自动结束
# 可通过环境变量 SESSION_TIMEOUT 覆盖
SESSION_TIMEOUT_SECONDS = int(os.getenv("SESSION_TIMEOUT", 30 * 60))  # 默认 30 分钟

# Session 最大存活时间（秒），即使持续活跃也会强制结束
SESSION_MAX_DURATION_SECONDS = int(os.getenv("SESSION_MAX_DURATION", 24 * 60 * 60))  # 默认 24 小时

# 单个 Session 最大事件数，超过后自动结束并整合
SESSION_MAX_EVENTS = int(os.getenv("SESSION_MAX_EVENTS", 100))

# Session 超时检查间隔（秒）
SESSION_CHECK_INTERVAL_SECONDS = 60  # 每分钟检查一次

# =============================================================================
# 指代消解配置
# =============================================================================

# 检索时用于消解的最近事件数
COREFERENCE_CONTEXT_SIZE = int(os.getenv("COREFERENCE_CONTEXT_SIZE", 5))  # 默认最近 5 条
