"""
pytest 配置和共享 fixtures

提供测试目标服务器参数化支持：
- --target 参数：指定测试目标（local 或 zeabur）
- target_env fixture：根据参数自动设置环境变量
"""
import os
import pytest
import importlib


def pytest_addoption(parser):
    """添加 pytest 命令行参数"""
    parser.addoption(
        "--target",
        action="store",
        default="zeabur",
        choices=["local", "zeabur"],
        help="测试目标服务器: local (Docker Desktop) 或 zeabur (远程服务器)"
    )


@pytest.fixture(scope="session", autouse=True)
def target_env(request):
    """
    根据 --target 参数设置环境变量
    
    这个 fixture 会在所有测试开始前自动执行（autouse=True），
    根据 --target 参数设置相应的数据库连接环境变量。
    """
    target = request.config.getoption("--target")
    
    if target == "local":
        # 本地 Docker Desktop 配置
        os.environ["QDRANT_HOST"] = "localhost"
        os.environ["QDRANT_PORT"] = "6400"
        os.environ["NEO4J_NEUROMEMORY_HOST"] = "localhost"
        os.environ["NEO4J_BOLT_PORT"] = "17687"
        os.environ["NEO4J_PASSWORD"] = os.getenv("NEO4J_PASSWORD", "zeabur2025")
        # 清除可能存在的远程配置
        os.environ.pop("NEO4J_URL", None)
        os.environ.pop("QDRANT_NEUROMEMORY_HOST", None)
        
        print(f"\n[测试配置] 目标: {target} (本地 Docker Desktop)")
        print(f"  - QDRANT_HOST: localhost:6400")
        print(f"  - NEO4J: localhost:17687")
        
    elif target == "zeabur":
        # ZeaBur 远程配置
        # 先读取当前 config（在重新加载前）
        import config
        zeabur_config = config.ZEABUR_TEST_CONFIG
        
        # 优先使用环境变量，否则使用配置文件中的默认值
        zeabur_neo4j_host = os.getenv("ZEABUR_NEO4J_HOST") or zeabur_config.get("neo4j_host") or os.getenv("NEO4J_NEUROMEMORY_HOST")
        zeabur_qdrant_host = os.getenv("ZEABUR_QDRANT_HOST") or zeabur_config.get("qdrant_host") or os.getenv("QDRANT_NEUROMEMORY_HOST")
        
        # 设置环境变量
        if zeabur_neo4j_host:
            os.environ["NEO4J_NEUROMEMORY_HOST"] = zeabur_neo4j_host
        if zeabur_qdrant_host:
            os.environ["QDRANT_NEUROMEMORY_HOST"] = zeabur_qdrant_host
        
        # ZeaBur 密码（优先环境变量，否则使用配置中的默认值）
        os.environ["NEO4J_PASSWORD"] = os.getenv("NEO4J_PASSWORD") or os.getenv("Neo4jPassword") or zeabur_config.get("neo4j_password", "zeabur2025")
        
        print(f"\n[测试配置] 目标: {target} (ZeaBur 远程服务器)")
        if zeabur_neo4j_host:
            print(f"  - NEO4J: {zeabur_neo4j_host}")
        if zeabur_qdrant_host:
            print(f"  - QDRANT: {zeabur_qdrant_host}:{zeabur_config.get('qdrant_port', 6400)}")
    
    # 重新加载 config 模块以应用新环境变量
    # 注意：这会影响所有导入 config 的模块
    try:
        import config
        importlib.reload(config)
        print(f"[测试配置] config 模块已重新加载")
    except Exception as e:
        print(f"[测试配置] 警告: 重新加载 config 模块失败: {e}")
    
    yield target
    
    # 清理（可选，测试结束后恢复环境变量）
    # 注意：session scope 的 fixture 在测试结束后才会执行清理
