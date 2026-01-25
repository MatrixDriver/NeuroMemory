"""
Session 管理器模块

实现内部自动 Session 管理，为 NeuroMemory 提供短期记忆存储和生命周期管理。
"""
import asyncio
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from config import (
    SESSION_TIMEOUT_SECONDS,
    SESSION_MAX_DURATION_SECONDS,
    SESSION_MAX_EVENTS,
    SESSION_CHECK_INTERVAL_SECONDS,
)

logger = logging.getLogger("neuro_memory.session")


# =============================================================================
# 数据结构
# =============================================================================

class SessionStatus(Enum):
    """Session 状态"""
    ACTIVE = "active"      # 活跃中
    ENDING = "ending"      # 正在整合到长期记忆
    ENDED = "ended"        # 已结束


@dataclass
class Event:
    """会话事件"""
    event_id: str
    role: str              # "user" | "assistant" | "system"
    content: str           # 事件内容
    timestamp: datetime
    metadata: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "event_id": self.event_id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class Session:
    """用户会话"""
    session_id: str
    user_id: str
    events: list[Event] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    last_active_at: datetime = field(default_factory=datetime.now)
    status: SessionStatus = SessionStatus.ACTIVE
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "event_count": len(self.events),
            "created_at": self.created_at.isoformat(),
            "last_active_at": self.last_active_at.isoformat(),
            "status": self.status.value,
        }


@dataclass
class SessionSummary:
    """Session 结束时的摘要信息"""
    session_id: str
    user_id: str
    event_count: int
    duration_seconds: int
    created_at: datetime
    ended_at: datetime
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "session_id": self.session_id,
            "event_count": self.event_count,
            "duration_seconds": self.duration_seconds,
            "created_at": self.created_at.isoformat(),
            "ended_at": self.ended_at.isoformat(),
        }


# =============================================================================
# SessionManager 类
# =============================================================================

class SessionManager:
    """Session 生命周期管理器"""
    
    def __init__(self):
        """初始化 SessionManager"""
        self._sessions: dict[str, Session] = {}  # user_id -> Session
        self._lock = threading.Lock()  # 使用线程锁，不绑定到 event loop
        self._timeout_task: Optional[asyncio.Task] = None
        self._consolidate_callback = None  # 整合回调函数
        # 共享线程池，用于 Session 整合回调，避免每次 end_session 新建 Executor 导致线程泄漏
        self._consolidation_executor = ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="session_consolidate",
        )
        
        # 不在这里启动超时检查任务（避免绑定到错误的 event loop）
        logger.info("SessionManager 初始化完成")
    
    def start_timeout_checker(self):
        """启动超时检查任务（在 event loop 运行后调用）"""
        if self._timeout_task is None or self._timeout_task.done():
            async def _run_checker():
                while True:
                    try:
                        await asyncio.sleep(SESSION_CHECK_INTERVAL_SECONDS)
                        await self._check_timeouts()
                    except asyncio.CancelledError:
                        break
                    except Exception as e:
                        logger.error(f"超时检查任务异常: {e}")
            
            try:
                loop = asyncio.get_running_loop()
                self._timeout_task = asyncio.create_task(_run_checker())
                logger.info("超时检查任务已启动")
            except RuntimeError:
                logger.debug("当前无运行中的 event loop，跳过启动超时检查任务")
    
    def set_consolidate_callback(self, callback):
        """设置整合回调函数"""
        self._consolidate_callback = callback
    
    def _get_or_create_session_internal(self, user_id: str) -> Session:
        """内部方法：获取或创建 Session（需要在锁内调用）"""
        # 检查是否有活跃 Session
        if user_id in self._sessions:
            session = self._sessions[user_id]
            
            # 如果 Session 已结束，创建新 Session
            if session.status == SessionStatus.ENDED:
                logger.info(f"用户 {user_id} 的 Session 已结束，创建新 Session")
                session = self._create_session(user_id)
                self._sessions[user_id] = session
            else:
                # 刷新最后活跃时间
                session.last_active_at = datetime.now()
                logger.debug(f"刷新用户 {user_id} 的 Session 活跃时间")
        else:
            # 创建新 Session
            session = self._create_session(user_id)
            self._sessions[user_id] = session
            logger.info(f"为用户 {user_id} 创建新 Session: {session.session_id}")
        
        return session
    
    async def get_or_create_session(self, user_id: str) -> Session:
        """
        获取或创建用户 Session
        
        Args:
            user_id: 用户标识
            
        Returns:
            Session 对象
        """
        # 使用线程锁保护同步操作
        with self._lock:
            return self._get_or_create_session_internal(user_id)
    
    def _create_session(self, user_id: str) -> Session:
        """创建新 Session"""
        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        return Session(
            session_id=session_id,
            user_id=user_id,
            created_at=datetime.now(),
            last_active_at=datetime.now(),
            status=SessionStatus.ACTIVE,
        )
    
    async def add_event(self, user_id: str, event: Event) -> None:
        """
        向用户 Session 添加事件
        
        Args:
            user_id: 用户标识
            event: 事件对象
        """
        # 第一步：检查是否需要结束旧 Session
        should_end_session = False
        with self._lock:
            if user_id in self._sessions:
                session = self._sessions[user_id]
                if len(session.events) >= SESSION_MAX_EVENTS:
                    should_end_session = True
        
        # 第二步：在锁外结束旧 Session（避免死锁）
        if should_end_session:
            logger.warning(f"用户 {user_id} 的 Session 达到最大事件数，自动结束")
            await self.end_session(user_id)
        
        # 第三步：添加事件到新 Session
        with self._lock:
            session = self._get_or_create_session_internal(user_id)
            session.events.append(event)
            session.last_active_at = datetime.now()
            logger.debug(f"向用户 {user_id} 的 Session 添加事件: {event.event_id}")
    
    async def get_session_events(self, user_id: str, limit: int = 20) -> list[Event]:
        """
        获取用户 Session 的最近事件
        
        Args:
            user_id: 用户标识
            limit: 返回的最大事件数
            
        Returns:
            事件列表（按时间顺序，最先的在前）
        """
        with self._lock:
            if user_id not in self._sessions:
                return []
            
            session = self._sessions[user_id]
            if session.status == SessionStatus.ENDED:
                return []
            
            # 返回最近的事件（从早到晚），列表切片自动处理越界
            return session.events[-limit:]
    
    async def end_session(self, user_id: str) -> Optional[SessionSummary]:
        """
        结束用户 Session（异步触发整合）
        
        Args:
            user_id: 用户标识
            
        Returns:
            SessionSummary 对象，如果用户没有活跃 Session 则返回 None
        """
        with self._lock:
            if user_id not in self._sessions:
                logger.info(f"用户 {user_id} 没有活跃 Session")
                return None
            
            session = self._sessions[user_id]
            
            if session.status != SessionStatus.ACTIVE:
                logger.info(f"用户 {user_id} 的 Session 状态为 {session.status.value}，无需结束")
                return None
            
            # 标记为正在结束
            session.status = SessionStatus.ENDING
            ended_at = datetime.now()
            
            # 计算摘要
            duration = int((ended_at - session.created_at).total_seconds())
            summary = SessionSummary(
                session_id=session.session_id,
                user_id=user_id,
                event_count=len(session.events),
                duration_seconds=duration,
                created_at=session.created_at,
                ended_at=ended_at,
            )
            
            logger.info(f"结束用户 {user_id} 的 Session: {summary.event_count} 个事件，持续 {duration} 秒")
            
            # 异步触发整合（如果设置了回调）
            if self._consolidate_callback:
                self._consolidation_executor.submit(self._consolidate_callback, session)
            
            # 标记为已结束
            session.status = SessionStatus.ENDED
            
            return summary
    
    async def _check_timeouts(self) -> None:
        """定期检查并结束超时 Session"""
        # 第一步：在锁内收集需要结束的 session
        timeout_sessions = []
        with self._lock:
            now = datetime.now()
            
            for user_id, session in list(self._sessions.items()):
                if session.status != SessionStatus.ACTIVE:
                    continue
                
                # 检查超时
                time_since_active = (now - session.last_active_at).total_seconds()
                session_duration = (now - session.created_at).total_seconds()
                
                should_timeout = (
                    time_since_active > SESSION_TIMEOUT_SECONDS or
                    session_duration > SESSION_MAX_DURATION_SECONDS
                )
                
                if should_timeout:
                    timeout_sessions.append(user_id)
        
        # 第二步：释放锁后，逐个结束 session（避免死锁）
        for user_id in timeout_sessions:
            logger.info(f"检测到用户 {user_id} 的 Session 超时，自动结束")
            await self.end_session(user_id)  # 现在可以安全获取锁
    
    def get_session_status(self, user_id: str) -> Optional[dict]:
        """
        获取用户 Session 状态（同步方法，用于调试）
        
        Args:
            user_id: 用户标识
            
        Returns:
            Session 状态字典，如果没有活跃 Session 则返回 None
        """
        with self._lock:
            if user_id not in self._sessions:
                return None
            session = self._sessions[user_id]
            if session.status != SessionStatus.ACTIVE:
                return None
            now = datetime.now()
            time_until_timeout = SESSION_TIMEOUT_SECONDS - (now - session.last_active_at).total_seconds()
            return {
                "event_count": len(session.events),
                "created_at": session.created_at.isoformat(),
                "last_active_at": session.last_active_at.isoformat(),
                "time_until_timeout_seconds": max(0, int(time_until_timeout)),
            }


# =============================================================================
# 模块级单例
# =============================================================================

_session_manager_instance: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """获取 SessionManager 单例"""
    global _session_manager_instance
    if _session_manager_instance is None:
        _session_manager_instance = SessionManager()
    return _session_manager_instance
