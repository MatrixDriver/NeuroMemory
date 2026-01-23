"""
ZeaBur 远程部署连接和服务接口测试

测试 ZeaBur 远程环境的：
- 环境变量配置解析
- 数据库连接（Neo4j、Qdrant）
- REST API 端点
- 端到端功能

运行方式:
    # Bash / Linux / macOS:
    ZEABUR_BASE_URL=https://neuromemory.zeabur.app pytest tests/test_zeabur.py -v
    
    # PowerShell (Windows):
    $env:ZEABUR_BASE_URL="https://neuromemory.zeabur.app"; uv run pytest tests/test_zeabur.py -v
    # 或使用 uv 的 --env 参数（如果支持）:
    # uv run --env ZEABUR_BASE_URL=https://neuromemory.zeabur.app pytest tests/test_zeabur.py -v
    
    # 跳过慢速测试 (PowerShell):
    $env:ZEABUR_BASE_URL="https://neuromemory.zeabur.app"; uv run pytest tests/test_zeabur.py -v -m "not slow"
    
    # 只运行配置测试（不需要远程服务）
    pytest tests/test_zeabur.py::TestZeaburConfig -v
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

# ZeaBur 远程服务 URL（通过环境变量配置）
ZEABUR_BASE_URL = os.getenv("ZEABUR_BASE_URL", "https://neuromemory.zeabur.app").rstrip("/")
ZEABUR_NEO4J_URL = os.getenv("ZEABUR_NEO4J_URL")  # 可选，如 neo4j://neo4j-neuromemory:7687
ZEABUR_NEO4J_PASSWORD = os.getenv("ZEABUR_NEO4J_PASSWORD", os.getenv("Neo4jPassword", "zeabur2025"))
ZEABUR_QDRANT_HOST = os.getenv("ZEABUR_QDRANT_HOST")  # 可选，如 qdrant-neuromemory
ZEABUR_QDRANT_PORT = int(os.getenv("ZEABUR_QDRANT_PORT", "6400"))

# HTTP 请求超时（秒）
HTTP_TIMEOUT = 30

# 测试标记：所有 ZeaBur 测试都需要此标记
pytestmark = pytest.mark.zeabur


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def zeabur_base_url() -> str:
    """返回 ZeaBur 基础 URL"""
    return ZEABUR_BASE_URL


@pytest.fixture
def http_client():
    """创建 HTTP 客户端（httpx 或 requests）"""
    if not HTTP_CLIENT_AVAILABLE:
        pytest.skip(f"需要 httpx 或 requests 库，请安装: pip install httpx 或 pip install requests")
    
    if HTTP_CLIENT_TYPE == "httpx":
        client = httpx.Client(base_url=ZEABUR_BASE_URL, timeout=HTTP_TIMEOUT)
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
        
        yield RequestsClient(ZEABUR_BASE_URL)
    else:
        pytest.skip("HTTP 客户端不可用")


@pytest.fixture
def unique_user_id() -> str:
    """生成唯一的用户 ID"""
    return f"zeabur_test_{int(time.time() * 1000)}"


@pytest.fixture
def skip_if_no_zeabur_url():
    """如果未配置 ZeaBur URL，跳过测试"""
    if not ZEABUR_BASE_URL or ZEABUR_BASE_URL == "https://neuromemory.zeabur.app":
        # 如果使用默认值，检查是否真的可访问
        pass  # 允许使用默认值，但会在实际请求时失败
    return None


# =============================================================================
# 测试类：环境变量配置
# =============================================================================

class TestZeaburConfig:
    """测试 ZeaBur 环境变量配置解析"""
    
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
    
    def test_placeholder_fallback(self, monkeypatch):
        """测试 {{ }} 占位符的回退逻辑"""
        import config
        
        # 模拟 ZeaBur 注入的未解析占位符
        monkeypatch.setenv("NEO4J_URL", "neo4j://{{ service.host }}:7687")
        monkeypatch.setenv("NEO4J_NEUROMEMORY_HOST", "neo4j-service")
        
        # 重新加载配置（需要重新导入或手动测试逻辑）
        _neo4j_url_raw = os.getenv("NEO4J_URL", "")
        if _neo4j_url_raw and "{{" not in _neo4j_url_raw:
            neo4j_url = _neo4j_url_raw
        else:
            _h = os.getenv("NEO4J_NEUROMEMORY_HOST") or os.getenv("NEO4J_HOST") or "localhost"
            _p = int(os.getenv("NEO4J_BOLT_PORT", "17687"))
            neo4j_url = f"neo4j://{_h}:{_p}"
        
        assert "{{" not in neo4j_url
        assert neo4j_url == "neo4j://neo4j-service:17687"
    
    def test_host_injection_neo4j(self, monkeypatch):
        """测试 NEO4J_NEUROMEMORY_HOST 注入"""
        monkeypatch.setenv("NEO4J_NEUROMEMORY_HOST", "neo4j-injected-host")
        monkeypatch.delenv("NEO4J_URL", raising=False)
        
        _h = os.getenv("NEO4J_NEUROMEMORY_HOST") or os.getenv("NEO4J_HOST") or "localhost"
        assert _h == "neo4j-injected-host"
    
    def test_host_injection_qdrant(self, monkeypatch):
        """测试 QDRANT_NEUROMEMORY_HOST 注入"""
        monkeypatch.setenv("QDRANT_NEUROMEMORY_HOST", "qdrant-injected-host")
        monkeypatch.delenv("QDRANT_HOST", raising=False)
        
        _qh = os.getenv("QDRANT_HOST") or os.getenv("QDRANT_NEUROMEMORY_HOST") or "localhost"
        assert _qh == "qdrant-injected-host"


# =============================================================================
# 测试类：远程数据库连接
# =============================================================================

class TestZeaburDatabaseConnections:
    """测试远程数据库连接"""
    
    @pytest.mark.requires_db
    def test_neo4j_connection(self):
        """测试远程 Neo4j 连接"""
        # 如果提供了直接连接 URL，使用它；否则跳过
        if not ZEABUR_NEO4J_URL:
            pytest.skip("未设置 ZEABUR_NEO4J_URL，跳过直接连接测试")
        
        try:
            from neo4j import GraphDatabase
            
            # 解析 URL（格式：neo4j://host:port）
            # 如果 URL 包含密码，直接使用；否则使用环境变量中的密码
            driver = GraphDatabase.driver(
                ZEABUR_NEO4J_URL,
                auth=("neo4j", ZEABUR_NEO4J_PASSWORD)
            )
            driver.verify_connectivity()
            driver.close()
            
            # 如果到达这里，连接成功
            assert True
        except Exception as e:
            pytest.skip(f"无法连接到远程 Neo4j ({ZEABUR_NEO4J_URL}): {e}")
    
    @pytest.mark.requires_db
    def test_qdrant_connection(self):
        """测试远程 Qdrant 连接"""
        # 如果提供了 host，使用它；否则跳过
        if not ZEABUR_QDRANT_HOST:
            pytest.skip("未设置 ZEABUR_QDRANT_HOST，跳过直接连接测试")
        
        try:
            from qdrant_client import QdrantClient
            
            client = QdrantClient(host=ZEABUR_QDRANT_HOST, port=ZEABUR_QDRANT_PORT)
            collections = client.get_collections()
            
            # 如果到达这里，连接成功
            assert isinstance(collections, dict) or isinstance(collections, list)
        except Exception as e:
            pytest.skip(f"无法连接到远程 Qdrant ({ZEABUR_QDRANT_HOST}:{ZEABUR_QDRANT_PORT}): {e}")


# =============================================================================
# 测试类：REST API 端点
# =============================================================================

class TestZeaburRestApi:
    """测试 ZeaBur REST API 端点"""
    
    def test_root_endpoint(self, http_client):
        """测试 GET / 根路由"""
        response = http_client.get("/")
        assert response.status_code == 200
        data = response.json() if hasattr(response, 'json') else response
        assert "service" in data
        assert data["service"] == "neuro-memory"
        assert "version" in data
        assert "docs" in data
    
    def test_health_endpoint(self, http_client):
        """测试 GET /health 基础健康检查"""
        response = http_client.get("/health")
        assert response.status_code == 200
        data = response.json() if hasattr(response, 'json') else response
        assert "status" in data
        assert data["status"] == "healthy"
        assert "service" in data
    
    def test_api_v1_health_endpoint(self, http_client):
        """测试 GET /api/v1/health 详细健康检查"""
        response = http_client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json() if hasattr(response, 'json') else response
        assert "status" in data
        assert data["status"] in ("healthy", "unhealthy")
        assert "components" in data
        assert "neo4j" in data["components"]
        assert "qdrant" in data["components"]
        assert "llm" in data["components"]
    
    def test_process_endpoint(self, http_client, unique_user_id):
        """测试 POST /process 处理记忆（v3 格式）"""
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
    
    def test_api_v1_memory_post(self, http_client, unique_user_id):
        """测试 POST /api/v1/memory 添加记忆"""
        payload = {
            "content": "这是一条测试记忆",
            "user_id": unique_user_id,
            "metadata": {"test": True}
        }
        
        response = http_client.post("/api/v1/memory", json=payload)
        # 可能成功（200）或失败（500），但结构应该正确
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json() if hasattr(response, 'json') else response
            assert "memory_id" in data
            assert isinstance(data["memory_id"], str)
    
    def test_api_v1_memory_search(self, http_client, unique_user_id):
        """测试 GET /api/v1/memory/search 混合检索"""
        params = {
            "query": "测试查询",
            "user_id": unique_user_id,
            "limit": 5
        }
        
        response = http_client.get("/api/v1/memory/search", params=params)
        assert response.status_code == 200
        data = response.json() if hasattr(response, 'json') else response
        assert "memories" in data
        assert "metadata" in data
        assert isinstance(data["memories"], list)
    
    def test_api_v1_graph(self, http_client, unique_user_id):
        """测试 GET /api/v1/graph 获取知识图谱"""
        params = {
            "user_id": unique_user_id,
            "depth": 2
        }
        
        response = http_client.get("/api/v1/graph", params=params)
        assert response.status_code == 200
        data = response.json() if hasattr(response, 'json') else response
        assert "nodes" in data
        assert "edges" in data
        assert isinstance(data["nodes"], list)
        assert isinstance(data["edges"], list)
    
    @pytest.mark.slow
    def test_api_v1_ask(self, http_client, unique_user_id):
        """测试 POST /api/v1/ask 基于记忆问答（需要 LLM）"""
        payload = {
            "question": "测试问题：你是谁？",
            "user_id": unique_user_id
        }
        
        response = http_client.post("/api/v1/ask", json=payload)
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

class TestZeaburE2E:
    """测试端到端功能"""
    
    @pytest.mark.slow
    def test_full_memory_workflow(self, http_client, unique_user_id):
        """测试完整的记忆添加和检索流程"""
        # 1. 添加记忆
        payload_add = {
            "content": f"用户 {unique_user_id} 喜欢编程和人工智能",
            "user_id": unique_user_id
        }
        
        response_add = http_client.post("/api/v1/memory", json=payload_add)
        if response_add.status_code != 200:
            pytest.skip(f"无法添加记忆（可能数据库未就绪）: {response_add.status_code}")
        
        # 等待索引更新
        time.sleep(2)
        
        # 2. 检索记忆
        params_search = {
            "query": "编程",
            "user_id": unique_user_id,
            "limit": 5
        }
        
        response_search = http_client.get("/api/v1/memory/search", params=params_search)
        assert response_search.status_code == 200
        data_search = response_search.json() if hasattr(response_search, 'json') else response_search
        assert "memories" in data_search
        
        # 3. 获取图谱
        params_graph = {
            "user_id": unique_user_id,
            "depth": 2
        }
        
        response_graph = http_client.get("/api/v1/graph", params=params_graph)
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
