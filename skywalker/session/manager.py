from __future__ import annotations

import logging
from datetime import datetime, timezone

from skywalker.core import Message, Role
from skywalker.memory.long_term import MemoryManager
from skywalker.session.store import SessionMeta, SessionStore

logger = logging.getLogger("skywalker.session")


class SessionManager:
    """管理会话的完整周期: new → add → save → resume"""

    def __init__(
            self,
            store: SessionStore,
            memory_manager: MemoryManager | None = None,
    ):
        self._store = store
        self._memory_manager = memory_manager
        self._current_session_id: str | None = None
        self._messages: list[Message] = []

    @property
    def current_session_id(self) -> str | None:
        return self._current_session_id

    @property
    def messages(self) -> list[Message]:
        return self._messages

    def new_session(self, project_root: str) -> str:
        """创建新会话，返回会话ID"""
        import random
        now = datetime.now(timezone.utc)
        session_id = now.strftime("%Y%m%d%H%M%S") + f"-{random.randint(1000, 9999)}"
        self._current_session_id = session_id
        self._messages = []

        meta = SessionMeta(
            session_id=session_id,
            title="新会话",
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
            project_root=project_root,
        )
        self._store.create_session_dir(session_id)
        self._store.save_meta(session_id, meta)
        logger.info(f"🆕 新建会话 | id={session_id}")
        return session_id

    def add_message(self, message: Message) -> None:
        """添加一条消息"""
        self._messages.append(message)

    async def save_session(self, title: str | None = None) -> SessionMeta | None:
        """保存会话: 写 messages.json + 更新 meta.json + 写 memory.md"""
        if not self._current_session_id:
            self._current_session_id = "Default Session"
        session_id = self._current_session_id
        now = datetime.now(timezone.utc)

        # 1. 保存 messages.json（若无内容，则不保存）
        if not self.messages:
            logger.debug(f"📭 无消息，删除空会话 | id={session_id}")
            self._store.delete_session(session_id)
            return None

        self._store.save_messages(session_id, self.messages)
        logger.debug(f"💾 保存消息 | id={session_id}, count={len(self.messages)}")

        # 2. 更新 meta.json（无条件）
        meta = self._store.load_meta(session_id)
        if meta is None:
            meta = SessionMeta(
                session_id=session_id,
                title=title or "Default Session",
                created_at=now.isoformat(),
                updated_at=now.isoformat(),
                project_root="",
            )
        if title:
            meta.title = title
        meta.updated_at = now.isoformat()
        meta.message_count = len(self.messages)
        self._store.save_meta(session_id, meta)

        # 3. 写 memory.md（可选，失败不影响会话保存）
        if self._memory_manager and self._messages:
            try:
                gate = self._memory_manager._gate
                if gate:
                    gate_result = await gate.evaluate(self.messages)
                    if gate_result.passed and gate_result.entries:
                        self._store.save_session_memory(session_id, gate_result.entries)
                        logger.debug(f"💾 保存会话记忆 | id={session_id}, entries={len(gate_result.entries)}")
            except Exception as e:
                logger.warning(f"⚠️ 会话记忆保存失败: {e}")

        logger.info(f"✅ 保存会话 | id={session_id}, title={meta.title}, messages={meta.message_count}")
        return meta

    def resume_session(self, session_id: str) -> list[Message]:
        """恢复历史会话，返回消息列表"""
        self._current_session_id = session_id
        self._messages = self._store.load_messages(session_id)
        logger.info(f"📂 恢复会话 | id={session_id}, messages={len(self._messages)}")
        return self._messages

    def list_sessions(self) -> list[SessionMeta]:
        """列出所有会话"""
        sessions = self._store.list_sessions()
        logger.debug(f"📋 列出会话 | count={len(sessions)}")
        return sessions

    def delete_session(self, session_id: str) -> bool:
        """删除指定会话"""
        if session_id == self._current_session_id:
            self._current_session_id = None
            self._messages = []
        result = self._store.delete_session(session_id)
        if result:
            logger.info(f"🗑️ 删除会话 | id={session_id}")
        else:
            logger.warning(f"⚠️ 会话不存在 | id={session_id}")
        return result

    # 别名，简化调用
    async def save(self, title: str | None = None) -> SessionMeta | None:
        return await self.save_session(title)

    def resume(self, session_id: str) -> list[Message]:
        return self.resume_session(session_id)


    # 别名，简化调用
    async def save(self, title: str | None = None) -> SessionMeta:
        return await self.save_session(title)

    def resume(self, session_id: str) -> list[Message]:
        return self.resume_session(session_id)

            



    



