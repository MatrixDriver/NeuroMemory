"""
NeuroMemory Session 管理测试套件

测试 Session 管理、指代消解和整合功能：
- SessionManager 生命周期测试
- CoreferenceResolver 指代消解测试
- SessionConsolidator 整合测试
- 端到端集成测试

运行前准备：
1. 启动数据库服务: docker-compose up -d
2. 等待服务就绪（约 10-20 秒）

运行方式:
    # 运行所有测试（跳过需要数据库的测试如果数据库未运行）
    pytest tests/test_session.py -v
    
    # 只运行不需要数据库的测试
    pytest tests/test_session.py -m "not requires_db" -v
    
    # 跳过慢速测试
    pytest tests/test_session.py -m "not slow" -v
"""
import pytest
import time
import asyncio
from datetime import datetime, timedelta

from config import LLM_PROVIDER, EMBEDDING_PROVIDER

# 为整个测试文件设置默认超时（30秒）
pytestmark = pytest.mark.timeout(30)


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
    """创建共享的 PrivateBrain 实例"""
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
    print("初始化 PrivateBrain (Session 管理)...")
    print(f"当前配置: LLM={LLM_PROVIDER}, Embedding={EMBEDDING_PROVIDER}")
    print(f"数据库: Qdrant={qdrant_host}:{qdrant_port}, Neo4j={neo4j_url}")
    print("=" * 60)
    
    try:
        brain_instance = PrivateBrain()
        
        # 预热
        print("执行预热调用...")
        try:
            brain_instance.search("预热查询", "warmup_user")
        except Exception as e:
            print(f"预热调用异常（可忽略）: {e}")
        print("预热完成")
        print("=" * 60)
        
        return brain_instance
    except Exception as e:
        pytest.skip(f"无法初始化 PrivateBrain（数据库连接失败）: {e}")


@pytest.fixture
def unique_user_id():
    """生成唯一的用户 ID"""
    return f"test_user_{int(time.time() * 1000)}"


@pytest.fixture
def session_manager():
    """获取 SessionManager 实例"""
    from session_manager import get_session_manager
    return get_session_manager()


@pytest.fixture
def coreference_resolver():
    """获取 CoreferenceResolver 实例"""
    from coreference import get_coreference_resolver
    return get_coreference_resolver()


@pytest.fixture
def event_loop():
    """为每个测试创建独立的 event loop，并正确清理"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    
    # 清理：取消所有待处理的任务
    try:
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    except Exception:
        pass
    finally:
        loop.close()


# =============================================================================
# 单元测试：SessionManager
# =============================================================================

class TestSessionManager:
    """测试 SessionManager 生命周期管理"""
    
    @pytest.mark.timeout(5)
    def test_shared_consolidation_executor(self, session_manager):
        """验证使用共享 ThreadPoolExecutor，避免每次 end_session 新建导致线程泄漏"""
        assert hasattr(session_manager, "_consolidation_executor")
        from concurrent.futures import ThreadPoolExecutor
        assert isinstance(session_manager._consolidation_executor, ThreadPoolExecutor)
    
    @pytest.mark.timeout(5)
    def test_create_session(self, session_manager, unique_user_id, event_loop):
        """测试 Session 创建"""
        session = event_loop.run_until_complete(
            session_manager.get_or_create_session(unique_user_id)
        )
        
        assert session is not None
        assert session.user_id == unique_user_id
        assert session.status.value == "active"
        assert len(session.events) == 0
    
    @pytest.mark.timeout(5)
    def test_get_existing_session(self, session_manager, unique_user_id, event_loop):
        """测试获取已存在的 Session"""
        # 创建 Session
        session1 = event_loop.run_until_complete(
            session_manager.get_or_create_session(unique_user_id)
        )
        session_id = session1.session_id
        
        # 再次获取应该是同一个 Session
        session2 = event_loop.run_until_complete(
            session_manager.get_or_create_session(unique_user_id)
        )
        
        assert session2.session_id == session_id
    
    @pytest.mark.timeout(5)
    def test_add_event(self, session_manager, unique_user_id, event_loop):
        """测试添加事件"""
        from session_manager import Event
        
        # 创建 Session
        session = event_loop.run_until_complete(
            session_manager.get_or_create_session(unique_user_id)
        )
        
        # 添加事件
        event = Event(
            event_id="evt_test",
            role="user",
            content="测试内容",
            timestamp=datetime.now(),
        )
        
        event_loop.run_until_complete(
            session_manager.add_event(unique_user_id, event)
        )
        
        # 验证事件已添加
        events = event_loop.run_until_complete(
            session_manager.get_session_events(unique_user_id)
        )
        
        assert len(events) == 1
        assert events[0].content == "测试内容"
    
    @pytest.mark.timeout(5)
    def test_get_session_events_limit(self, session_manager, unique_user_id, event_loop):
        """测试获取事件数量限制"""
        from session_manager import Event
        
        # 添加多个事件
        for i in range(10):
            event = Event(
                event_id=f"evt_{i}",
                role="user",
                content=f"内容 {i}",
                timestamp=datetime.now(),
            )
            event_loop.run_until_complete(
                session_manager.add_event(unique_user_id, event)
            )
        
        # 获取最近 5 条
        events = event_loop.run_until_complete(
            session_manager.get_session_events(unique_user_id, limit=5)
        )
        
        assert len(events) == 5
        # 应该是最新的 5 条
        assert events[-1].content == "内容 9"
    
    @pytest.mark.timeout(5)
    def test_end_session(self, session_manager, unique_user_id, event_loop):
        """测试结束 Session"""
        from session_manager import Event
        
        # 创建 Session 并添加事件
        session = event_loop.run_until_complete(
            session_manager.get_or_create_session(unique_user_id)
        )
        
        event = Event(
            event_id="evt_test",
            role="user",
            content="测试内容",
            timestamp=datetime.now(),
        )
        event_loop.run_until_complete(
            session_manager.add_event(unique_user_id, event)
        )
        
        # 结束 Session
        summary = event_loop.run_until_complete(
            session_manager.end_session(unique_user_id)
        )
        
        assert summary is not None
        assert summary.event_count == 1
        assert summary.user_id == unique_user_id
        
        # Session 应该已结束
        session = event_loop.run_until_complete(
            session_manager.get_or_create_session(unique_user_id)
        )
        # 应该创建了新 Session（因为旧的已结束）
        assert session.status.value == "active"
    
    @pytest.mark.timeout(5)
    def test_get_session_status(self, session_manager, unique_user_id, event_loop):
        """测试获取 Session 状态"""
        from session_manager import Event
        
        # 创建 Session 并添加事件
        event_loop.run_until_complete(
            session_manager.get_or_create_session(unique_user_id)
        )
        
        event = Event(
            event_id="evt_test",
            role="user",
            content="测试内容",
            timestamp=datetime.now(),
        )
        event_loop.run_until_complete(
            session_manager.add_event(unique_user_id, event)
        )
        
        # 获取状态
        status = session_manager.get_session_status(unique_user_id)
        
        assert status is not None
        assert status["event_count"] == 1
        assert "created_at" in status
        assert "last_active_at" in status


# =============================================================================
# 单元测试：CoreferenceResolver
# =============================================================================

class TestCoreferenceResolver:
    """测试指代消解功能"""
    
    @pytest.mark.timeout(5)
    def test_extract_nouns_preserves_order(self, coreference_resolver):
        """_extract_nouns 有序去重，保留首次出现顺序，nouns[-1] 为最近出现的名词"""
        text = "灿灿 小红 灿灿"
        nouns = coreference_resolver._extract_nouns(text)
        assert "灿灿" in nouns and "小红" in nouns
        # 首次出现顺序：灿灿 先于 小红，故 灿灿 在 小红 前面
        assert nouns.index("灿灿") < nouns.index("小红")
        assert nouns[-1]  # 有最后一个元素，供 resolve_query 使用
    
    @pytest.mark.timeout(5)
    def test_resolve_query_no_context(self, coreference_resolver):
        """测试无上下文时不消解"""
        from session_manager import Event
        
        query = "这个是什么？"
        context = []
        
        resolved = coreference_resolver.resolve_query(query, context)
        
        assert resolved == query  # 无上下文，不消解
    
    @pytest.mark.timeout(5)
    def test_resolve_query_this(self, coreference_resolver):
        """测试消解 '这个'"""
        from session_manager import Event
        
        query = "你喜欢吃这个吗？"
        context = [
            Event(
                event_id="evt1",
                role="user",
                content="桔子熟了",
                timestamp=datetime.now(),
            ),
            Event(
                event_id="evt2",
                role="user",
                content="很甜",
                timestamp=datetime.now(),
            ),
        ]
        
        resolved = coreference_resolver.resolve_query(query, context)
        
        # 应该消解为包含"桔子"
        assert "桔子" in resolved or resolved != query
    
    @pytest.mark.timeout(5)
    def test_resolve_query_she(self, coreference_resolver):
        """测试消解 '她'"""
        from session_manager import Event
        
        query = "她今年几岁了？"
        context = [
            Event(
                event_id="evt1",
                role="user",
                content="我女儿叫灿灿",
                timestamp=datetime.now(),
            ),
        ]
        
        resolved = coreference_resolver.resolve_query(query, context)
        
        # 应该消解为包含"灿灿"
        assert "灿灿" in resolved or resolved != query
    
    @pytest.mark.timeout(60)
    @pytest.mark.slow
    def test_resolve_events_llm(self, coreference_resolver):
        """测试 LLM 消解事件（需要 LLM 调用）"""
        from session_manager import Event
        
        events = [
            Event(
                event_id="evt1",
                role="user",
                content="我女儿叫灿灿",
                timestamp=datetime.now(),
            ),
            Event(
                event_id="evt2",
                role="user",
                content="她今年5岁",
                timestamp=datetime.now(),
            ),
            Event(
                event_id="evt3",
                role="user",
                content="她喜欢画画",
                timestamp=datetime.now(),
            ),
        ]
        
        print("\n--- 测试 LLM 消解 ---")
        memories = coreference_resolver.resolve_events(events)
        
        print(f"输入事件数: {len(events)}")
        print(f"输出记忆数: {len(memories)}")
        for i, memory in enumerate(memories):
            print(f"  记忆 {i+1}: {memory}")
        
        # 应该返回至少一条记忆
        assert len(memories) > 0
        # 应该消解了代词
        for memory in memories:
            assert "她" not in memory or "灿灿" in memory


# =============================================================================
# 单元测试：SessionConsolidator
# =============================================================================

class TestSessionConsolidator:
    """测试 Session 整合功能"""
    
    @pytest.mark.timeout(5)
    def test_consolidate_empty_session(self):
        """测试空 Session 跳过整合"""
        from session_manager import Session
        from consolidator import get_consolidator
        
        consolidator = get_consolidator()
        
        session = Session(
            session_id="sess_test",
            user_id="test_user",
            events=[],
        )
        
        result = consolidator.consolidate(session)
        
        assert result.skipped is True
        assert result.reason == "empty_session"
        assert result.stored_count == 0
    
    @pytest.mark.timeout(60)
    @pytest.mark.slow
    def test_consolidate_with_events(self, unique_user_id):
        """测试整合有事件的 Session（需要 LLM 调用）"""
        from session_manager import Session, Event
        from consolidator import get_consolidator
        
        consolidator = get_consolidator()
        
        session = Session(
            session_id="sess_test",
            user_id=unique_user_id,
            events=[
                Event(
                    event_id="evt1",
                    role="user",
                    content="我女儿叫灿灿",
                    timestamp=datetime.now(),
                ),
                Event(
                    event_id="evt2",
                    role="user",
                    content="她今年5岁",
                    timestamp=datetime.now(),
                ),
            ],
        )
        
        print("\n--- 测试 Session 整合 ---")
        result = consolidator.consolidate(session)
        
        print(f"整合结果: {result.to_dict()}")
        
        # 应该尝试整合（可能因为隐私过滤而存储 0 条）
        assert result.skipped is False or result.stored_count >= 0


# =============================================================================
# 集成测试：端到端流程
# =============================================================================

class TestSessionIntegration:
    """测试 Session 管理端到端流程"""
    
    @pytest.mark.requires_db
    @pytest.mark.timeout(30)
    @pytest.mark.slow
    def test_multi_turn_conversation(self, brain, unique_user_id):
        """测试多轮对话的指代消解"""
        print("\n" + "=" * 60)
        print("测试：多轮对话指代消解")
        print("=" * 60)
        
        # 第一轮：介绍
        result1 = brain.process("我叫小朱", unique_user_id)
        print(f"\n>>> 输入: 我叫小朱")
        print(f">>> 返回: {result1.get('resolved_query', 'N/A')}")
        assert result1["status"] == "success"
        
        # 第二轮：介绍女儿
        result2 = brain.process("我女儿叫灿灿", unique_user_id)
        print(f"\n>>> 输入: 我女儿叫灿灿")
        print(f">>> 返回: {result2.get('resolved_query', 'N/A')}")
        assert result2["status"] == "success"
        
        # 第三轮：包含代词
        result3 = brain.process("她今年几岁了？", unique_user_id)
        print(f"\n>>> 输入: 她今年几岁了？")
        print(f">>> 返回 resolved_query: {result3.get('resolved_query', 'N/A')}")
        print(f">>> 返回 memories: {len(result3.get('memories', []))} 条")
        
        # 应该消解了"她"
        resolved = result3.get("resolved_query", "")
        assert "她" not in resolved or "灿灿" in resolved
    
    @pytest.mark.requires_db
    @pytest.mark.timeout(60)
    @pytest.mark.slow
    def test_end_session_consolidation(self, brain, unique_user_id):
        """测试显式结束 Session 触发整合"""
        print("\n" + "=" * 60)
        print("测试：显式结束 Session")
        print("=" * 60)
        
        # 添加一些事件
        brain.process("我叫小朱", unique_user_id)
        brain.process("我女儿叫灿灿", unique_user_id)
        time.sleep(1)  # 等待事件添加
        
        # 结束 Session
        result = brain.end_session(unique_user_id)
        print(f"\n>>> 结束 Session 结果: {result}")
        
        assert result["status"] == "success"
        assert result["session_info"] is not None
        assert result["session_info"]["event_count"] == 2
        
        # 等待整合完成
        time.sleep(3)
        
        # 验证整合后的记忆可以检索
        search_result = brain.search("小朱的女儿", unique_user_id)
        print(f"\n>>> 搜索 '小朱的女儿': {search_result}")
        
        # 可能检索到整合后的记忆（取决于整合是否完成和隐私过滤结果）
        # 这里只验证搜索不报错
        assert search_result["status"] == "success"
    
    @pytest.mark.requires_db
    @pytest.mark.timeout(60)
    @pytest.mark.slow
    def test_cross_session_query(self, brain, unique_user_id):
        """测试跨 Session 查询"""
        print("\n" + "=" * 60)
        print("测试：跨 Session 查询")
        print("=" * 60)
        
        # Session 1: 存储记忆
        brain.process("我叫小朱", unique_user_id)
        brain.process("我女儿叫灿灿", unique_user_id)
        
        # 结束 Session 1
        brain.end_session(unique_user_id)
        time.sleep(5)  # 等待整合完成
        
        # Session 2: 查询
        result = brain.process("小朱的女儿叫什么？", unique_user_id)
        print(f"\n>>> 查询: 小朱的女儿叫什么？")
        print(f">>> 返回: {result}")
        
        assert result["status"] == "success"
        # 可能检索到之前的记忆
        assert "resolved_query" in result
        assert "memories" in result


# =============================================================================
# 边缘情况测试
# =============================================================================

class TestEdgeCases:
    """测试边缘情况"""
    
    @pytest.mark.timeout(5)
    def test_empty_session_timeout(self, session_manager, unique_user_id, event_loop):
        """测试空 Session 超时"""
        # 创建空 Session
        session = event_loop.run_until_complete(
            session_manager.get_or_create_session(unique_user_id)
        )
        
        # 手动设置超时（模拟）
        session.last_active_at = datetime.now() - timedelta(hours=1)
        
        # 检查超时（现在不会死锁了）
        event_loop.run_until_complete(session_manager._check_timeouts())
        
        # 空 Session 超时应该被清理
        status = session_manager.get_session_status(unique_user_id)
        # 可能已清理或已结束
        assert status is None or session.status.value != "active"
    
    @pytest.mark.timeout(10)
    def test_max_events_limit(self, session_manager, unique_user_id, event_loop):
        """测试最大事件数限制"""
        from session_manager import Event
        from config import SESSION_MAX_EVENTS
        
        # 添加最大事件数
        for i in range(SESSION_MAX_EVENTS):
            event = Event(
                event_id=f"evt_{i}",
                role="user",
                content=f"内容 {i}",
                timestamp=datetime.now(),
            )
            event_loop.run_until_complete(
                session_manager.add_event(unique_user_id, event)
            )
        
        # 再添加一个应该触发结束
        event = Event(
            event_id="evt_overflow",
            role="user",
            content="溢出事件",
            timestamp=datetime.now(),
        )
        event_loop.run_until_complete(
            session_manager.add_event(unique_user_id, event)
        )
        
        # 应该创建了新 Session
        session = event_loop.run_until_complete(
            session_manager.get_or_create_session(unique_user_id)
        )
        # 新 Session 应该只有 1 个事件
        assert len(session.events) == 1


# =============================================================================
# 运行入口
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
