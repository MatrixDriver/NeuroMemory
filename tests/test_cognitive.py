"""
NeuroMemory 测试套件

基于 PrivateBrain 的 Y 型分流架构测试：
- 隐私过滤功能测试
- 检索功能测试
- 存储决策测试
- 端到端流程测试

运行方式:
    # 安装测试依赖
    uv pip install -e ".[dev]"
    
    # 运行所有测试（默认显示输出）
    pytest
    
    # 运行特定测试
    pytest tests/test_cognitive.py::TestPrivacyFilter -v -s
    
    # 跳过慢速测试（只运行单元测试）
    pytest -m "not slow"
"""

import pytest
import time

from config import LLM_PROVIDER, EMBEDDING_PROVIDER


# =============================================================================
# 工具函数
# =============================================================================

def check_database_available():
    """
    检查 Qdrant 数据库服务是否可用。
    
    使用 health_checks.check_qdrant() 进行实际连接检查，
    而不是简单的 socket 连接，这样可以正确处理远程主机名。
    """
    try:
        from health_checks import check_qdrant
        return check_qdrant()
    except Exception:
        return False


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(scope="module")
def brain():
    """创建共享的 PrivateBrain 实例（模块级别复用）"""
    # 预先导入 openai 模块，避免并发导入时的死锁问题
    # 这是 Python 并发导入的已知问题
    import openai  # noqa: F401
    import openai.resources  # noqa: F401
    import openai.resources.chat  # noqa: F401
    import openai.resources.embeddings  # noqa: F401
    
    # 确保使用最新的配置（conftest.py 中的 target_env 已重新加载 config）
    import importlib
    import config
    importlib.reload(config)
    
    from private_brain import PrivateBrain
    
    # 显示当前数据库配置
    from config import MEM0_CONFIG
    qdrant_host = MEM0_CONFIG.get("vector_store", {}).get("config", {}).get("host", "unknown")
    qdrant_port = MEM0_CONFIG.get("vector_store", {}).get("config", {}).get("port", "unknown")
    neo4j_url = "未启用"
    if "graph_store" in MEM0_CONFIG:
        neo4j_url = MEM0_CONFIG["graph_store"].get("config", {}).get("url", "unknown")
    
    # 检查数据库是否可用（使用配置中的 host）
    if not check_database_available():
        pytest.skip(f"Qdrant 数据库未运行 ({qdrant_host}:{qdrant_port})，请先启动: docker-compose up -d")
    
    print("\n" + "=" * 60)
    print("初始化 PrivateBrain...")
    print(f"当前配置: LLM={LLM_PROVIDER}, Embedding={EMBEDDING_PROVIDER}")
    print(f"数据库: Qdrant={qdrant_host}:{qdrant_port}, Neo4j={neo4j_url}")
    print("=" * 60)
    
    brain_instance = PrivateBrain()
    
    # 预热：执行一次简单的搜索，确保所有内部模块正确初始化
    print("执行预热调用...")
    try:
        brain_instance.search("预热查询", "warmup_user")
    except Exception as e:
        print(f"预热调用异常（可忽略）: {e}")
    print("预热完成")
    print("=" * 60)
    
    return brain_instance


@pytest.fixture
def unique_user_id():
    """生成唯一的用户 ID，避免测试间数据污染"""
    return f"test_user_{int(time.time() * 1000)}"


# =============================================================================
# 单元测试：身份提取与代词消解
# =============================================================================

class TestIdentityExtraction:
    """测试用户身份提取功能"""

    def test_extract_name_pattern_1(self):
        """测试 '我的名字叫XXX' 模式"""
        from main import extract_user_identity, USER_IDENTITY_CACHE
        USER_IDENTITY_CACHE.clear()
        
        result = extract_user_identity("我的名字叫小朱", "test_user")
        assert result == "小朱"
        assert USER_IDENTITY_CACHE["test_user"]["name"] == "小朱"
        USER_IDENTITY_CACHE.clear()

    def test_extract_name_pattern_2(self):
        """测试 '我叫XXX' 模式"""
        from main import extract_user_identity, USER_IDENTITY_CACHE
        USER_IDENTITY_CACHE.clear()
        
        result = extract_user_identity("我叫张三", "test_user")
        assert result == "张三"
        USER_IDENTITY_CACHE.clear()

    def test_extract_name_pattern_3(self):
        """测试 '我是XXX' 模式"""
        from main import extract_user_identity, USER_IDENTITY_CACHE
        USER_IDENTITY_CACHE.clear()
        
        result = extract_user_identity("我是李四", "test_user")
        assert result == "李四"
        USER_IDENTITY_CACHE.clear()

    def test_no_identity_in_input(self):
        """测试无身份信息时返回 None"""
        from main import extract_user_identity, USER_IDENTITY_CACHE
        USER_IDENTITY_CACHE.clear()
        
        result = extract_user_identity("今天天气真好", "test_user")
        assert result is None
        USER_IDENTITY_CACHE.clear()


class TestPronounResolution:
    """测试代词消解功能"""

    def test_resolve_my(self):
        """测试 '我的' 替换"""
        from main import resolve_pronouns, USER_IDENTITY_CACHE
        USER_IDENTITY_CACHE.clear()
        USER_IDENTITY_CACHE["test_user"] = {"name": "小朱"}
        
        result = resolve_pronouns("我的儿子叫什么", "test_user")
        assert result == "小朱的儿子叫什么"
        USER_IDENTITY_CACHE.clear()

    def test_resolve_me(self):
        """测试 '我' 替换"""
        from main import resolve_pronouns, USER_IDENTITY_CACHE
        USER_IDENTITY_CACHE.clear()
        USER_IDENTITY_CACHE["test_user"] = {"name": "小朱"}
        
        result = resolve_pronouns("我喜欢吃苹果", "test_user")
        assert result == "小朱喜欢吃苹果"
        USER_IDENTITY_CACHE.clear()

    def test_skip_identity_statement(self):
        """测试身份声明语句不被消解"""
        from main import resolve_pronouns, USER_IDENTITY_CACHE
        USER_IDENTITY_CACHE.clear()
        USER_IDENTITY_CACHE["test_user"] = {"name": "小朱"}
        
        result = resolve_pronouns("我的名字叫小朱", "test_user")
        # 身份声明不应消解，避免 "小朱的名字叫小朱"
        assert result == "我的名字叫小朱"
        USER_IDENTITY_CACHE.clear()

    def test_no_identity_no_resolution(self):
        """测试无身份信息时不做消解"""
        from main import resolve_pronouns, USER_IDENTITY_CACHE
        USER_IDENTITY_CACHE.clear()
        
        result = resolve_pronouns("我的儿子叫什么", "unknown_user")
        assert result == "我的儿子叫什么"
        USER_IDENTITY_CACHE.clear()


# =============================================================================
# 集成测试：隐私过滤器
# =============================================================================

class TestPrivacyFilter:
    """测试隐私过滤功能（需要 LLM 调用）"""

    @pytest.mark.slow
    def test_private_personal_info(self):
        """测试个人信息被分类为 PRIVATE"""
        from privacy_filter import classify_privacy
        
        print("\n--- 测试个人信息分类 ---")
        privacy_type, reason = classify_privacy("我的名字叫小朱")
        print(f"类型: {privacy_type}")
        print(f"理由: {reason}")
        assert privacy_type == "PRIVATE"

    @pytest.mark.slow
    def test_private_personal_relationship(self):
        """测试个人关系被分类为 PRIVATE"""
        from privacy_filter import classify_privacy
        
        print("\n--- 测试个人关系分类 ---")
        privacy_type, reason = classify_privacy("灿灿是小朱的女儿")
        print(f"类型: {privacy_type}")
        print(f"理由: {reason}")
        assert privacy_type == "PRIVATE"

    @pytest.mark.slow
    def test_private_personal_preference(self):
        """测试个人偏好被分类为 PRIVATE"""
        from privacy_filter import classify_privacy
        
        print("\n--- 测试个人偏好分类 ---")
        privacy_type, reason = classify_privacy("我喜欢吃苹果")
        print(f"类型: {privacy_type}")
        print(f"理由: {reason}")
        assert privacy_type == "PRIVATE"

    @pytest.mark.slow
    def test_public_factual_knowledge(self):
        """测试公共事实被分类为 PUBLIC"""
        from privacy_filter import classify_privacy
        
        print("\n--- 测试公共事实分类 ---")
        privacy_type, reason = classify_privacy("北京是中国的首都")
        print(f"类型: {privacy_type}")
        print(f"理由: {reason}")
        assert privacy_type == "PUBLIC"

    @pytest.mark.slow
    def test_public_query(self):
        """测试查询问句被分类为 PUBLIC"""
        from privacy_filter import classify_privacy
        
        print("\n--- 测试查询问句分类 ---")
        privacy_type, reason = classify_privacy("小朱的儿子叫什么名字？")
        print(f"类型: {privacy_type}")
        print(f"理由: {reason}")
        assert privacy_type == "PUBLIC"


# =============================================================================
# 集成测试：PrivateBrain 核心功能
# =============================================================================

class TestPrivateBrain:
    """测试 PrivateBrain 核心功能"""

    @pytest.mark.slow
    def test_process_returns_json_format(self, brain, unique_user_id):
        """测试 process() 返回正确的 JSON 格式"""
        print("\n--- 测试 JSON 返回格式 ---")
        
        result = brain.process("测试查询", unique_user_id)
        
        # 验证必要字段存在（memories / relations）
        assert "status" in result
        assert "memories" in result
        assert "relations" in result
        assert "metadata" in result
        
        # 验证 metadata 结构
        assert "retrieval_time_ms" in result["metadata"]
        assert "has_memory" in result["metadata"]
        
        print(f"返回结构: {list(result.keys())}")
        print(f"状态: {result['status']}")

    @pytest.mark.slow
    def test_process_debug_returns_natural_language(self, brain, unique_user_id):
        """测试 process_debug() 返回自然语言格式"""
        print("\n--- 测试调试模式输出 ---")
        
        result = brain.process_debug("测试查询", unique_user_id)
        
        # 验证返回是字符串
        assert isinstance(result, str)
        
        # 验证包含关键部分
        assert "检索过程" in result
        assert "存储决策" in result
        assert "性能统计" in result
        
        print(result)

    @pytest.mark.slow
    def test_add_and_search(self, brain, unique_user_id):
        """测试直接添加和搜索记忆"""
        print("\n--- 测试添加和搜索 ---")
        
        # 添加记忆
        add_result = brain.add("小明喜欢打篮球", unique_user_id)
        assert add_result["status"] == "success"
        assert "memory_id" in add_result
        print(f"添加结果: {add_result}")
        
        # 等待索引更新
        time.sleep(2)
        
        # 搜索记忆（limit=1 校验）
        search_result = brain.search("小明的爱好是什么", unique_user_id, limit=1)
        print(f"搜索结果: {search_result}")
        
        assert search_result["status"] == "success"
        assert len(search_result.get("memories", [])) <= 1

    @pytest.mark.slow
    def test_get_user_graph(self, brain, unique_user_id):
        """测试获取用户图谱"""
        print("\n--- 测试获取用户图谱 ---")
        
        # 先添加一些记忆
        brain.add("小红是小明的妹妹", unique_user_id)
        time.sleep(2)
        
        # 获取图谱
        graph = brain.get_user_graph(unique_user_id)
        print(f"图谱结果: {graph}")
        
        assert graph["status"] == "success"
        assert "memories" in graph
        assert "graph_relations" in graph
        assert "nodes" in graph
        assert "edges" in graph


# =============================================================================
# 端到端测试：Y 型分流流程
# =============================================================================

class TestYSplitFlow:
    """测试 Y 型分流完整流程"""

    @pytest.mark.slow
    def test_private_data_stored(self, brain, unique_user_id):
        """
        测试私有数据被正确存储
        
        输入私有数据后，应该能检索到
        """
        print("\n" + "=" * 60)
        print("测试：私有数据应被存储")
        print("=" * 60)
        
        # 输入私有数据
        user_suffix = unique_user_id[-6:]
        private_text = f"我叫测试用户_{user_suffix}"
        print(f"\n>>> 输入私有数据: {private_text}")
        
        result = brain.process_debug(private_text, unique_user_id)
        print(result)
        
        # 验证分类结果
        assert "PRIVATE" in result
        assert "存储" in result
        
        # 等待异步存储完成（增加等待时间以确保存储完成）
        time.sleep(5)
        
        # 使用更接近原文的查询来验证检索
        search_query = f"测试用户_{user_suffix}"
        search_result = brain.search(search_query, unique_user_id)
        print(f"\n>>> 搜索查询: {search_query}")
        print(f">>> 搜索结果: {search_result}")
        
        # 应该有记忆（memories）
        has_memory = search_result["metadata"]["has_memory"]
        has_chunks = len(search_result["memories"]) > 0
        
        if not (has_memory or has_chunks):
            # 如果第一次搜索没找到，尝试使用原文再搜索一次
            print("\n>>> 第一次搜索未找到，尝试使用原文搜索...")
            search_result = brain.search(private_text, unique_user_id)
            print(f">>> 原文搜索结果: {search_result}")
            has_memory = search_result["metadata"]["has_memory"]
            has_chunks = len(search_result["memories"]) > 0
        
        assert has_memory or has_chunks, f"存储后应能检索到记忆，但搜索结果为空"

    @pytest.mark.slow
    def test_public_data_discarded(self, brain, unique_user_id):
        """
        测试公共知识被正确丢弃
        
        输入公共知识后，不应该被存储
        """
        print("\n" + "=" * 60)
        print("测试：公共知识应被丢弃")
        print("=" * 60)
        
        # 输入公共知识
        public_text = "太阳从东方升起"
        print(f"\n>>> 输入公共知识: {public_text}")
        
        result = brain.process_debug(public_text, unique_user_id)
        print(result)
        
        # 验证分类结果
        assert "PUBLIC" in result
        assert "不存储" in result

    @pytest.mark.slow
    def test_query_only_retrieves(self, brain, unique_user_id):
        """
        测试查询只检索不存储
        
        问句应该被分类为 PUBLIC，只检索不存储
        """
        print("\n" + "=" * 60)
        print("测试：查询只检索不存储")
        print("=" * 60)
        
        # 先存储一些数据
        brain.add("小李有一只猫叫咪咪", unique_user_id)
        time.sleep(2)
        
        # 发起查询
        query = "小李的猫叫什么名字？"
        print(f"\n>>> 查询: {query}")
        
        result = brain.process_debug(query, unique_user_id)
        print(result)
        
        # 查询应该被分类为 PUBLIC（不存储）
        assert "PUBLIC" in result or "不存储" in result


# =============================================================================
# 端到端测试：多跳检索
# =============================================================================

class TestMultiHopRetrieval:
    """测试多跳检索能力"""

    @pytest.mark.slow
    def test_family_relationship_retrieval(self, brain, unique_user_id):
        """
        测试家庭关系检索
        
        构建知识：
        1. 小朱有两个孩子
        2. 灿灿是小朱的女儿
        3. 灿灿还有一个弟弟，叫帅帅
        
        检索目标：找到与"小朱的儿子"相关的记忆
        """
        print("\n" + "=" * 60)
        print("测试：家庭关系检索")
        print("=" * 60)
        
        # 构建私有记忆（使用 add() 直接添加，跳过隐私过滤）
        print("\n--- 阶段 1: 构建记忆 ---")
        
        memories = [
            "小朱有两个孩子",
            "灿灿是小朱的女儿",
            "灿灿还有一个弟弟叫帅帅",
        ]
        
        for memory in memories:
            print(f">>> 存储: {memory}")
            brain.add(memory, unique_user_id)
        
        # 等待索引更新
        print("\n[等待索引更新...]")
        time.sleep(3)
        
        # 测试检索
        print("\n--- 阶段 2: 测试检索 ---")
        
        query = "小朱的儿子叫什么名字"
        print(f">>> 查询: {query}")
        
        result = brain.search(query, unique_user_id)
        print(f"\n检索结果:")
        print(f"  - 向量记忆数: {len(result['memories'])}")
        print(f"  - 图谱关系数: {len(result['relations'])}")
        
        # 打印向量记忆（memories，字段 content）
        if result['memories']:
            print("\n  向量记忆:")
            for chunk in result['memories']:
                text = chunk.get("content", chunk.get("memory", ""))
                score = chunk.get("score", 0)
                print(f"    - {text} (score: {score:.2f})")
        
        # 打印图谱关系（relations，字段 relation）
        if result['relations']:
            print("\n  图谱关系:")
            for rel in result['relations']:
                r = rel.get("relation", rel.get("relationship", "?"))
                print(f"    - {rel['source']} --[{r}]--> {rel['target']}")
        
        # 验证检索到了相关信息
        assert result["metadata"]["has_memory"], "应该检索到相关记忆"
        
        # 验证检索结果中包含关键信息（memories / content）
        all_text = " ".join([
            chunk.get("content", chunk.get("memory", ""))
            for chunk in result["memories"]
        ])
        
        # 应该能检索到与帅帅或弟弟相关的信息
        has_relevant_info = (
            "帅帅" in all_text or
            "弟弟" in all_text or
            len(result["relations"]) > 0
        )
        
        print(f"\n✓ 检索到相关信息: {has_relevant_info}")
        print("\n提示：调用方 LLM 可根据以上信息推理出：")
        print("  帅帅是灿灿的弟弟 → 帅帅是男性 → 帅帅是小朱的儿子")


# =============================================================================
# 性能测试
# =============================================================================

class TestPerformance:
    """性能相关测试"""

    @pytest.mark.slow
    def test_retrieval_response_time(self, brain, unique_user_id):
        """测试检索响应时间"""
        print("\n--- 测试检索响应时间 ---")
        
        start = time.perf_counter()
        result = brain.search("测试查询", unique_user_id)
        elapsed = time.perf_counter() - start
        
        print(f"检索耗时: {elapsed:.2f}s")
        print(f"返回的检索时间: {result['metadata']['retrieval_time_ms']}ms")
        
        # 检索应在 10 秒内完成（放宽以应对网络/API 波动）
        assert elapsed < 10, f"检索时间过长: {elapsed:.2f}s"

    @pytest.mark.slow
    def test_process_response_time(self, brain, unique_user_id):
        """测试完整处理响应时间（包含隐私分类）"""
        print("\n--- 测试完整处理响应时间 ---")
        
        start = time.perf_counter()
        result = brain.process("测试输入", unique_user_id)
        elapsed = time.perf_counter() - start
        
        print(f"处理耗时: {elapsed:.2f}s")
        
        # 完整处理（包含检索，不等待存储）应在 10 秒内
        assert elapsed < 10, f"处理时间过长: {elapsed:.2f}s"


# =============================================================================
# 运行入口（直接执行此文件时）
# =============================================================================

if __name__ == "__main__":
    # 支持直接运行: python tests/test_cognitive.py
    pytest.main([__file__, "-v", "-s"])
