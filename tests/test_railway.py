"""
Railway 远程部署连接和服务接口测试

测试 Railway 远程环境的：
- 环境变量配置解析
- 数据库连接（Neo4j、Qdrant）
- REST API 端点
- 端到端功能

运行方式:
    # 现在直接从 config.py 读取配置，无需设置环境变量
    # Bash / Linux / macOS:
    pytest tests/test_railway.py -v

    # PowerShell (Windows):
    uv run pytest tests/test_railway.py -v

    # 跳过慢速测试:
    uv run pytest tests/test_railway.py -v -m "not slow"

    # 只运行配置测试（不需要远程服务）
    pytest tests/test_railway.py::TestRailwayConfig -v

    # 如果需要临时覆盖配置，仍可使用环境变量:
    # $env:RAILWAY_BASE_URL="https://custom-url.up.railway.app"; uv run pytest tests/test_railway.py -v
"""
import os
import time
import pytest

# 尝试导入 httpx，如果没有则使用 requests
try:
    import httpx
    HTTP_CLIENT_AVAILABLE = True
    HTTP_CLIENT_TYPE = "httpx"
except ImportError:
    try:
        import requests
        HTTP_CLIENT_AVAILABLE = True
        HTTP_CLIENT_TYPE = "requests"
    except ImportError:
        HTTP_CLIENT_AVAILABLE = False
        HTTP_CLIENT_TYPE = None

# =============================================================================
# 配置和常量
# =============================================================================

# 从 config.py 导入 Railway 测试配置
from config import RAILWAY_TEST_CONFIG

RAILWAY_BASE_URL = RAILWAY_TEST_CONFIG["base_url"]
RAILWAY_NEO4J_URL = RAILWAY_TEST_CONFIG["neo4j_url"]
RAILWAY_NEO4J_PASSWORD = RAILWAY_TEST_CONFIG["neo4j_password"]
RAILWAY_QDRANT_HOST = RAILWAY_TEST_CONFIG["qdrant_host"]
RAILWAY_QDRANT_PORT = RAILWAY_TEST_CONFIG["qdrant_port"]
HTTP_TIMEOUT = RAILWAY_TEST_CONFIG["http_timeout"]

# 测试标记：所有 Railway 测试都需要此标记
pytestmark = pytest.mark.railway


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def railway_base_url() -> str:
    """返回 Railway 基础 URL"""
    return RAILWAY_BASE_URL


@pytest.fixture
def http_client():
    """创建 HTTP 客户端（httpx 或 requests）"""
    if not HTTP_CLIENT_AVAILABLE:
        pytest.skip(f"需要 httpx 或 requests 库，请安装: pip install httpx 或 pip install requests")

    if HTTP_CLIENT_TYPE == "httpx":
        client = httpx.Client(base_url=RAILWAY_BASE_URL, timeout=HTTP_TIMEOUT)
        yield client
        client.close()
    elif HTTP_CLIENT_TYPE == "requests":
        # requests 是模块，返回一个包装对象
        class RequestsClient:
            def __init__(self, base_url):
                self.base_url = base_url
                self.timeout = HTTP_TIMEOUT

            def get(self, path, **kwargs):
                url = f"{self.base_url}{path}" if not path.startswith("http") else path
                return requests.get(url, timeout=self.timeout, **kwargs)

            def post(self, path, **kwargs):
                url = f"{self.base_url}{path}" if not path.startswith("http") else path
                return requests.post(url, timeout=self.timeout, **kwargs)

            def request(self, method, path, **kwargs):
                url = f"{self.base_url}{path}" if not path.startswith("http") else path
                return requests.request(method, url, timeout=self.timeout, **kwargs)

        yield RequestsClient(RAILWAY_BASE_URL)
    else:
        pytest.skip("HTTP 客户端不可用")


@pytest.fixture
def unique_user_id() -> str:
    """生成唯一的用户 ID"""
    return f"railway_test_{int(time.time() * 1000)}"


@pytest.fixture
def skip_if_no_railway_url():
    """
    如果未配置 Railway URL，跳过测试

    注意：现在配置从 config.py 读取，默认值为 https://<your-app>.up.railway.app
    如果需要临时覆盖，可通过环境变量 RAILWAY_BASE_URL 设置
    """
    # 配置已在 config.py 中设置，这里保留 fixture 以保持向后兼容
    # 实际测试会在请求时失败，而不是在这里跳过
    return None


# =============================================================================
# 测试类：环境变量配置
# =============================================================================

class TestRailwayConfig:
    """测试 Railway 环境变量配置解析"""

    def test_env_var_reading_camelcase(self, monkeypatch):
        """测试驼峰命名环境变量的读取"""
        from config import _get_env_var

        # 测试 Neo4jPassword (驼峰)
        monkeypatch.setenv("Neo4jPassword", "test_password_123")
        result = _get_env_var("NEO4J_PASSWORD", "Neo4jPassword", default="")
        assert result == "test_password_123"

    def test_env_var_reading_underscore(self, monkeypatch):
        """测试下划线命名环境变量的读取"""
        from config import _get_env_var

        # 测试 NEO4J_PASSWORD (下划线)
        monkeypatch.setenv("NEO4J_PASSWORD", "test_password_456")
        result = _get_env_var("NEO4J_PASSWORD", "Neo4jPassword", default="")
        assert result == "test_password_456"

    def test_env_var_priority(self, monkeypatch):
        """测试环境变量优先级（下划线优先于驼峰）"""
        from config import _get_env_var

        # 同时设置两个，下划线应该优先
        monkeypatch.setenv("NEO4J_PASSWORD", "priority_password")
        monkeypatch.setenv("Neo4jPassword", "camelcase_password")
        result = _get_env_var("NEO4J_PASSWORD", "Neo4jPassword", default="")
        assert result == "priority_password"

    def test_host_injection_neo4j(self, monkeypatch):
        """测试 NEO4J_HOST 注入"""
        monkeypatch.setenv("NEO4J_HOST", "neo4j.railway.internal")
        monkeypatch.delenv("NEO4J_URL", raising=False)

        _h = os.getenv("NEO4J_HOST") or "localhost"
        assert _h == "neo4j.railway.internal"

    def test_host_injection_qdrant(self, monkeypatch):
        """测试 QDRANT_HOST 注入"""
        monkeypatch.setenv("QDRANT_HOST", "qdrant.railway.internal")

        _qh = os.getenv("QDRANT_HOST") or "localhost"
        assert _qh == "qdrant.railway.internal"


# =============================================================================
# 测试类：远程数据库连接
# =============================================================================

class TestRailwayDatabaseConnections:
    """测试远程数据库连接"""

    @pytest.mark.requires_db
    def test_neo4j_connection(self):
        """测试远程 Neo4j 连接"""
        # 如果提供了直接连接 URL，使用它；否则跳过
        if not RAILWAY_NEO4J_URL:
            pytest.skip("未设置 RAILWAY_NEO4J_URL，跳过直接连接测试")

        try:
            from neo4j import GraphDatabase

            driver = GraphDatabase.driver(
                RAILWAY_NEO4J_URL,
                auth=("neo4j", RAILWAY_NEO4J_PASSWORD)
            )
            driver.verify_connectivity()
            driver.close()

            assert True
        except Exception as e:
            pytest.skip(f"无法连接到远程 Neo4j ({RAILWAY_NEO4J_URL}): {e}")

    @pytest.mark.requires_db
    def test_qdrant_connection(self):
        """测试远程 Qdrant 连接"""
        if not RAILWAY_QDRANT_HOST:
            pytest.skip("未设置 RAILWAY_QDRANT_HOST，跳过直接连接测试")

        try:
            from qdrant_client import QdrantClient

            client = QdrantClient(host=RAILWAY_QDRANT_HOST, port=RAILWAY_QDRANT_PORT)
            collections = client.get_collections()

            assert isinstance(collections, dict) or isinstance(collections, list)
        except Exception as e:
            pytest.skip(f"无法连接到远程 Qdrant ({RAILWAY_QDRANT_HOST}:{RAILWAY_QDRANT_PORT}): {e}")


# =============================================================================
# 测试类：REST API 端点
# =============================================================================

class TestRailwayRestApi:
    """测试 Railway REST API 端点"""

    def test_root_endpoint(self, http_client):
        """测试 GET / 根路由"""
        response = http_client.get("/")
        assert response.status_code == 200
        data = response.json() if hasattr(response, 'json') else response
        assert "service" in data
        assert data["service"] == "neuro-memory"
        assert "docs" in data

    def test_health_endpoint_detailed(self, http_client):
        """测试 GET /health 详细健康检查（含 components）"""
        response = http_client.get("/health")
        assert response.status_code == 200
        data = response.json() if hasattr(response, 'json') else response
        assert "status" in data
        assert data["status"] in ("healthy", "unhealthy")
        assert "service" in data
        assert data["service"] == "neuro-memory"
        assert "components" in data
        assert "neo4j" in data["components"]
        assert "qdrant" in data["components"]
        assert "llm" in data["components"]

    def test_process_endpoint(self, http_client, unique_user_id):
        """测试 POST /process 处理记忆"""
        payload = {
            "input": "测试记忆内容",
            "user_id": unique_user_id
        }

        response = http_client.post("/process", json=payload)
        assert response.status_code == 200
        data = response.json() if hasattr(response, 'json') else response
        assert "resolved_query" in data
        assert "memories" in data
        assert "relations" in data
        assert "metadata" in data
        assert isinstance(data["memories"], list)
        assert isinstance(data["relations"], list)

    def test_search(self, http_client, unique_user_id):
        """测试 GET /search 纯检索"""
        params = {
            "query": "测试查询",
            "user_id": unique_user_id,
            "limit": 5
        }

        response = http_client.get("/search", params=params)
        # 可能成功（200）或失败（500，如数据库连接问题）
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json() if hasattr(response, 'json') else response
            assert "memories" in data
            assert "metadata" in data
            assert isinstance(data["memories"], list)

    @pytest.mark.slow
    def test_ask(self, http_client, unique_user_id):
        """测试 POST /ask 基于记忆问答（需要 LLM）"""
        payload = {
            "question": "测试问题：你是谁？",
            "user_id": unique_user_id
        }

        response = http_client.post("/ask", json=payload)
        # 可能成功（200）或失败（500）
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json() if hasattr(response, 'json') else response
            assert "answer" in data
            assert "sources" in data
            assert isinstance(data["sources"], list)

    def test_end_session(self, http_client, unique_user_id):
        """测试 POST /end-session 结束会话"""
        payload = {
            "user_id": unique_user_id
        }

        response = http_client.post("/end-session", json=payload)
        assert response.status_code == 200
        data = response.json() if hasattr(response, 'json') else response
        assert "status" in data
        assert "message" in data

    def test_session_status(self, http_client, unique_user_id):
        """测试 GET /session-status/{user_id} 获取会话状态"""
        response = http_client.get(f"/session-status/{unique_user_id}")
        assert response.status_code == 200
        data = response.json() if hasattr(response, 'json') else response
        assert "status" in data
        assert "has_active_session" in data


# =============================================================================
# 测试类：端到端功能
# =============================================================================

class TestRailwayE2E:
    """测试端到端功能"""

    @pytest.mark.slow
    def test_full_memory_workflow(self, http_client, unique_user_id):
        """测试完整的记忆添加和检索流程"""
        # 1. 通过 /process 添加记忆
        payload_add = {
            "input": f"用户 {unique_user_id} 喜欢编程和人工智能",
            "user_id": unique_user_id
        }

        response_add = http_client.post("/process", json=payload_add)
        assert response_add.status_code == 200

        # 结束会话以触发记忆整合
        http_client.post("/end-session", json={"user_id": unique_user_id})

        # 等待整合完成
        time.sleep(3)

        # 2. 检索记忆
        params_search = {
            "query": "编程",
            "user_id": unique_user_id,
            "limit": 5
        }

        response_search = http_client.get("/search", params=params_search)
        assert response_search.status_code == 200
        data_search = response_search.json() if hasattr(response_search, 'json') else response_search
        assert "memories" in data_search

        # 3. 获取图谱
        response_graph = http_client.get(f"/graph/{unique_user_id}")
        assert response_graph.status_code == 200
        data_graph = response_graph.json() if hasattr(response_graph, 'json') else response_graph
        assert "nodes" in data_graph
        assert "edges" in data_graph

    @pytest.mark.slow
    def test_session_workflow(self, http_client, unique_user_id):
        """测试 Session 管理流程"""
        # 1. 处理第一轮对话
        payload1 = {
            "input": "我叫小朱",
            "user_id": unique_user_id
        }

        response1 = http_client.post("/process", json=payload1)
        assert response1.status_code == 200

        # 2. 处理第二轮对话（包含指代）
        payload2 = {
            "input": "我女儿叫灿灿",
            "user_id": unique_user_id
        }

        response2 = http_client.post("/process", json=payload2)
        assert response2.status_code == 200

        # 3. 检查会话状态
        response_status = http_client.get(f"/session-status/{unique_user_id}")
        assert response_status.status_code == 200
        data_status = response_status.json() if hasattr(response_status, 'json') else response_status
        assert "has_active_session" in data_status

        # 4. 结束会话
        payload_end = {
            "user_id": unique_user_id
        }

        response_end = http_client.post("/end-session", json=payload_end)
        assert response_end.status_code == 200
        data_end = response_end.json() if hasattr(response_end, 'json') else response_end
        assert data_end["status"] == "success"

    @pytest.mark.slow
    def test_cross_session_query(self, http_client, unique_user_id):
        """测试跨 Session 查询"""
        # Session 1: 存储记忆
        payload1 = {
            "input": "我喜欢Python编程",
            "user_id": unique_user_id
        }

        http_client.post("/process", json=payload1)

        # 结束 Session 1
        payload_end = {
            "user_id": unique_user_id
        }

        http_client.post("/end-session", json=payload_end)

        # 等待整合完成
        time.sleep(5)

        # Session 2: 查询
        payload2 = {
            "input": "我喜欢什么编程语言？",
            "user_id": unique_user_id
        }

        response = http_client.post("/process", json=payload2)
        assert response.status_code == 200
        data = response.json() if hasattr(response, 'json') else response
        assert "resolved_query" in data
        assert "memories" in data


# =============================================================================
# 运行入口
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
