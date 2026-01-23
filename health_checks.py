"""
Health check helpers for Neo4j, Qdrant, and LLM configuration.

Used by /api/v1/health to populate components: {neo4j, qdrant, llm}。

check_llm_config 使用 os.getenv，依赖 .env 已加载。本模块的
`from config import ...` 会在导入时触发 config 的 load_dotenv；单独使用
check_llm_config 前需先 import config 或 import health_checks，以确保与 config 一致。
"""
import os

from config import MEM0_CONFIG, LLM_PROVIDER


def check_neo4j() -> bool:
    """
    检查 Neo4j 连接是否可用。

    若 MEM0_CONFIG 中未配置 graph_store（图谱禁用），返回 True（视为健康）。
    """
    gs = MEM0_CONFIG.get("graph_store") or {}
    cfg = gs.get("config") or {}
    if not cfg:
        return True  # 图谱禁用，视为健康
    try:
        from neo4j import GraphDatabase

        uri = cfg.get("url", "")
        user = cfg.get("username", "")
        pw = cfg.get("password", "")
        if not uri:
            return False
        driver = GraphDatabase.driver(uri, auth=(user, pw))
        driver.verify_connectivity()
        driver.close()
        return True
    except Exception:
        return False


def check_qdrant() -> bool:
    """
    检查 Qdrant 连接是否可用。
    """
    vs = MEM0_CONFIG.get("vector_store") or {}
    cfg = vs.get("config") or {}
    try:
        from qdrant_client import QdrantClient

        host = cfg.get("host", "localhost")
        port = int(cfg.get("port", 6400))
        client = QdrantClient(host=host, port=port)
        client.get_collections()
        return True
    except Exception:
        return False


def check_llm_config() -> bool:
    """
    检查当前 LLM 提供商所需的 API 密钥是否已配置。
    兼容 ZeaBur 驼峰命名（如 DeepSeekApiKey）。
    """
    if LLM_PROVIDER == "gemini":
        return bool((os.getenv("GOOGLE_API_KEY") or os.getenv("GoogleApiKey") or "").strip())
    if LLM_PROVIDER == "deepseek":
        return bool((os.getenv("DEEPSEEK_API_KEY") or os.getenv("DeepSeekApiKey") or os.getenv("OPENAI_API_KEY") or "").strip())
    if LLM_PROVIDER == "openai":
        return bool((os.getenv("OPENAI_API_KEY") or "").strip())
    return False
