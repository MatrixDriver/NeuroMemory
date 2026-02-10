"""高层 API：会话管理模块（示例实现）"""

from __future__ import annotations
from typing import List, Dict, Optional
import httpx


class ConversationsClient:
    """会话管理客户端 - 高层 API

    让用户直接提交对话，系统自动处理记忆提取。
    """

    def __init__(self, http: httpx.Client):
        self._http = http

    def add_message(
        self,
        user_id: str,
        role: str,
        content: str,
        session_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> Dict:
        """添加单条对话消息

        Args:
            user_id: 用户 ID
            role: 角色 (user/assistant/system)
            content: 消息内容
            session_id: 会话 ID（可选，自动生成）
            metadata: 元数据（时间戳等）

        Returns:
            消息记录

        Example:
            >>> client.conversations.add_message(
            ...     user_id="user123",
            ...     role="user",
            ...     content="我喜欢蓝色"
            ... )
        """
        payload = {
            "user_id": user_id,
            "role": role,
            "content": content,
            "session_id": session_id,
            "metadata": metadata,
        }
        resp = self._http.post("/conversations/messages", json=payload)
        resp.raise_for_status()
        return resp.json()

    def add_messages(
        self,
        user_id: str,
        messages: List[Dict],
        session_id: Optional[str] = None,
    ) -> Dict:
        """批量添加对话消息

        Args:
            user_id: 用户 ID
            messages: 消息列表 [{"role": "user", "content": "..."}, ...]
            session_id: 会话 ID

        Returns:
            添加结果统计

        Example:
            >>> client.conversations.add_messages(
            ...     user_id="user123",
            ...     messages=[
            ...         {"role": "user", "content": "我在 Google 工作"},
            ...         {"role": "assistant", "content": "很高兴认识您！"}
            ...     ]
            ... )
        """
        payload = {
            "user_id": user_id,
            "messages": messages,
            "session_id": session_id,
        }
        resp = self._http.post("/conversations/batch", json=payload)
        resp.raise_for_status()
        return resp.json()

    def enable_auto_extract(
        self,
        user_id: str,
        trigger: str = "message_count",
        threshold: int = 10,
        async_mode: bool = True,
    ) -> Dict:
        """启用自动记忆提取

        Args:
            user_id: 用户 ID
            trigger: 触发方式 (message_count/time_interval)
            threshold: 触发阈值（消息数或分钟数）
            async_mode: 是否异步执行

        Example:
            >>> client.conversations.enable_auto_extract(
            ...     user_id="user123",
            ...     trigger="message_count",
            ...     threshold=10
            ... )
        """
        payload = {
            "user_id": user_id,
            "trigger": trigger,
            "threshold": threshold,
            "async_mode": async_mode,
        }
        resp = self._http.post("/conversations/auto-extract", json=payload)
        resp.raise_for_status()
        return resp.json()

    def extract_memories(
        self,
        user_id: str,
        session_id: Optional[str] = None,
        force: bool = False,
    ) -> Dict:
        """手动触发记忆提取

        从会话中提取偏好、事实、情景记忆等。

        Args:
            user_id: 用户 ID
            session_id: 会话 ID（可选，提取所有会话）
            force: 强制重新提取（即使已提取过）

        Returns:
            提取结果统计

        Example:
            >>> result = client.conversations.extract_memories(
            ...     user_id="user123",
            ...     session_id="session_001"
            ... )
            >>> print(result)
            {
                "preferences_extracted": 2,
                "facts_extracted": 5,
                "documents_extracted": 1,
                "status": "completed"
            }
        """
        payload = {
            "user_id": user_id,
            "session_id": session_id,
            "force": force,
        }
        resp = self._http.post("/conversations/extract", json=payload)
        resp.raise_for_status()
        return resp.json()

    def get_session_history(
        self,
        user_id: str,
        session_id: str,
        limit: int = 100,
    ) -> List[Dict]:
        """获取会话历史

        Args:
            user_id: 用户 ID
            session_id: 会话 ID
            limit: 返回消息数量

        Returns:
            消息列表
        """
        resp = self._http.get(
            f"/conversations/sessions/{session_id}",
            params={"user_id": user_id, "limit": limit}
        )
        resp.raise_for_status()
        return resp.json()["messages"]

    def list_sessions(
        self,
        user_id: str,
        limit: int = 50,
    ) -> List[Dict]:
        """列出用户的所有会话

        Args:
            user_id: 用户 ID
            limit: 返回会话数量

        Returns:
            会话列表
        """
        resp = self._http.get(
            "/conversations/sessions",
            params={"user_id": user_id, "limit": limit}
        )
        resp.raise_for_status()
        return resp.json()["sessions"]
