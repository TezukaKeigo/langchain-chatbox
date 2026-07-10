"""
文件系统存储后端 — 基于 JSON 文件的异步文件系统实现。

本模块实现 StorageBackend 抽象基类，提供：
- 目录结构初始化（自动创建数据目录和空数据文件）
- 五个实体（User/Session/Message/Preset/UserConfig）的完整 CRUD
- 基于 asyncio.to_thread 的异步文件 I/O
- 基于 asyncio.Lock 的并发安全保护

设计决策：
- 使用 JSON 格式存储数据（config.yaml 中可配 format: json | yaml，当前实现 JSON）
- 消息按会话独立存储（messages/{session_id}.json），避免单文件过大
- 用户/会话/预设/配置分别存储为顶层 JSON 文件，数据量可控
- 使用 asyncio.to_thread 将同步文件 I/O 放到线程池执行
- 使用 asyncio.Lock 保证并发写入安全（单进程场景）
- 日期时间统一用 ISO 格式字符串存储，读取时转为 datetime 对象
- is_builtin 在 JSON 中存储为布尔值，保持与接口一致

与 SQLite/MySQL 后端的差异：
- 无外键约束：级联删除需要在代码中手动实现
- 无唯一约束：唯一性校验需要在代码中手动检查
- 无事务：多步操作不是原子的（简化实现）
- 无索引：搜索需要全量扫描（仅在学习场景下可接受）

数据目录结构：
    {root}/
    ├── users.json              # {user_id: {user_data}}
    ├── sessions.json           # {session_id: {session_data}}
    ├── presets.json            # {preset_id: {preset_data}}
    ├── user_configs.json       # {user_id: {key: value}}
    └── messages/
        └── {session_id}.json   # [{message_data}, ...]

使用方式：
    backend = FileBackend("data/file_storage")
    await backend.initialize()
    user = await backend.create_user("alice")
    await backend.close()
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import StorageBackend

logger = logging.getLogger("langchain_chat")


# ============================================================
# 辅助函数
# ============================================================


def _parse_datetime(value: Any) -> Optional[datetime]:
    """将 ISO 格式字符串解析为 datetime 对象。

    JSON 文件中日期存储为 ISO 字符串，读取时转为 datetime。
    同时兼容已经是 datetime 对象的值。

    Args:
        value: ISO 格式字符串、datetime 对象或 None

    Returns:
        datetime 对象；解析失败或为空时返回 None
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return None
    return None


# ============================================================
# FileBackend
# ============================================================


class FileBackend(StorageBackend):
    """文件系统异步存储后端。

    使用 JSON 文件进行数据持久化，通过 asyncio.to_thread 实现异步 I/O。

    Attributes:
        _root: 数据存储根目录（Path 对象）
        _format: 存储格式（json）
        _lock: 异步互斥锁（保证并发写入安全）
        _initialized: 是否已完成初始化
    """

    def __init__(self, root_path: str = "data/file_storage", fmt: str = "json") -> None:
        """初始化文件后端。

        Args:
            root_path: 数据存储根目录路径
            fmt: 存储格式（当前仅支持 json）
        """
        self._root = Path(root_path)
        self._format = fmt
        self._lock = asyncio.Lock()
        self._initialized = False

    # ============================================================
    # 生命周期
    # ============================================================

    async def initialize(self) -> None:
        """初始化文件后端：创建目录结构和空数据文件。

        此方法是幂等的 — 多次调用不会损坏数据：
        - 目录已存在不报错
        - 数据文件已存在不会被覆盖
        """
        # 创建目录结构
        self._root.mkdir(parents=True, exist_ok=True)
        (self._root / "messages").mkdir(exist_ok=True)

        # 创建空数据文件（如果不存在）
        for filename in ["users.json", "sessions.json", "presets.json", "user_configs.json"]:
            filepath = self._root / filename
            if not filepath.exists():
                await self._write_json(filepath, {})

        self._initialized = True
        logger.info("File 存储后端初始化完成 — 路径=%s", self._root)

    async def close(self) -> None:
        """关闭文件后端。

        JSON 文件不需要显式关闭连接，
        此方法主要用于接口一致性和未来扩展。
        """
        self._initialized = False

    # ============================================================
    # 内部辅助 — 文件 I/O
    # ============================================================

    def _ensure_initialized(self) -> None:
        """确保后端已完成初始化。"""
        if not self._initialized:
            raise RuntimeError(
                "File 存储后端未初始化，请先调用 initialize() 方法"
            )

    async def _read_json(self, filepath: Path) -> Any:
        """异步读取 JSON 文件。

        Args:
            filepath: JSON 文件路径

        Returns:
            解析后的 Python 对象（通常是 dict 或 list）
        """
        def _sync() -> Any:
            if not filepath.exists():
                return {} if "messages" not in str(filepath) else []
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)

        return await asyncio.to_thread(_sync)

    async def _write_json(self, filepath: Path, data: Any) -> None:
        """异步写入 JSON 文件。

        使用 indent=2 提高可读性，ensure_ascii=False 保留中文字符。
        datetime 对象通过 default=str 转为 ISO 字符串。

        Args:
            filepath: JSON 文件路径
            data: 要写入的数据
        """
        def _sync() -> None:
            # 确保父目录存在
            filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)

        await asyncio.to_thread(_sync)

    def _serialize_datetimes(self, d: Dict[str, Any]) -> Dict[str, Any]:
        """将字典中的 datetime 对象转为 ISO 字符串（写入前处理）。

        Args:
            d: 可能包含 datetime 值的字典

        Returns:
            所有 datetime 已转换为 ISO 字符串的字典
        """
        result = {}
        for k, v in d.items():
            if isinstance(v, datetime):
                result[k] = v.isoformat()
            else:
                result[k] = v
        return result

    def _deserialize_datetimes(
        self, d: Dict[str, Any], *fields: str
    ) -> Dict[str, Any]:
        """将字典中指定字段从 ISO 字符串转为 datetime（读取后处理）。

        Args:
            d: 数据字典
            *fields: 需要转换的字段名

        Returns:
            指定字段已转为 datetime 的字典
        """
        for field in fields:
            if field in d and d[field] is not None:
                d[field] = _parse_datetime(d[field])
        return d

    # ============================================================
    # 内部辅助 — 路径
    # ============================================================

    def _users_path(self) -> Path:
        return self._root / "users.json"

    def _sessions_path(self) -> Path:
        return self._root / "sessions.json"

    def _presets_path(self) -> Path:
        return self._root / "presets.json"

    def _user_configs_path(self) -> Path:
        return self._root / "user_configs.json"

    def _messages_path(self, session_id: str) -> Path:
        return self._root / "messages" / f"{session_id}.json"

    # ============================================================
    # 用户管理 (User CRUD)
    # ============================================================

    async def create_user(
        self, username: str, default_model: str = "gpt-4o-mini"
    ) -> Dict[str, Any]:
        """创建新用户。"""
        from src.models.schemas import _new_id, _now

        self._ensure_initialized()
        user_id = _new_id()
        now = _now()

        async with self._lock:
            users = await self._read_json(self._users_path())

            # 检查用户名唯一性
            for uid, u in users.items():
                if u.get("username") == username:
                    raise ValueError(
                        f"用户名 '{username}' 已存在，请使用其他名称"
                    )

            user_data = {
                "id": user_id,
                "username": username,
                "default_model": default_model,
                "default_preset_id": None,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }
            users[user_id] = user_data
            await self._write_json(self._users_path(), users)

        return {
            "id": user_id,
            "username": username,
            "default_model": default_model,
            "default_preset_id": None,
            "created_at": now,
            "updated_at": now,
        }

    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """按 ID 获取用户。"""
        self._ensure_initialized()
        users = await self._read_json(self._users_path())
        user = users.get(user_id)
        if user is None:
            return None
        return self._deserialize_datetimes(dict(user), "created_at", "updated_at")

    async def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """按用户名获取用户。"""
        self._ensure_initialized()
        users = await self._read_json(self._users_path())
        for uid, u in users.items():
            if u.get("username") == username:
                return self._deserialize_datetimes(dict(u), "created_at", "updated_at")
        return None

    async def list_users(self) -> List[Dict[str, Any]]:
        """列出所有用户（按创建时间倒序）。"""
        self._ensure_initialized()
        users = await self._read_json(self._users_path())
        result = [
            self._deserialize_datetimes(dict(u), "created_at", "updated_at")
            for u in users.values()
        ]
        result.sort(key=lambda u: u.get("created_at", ""), reverse=True)
        return result

    async def update_user(self, user_id: str, **fields) -> Dict[str, Any]:
        """更新用户信息。"""
        self._ensure_initialized()

        async with self._lock:
            users = await self._read_json(self._users_path())
            if user_id not in users:
                raise ValueError(f"用户 {user_id} 不存在")

            allowed = {"default_model", "default_preset_id", "username"}
            for key, value in fields.items():
                if key in allowed and value is not None:
                    users[user_id][key] = value

            users[user_id]["updated_at"] = datetime.utcnow().isoformat()
            await self._write_json(self._users_path(), users)

        return await self.get_user(user_id)

    async def delete_user(self, user_id: str) -> bool:
        """删除用户及其所有关联数据。

        手动实现级联删除（文件后端无外键约束）：
        1. 删除该用户的所有会话及其消息文件
        2. 删除该用户的所有自定义预设
        3. 删除该用户的所有配置项
        4. 删除用户本身
        """
        self._ensure_initialized()

        async with self._lock:
            users = await self._read_json(self._users_path())
            if user_id not in users:
                return False

            sessions = await self._read_json(self._sessions_path())
            presets = await self._read_json(self._presets_path())
            configs = await self._read_json(self._user_configs_path())

            # 删除该用户的会话及消息文件
            session_ids_to_delete = [
                sid for sid, s in sessions.items()
                if s.get("user_id") == user_id
            ]
            for sid in session_ids_to_delete:
                del sessions[sid]
                msg_path = self._messages_path(sid)
                if msg_path.exists():
                    os.remove(msg_path)

            # 删除该用户的私有预设
            preset_ids_to_delete = [
                pid for pid, p in presets.items()
                if p.get("user_id") == user_id
            ]
            for pid in preset_ids_to_delete:
                del presets[pid]

            # 删除该用户的配置
            if user_id in configs:
                del configs[user_id]

            # 删除用户
            del users[user_id]

            # 持久化
            await self._write_json(self._users_path(), users)
            await self._write_json(self._sessions_path(), sessions)
            await self._write_json(self._presets_path(), presets)
            await self._write_json(self._user_configs_path(), configs)

        return True

    # ============================================================
    # 会话管理 (Session CRUD)
    # ============================================================

    async def create_session(
        self,
        user_id: str,
        title: str = "新会话",
        model_name: str = "gpt-4o-mini",
        preset_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """创建新会话。"""
        from src.models.schemas import _new_id, _now

        self._ensure_initialized()
        session_id = _new_id()
        now = _now()

        async with self._lock:
            sessions = await self._read_json(self._sessions_path())
            session_data = {
                "id": session_id,
                "user_id": user_id,
                "title": title,
                "model_name": model_name,
                "preset_id": preset_id,
                "total_prompt_tokens": 0,
                "total_completion_tokens": 0,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }
            sessions[session_id] = session_data
            await self._write_json(self._sessions_path(), sessions)

        return {
            "id": session_id,
            "user_id": user_id,
            "title": title,
            "model_name": model_name,
            "preset_id": preset_id,
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "created_at": now,
            "updated_at": now,
        }

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """按 ID 获取会话。"""
        self._ensure_initialized()
        sessions = await self._read_json(self._sessions_path())
        session = sessions.get(session_id)
        if session is None:
            return None
        return self._deserialize_datetimes(dict(session), "created_at", "updated_at")

    async def list_sessions_by_user(
        self, user_id: str, limit: int = 50, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """列出用户的所有会话（按更新时间倒序）。"""
        self._ensure_initialized()
        sessions = await self._read_json(self._sessions_path())

        user_sessions = [
            self._deserialize_datetimes(dict(s), "created_at", "updated_at")
            for s in sessions.values()
            if s.get("user_id") == user_id
        ]
        user_sessions.sort(
            key=lambda s: s.get("updated_at", ""),
            reverse=True,
        )
        return user_sessions[offset:offset + limit]

    async def update_session(self, session_id: str, **fields) -> Dict[str, Any]:
        """更新会话信息。"""
        self._ensure_initialized()

        async with self._lock:
            sessions = await self._read_json(self._sessions_path())
            if session_id not in sessions:
                raise ValueError(f"会话 {session_id} 不存在")

            allowed = {
                "title", "model_name", "preset_id",
                "total_prompt_tokens", "total_completion_tokens",
            }
            for key, value in fields.items():
                if key in allowed and value is not None:
                    sessions[session_id][key] = value

            sessions[session_id]["updated_at"] = datetime.utcnow().isoformat()
            await self._write_json(self._sessions_path(), sessions)

        return await self.get_session(session_id)

    async def delete_session(self, session_id: str) -> bool:
        """删除会话及其所有消息。"""
        self._ensure_initialized()

        async with self._lock:
            sessions = await self._read_json(self._sessions_path())
            if session_id not in sessions:
                return False

            del sessions[session_id]
            await self._write_json(self._sessions_path(), sessions)

            # 删除消息文件
            msg_path = self._messages_path(session_id)
            if msg_path.exists():
                os.remove(msg_path)

        return True

    # ============================================================
    # 消息管理 (Message CRUD)
    # ============================================================

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> Dict[str, Any]:
        """向会话中添加一条消息。"""
        from src.models.schemas import _new_id, _now

        self._ensure_initialized()
        message_id = _new_id()
        now = _now()

        message_data = {
            "id": message_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "created_at": now.isoformat(),
        }

        async with self._lock:
            messages = await self._read_json(self._messages_path(session_id))
            messages.append(message_data)
            await self._write_json(self._messages_path(session_id), messages)

        return {
            "id": message_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "created_at": now,
        }

    async def list_messages_by_session(
        self, session_id: str, limit: int = 200, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """列出会话中的消息（按时间正序，最早在前）。"""
        self._ensure_initialized()
        messages = await self._read_json(self._messages_path(session_id))

        # 消息在文件中按添加顺序存储（即时间正序）
        result = messages[offset:offset + limit]
        return [
            self._deserialize_datetimes(dict(m), "created_at")
            for m in result
        ]

    async def search_messages(
        self, user_id: str, keyword: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """在用户的所有会话中搜索包含关键词的消息。

        遍历该用户的所有会话，对每条消息做模糊匹配。
        文件后端无索引，大数据量下性能较差，
        仅适合学习和小规模使用场景。

        Args:
            user_id: 用户 ID（限定搜索范围）
            keyword: 搜索关键词
            limit: 返回数量上限

        Returns:
            匹配的消息列表（按时间倒序），每条附带 session_title
        """
        self._ensure_initialized()

        # 获取该用户的所有会话
        sessions = await self._read_json(self._sessions_path())
        user_sessions = {
            sid: s for sid, s in sessions.items()
            if s.get("user_id") == user_id
        }

        # 在所有会话的消息中搜索
        matches = []
        for sid, session in user_sessions.items():
            messages = await self._read_json(self._messages_path(sid))
            for msg in messages:
                content = msg.get("content", "")
                if keyword.lower() in content.lower():
                    match = dict(msg)
                    match["session_title"] = session.get("title", "未知会话")
                    match["created_at"] = _parse_datetime(match.get("created_at"))
                    matches.append(match)

        # 按时间倒序排列
        matches.sort(
            key=lambda m: m.get("created_at", ""),
            reverse=True,
        )
        return matches[:limit]

    # ============================================================
    # 预设管理 (Preset CRUD)
    # ============================================================

    async def create_preset(
        self,
        name: str,
        system_prompt: str,
        user_id: Optional[str] = None,
        description: str = "",
        is_builtin: bool = False,
    ) -> Dict[str, Any]:
        """创建预设角色。"""
        from src.models.schemas import _new_id, _now

        self._ensure_initialized()
        preset_id = _new_id()
        now = _now()

        preset_data = {
            "id": preset_id,
            "user_id": user_id,
            "name": name,
            "description": description,
            "system_prompt": system_prompt,
            "is_builtin": is_builtin,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        async with self._lock:
            presets = await self._read_json(self._presets_path())
            presets[preset_id] = preset_data
            await self._write_json(self._presets_path(), presets)

        return {
            "id": preset_id,
            "user_id": user_id,
            "name": name,
            "description": description,
            "system_prompt": system_prompt,
            "is_builtin": is_builtin,
            "created_at": now,
            "updated_at": now,
        }

    async def get_preset(self, preset_id: str) -> Optional[Dict[str, Any]]:
        """按 ID 获取预设。"""
        self._ensure_initialized()
        presets = await self._read_json(self._presets_path())
        preset = presets.get(preset_id)
        if preset is None:
            return None
        result = self._deserialize_datetimes(
            dict(preset), "created_at", "updated_at"
        )
        result["is_builtin"] = bool(result["is_builtin"])
        return result

    async def list_presets(
        self, user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """列出可见预设（系统内置 + 可选的用户私有）。"""
        self._ensure_initialized()
        presets = await self._read_json(self._presets_path())

        results = []
        for p in presets.values():
            is_builtin = p.get("is_builtin", False)
            owner = p.get("user_id")
            if is_builtin or (user_id is not None and owner == user_id):
                d = self._deserialize_datetimes(
                    dict(p), "created_at", "updated_at"
                )
                d["is_builtin"] = bool(d["is_builtin"])
                results.append(d)

        # 排序：系统内置在前，按创建时间升序
        results.sort(
            key=lambda p: (not p["is_builtin"], p.get("created_at", "")),
        )
        return results

    async def update_preset(self, preset_id: str, **fields) -> Dict[str, Any]:
        """更新预设。内置预设不可编辑。"""
        self._ensure_initialized()

        async with self._lock:
            presets = await self._read_json(self._presets_path())
            if preset_id not in presets:
                raise ValueError(f"预设 {preset_id} 不存在")
            if presets[preset_id].get("is_builtin"):
                raise ValueError("系统内置预设不可编辑")

            allowed = {"name", "description", "system_prompt"}
            for key, value in fields.items():
                if key in allowed and value is not None:
                    presets[preset_id][key] = value

            presets[preset_id]["updated_at"] = datetime.utcnow().isoformat()
            await self._write_json(self._presets_path(), presets)

        return await self.get_preset(preset_id)

    async def delete_preset(self, preset_id: str) -> bool:
        """删除预设。内置预设不可删除。"""
        self._ensure_initialized()

        async with self._lock:
            presets = await self._read_json(self._presets_path())
            if preset_id not in presets:
                return False
            if presets[preset_id].get("is_builtin"):
                raise ValueError("系统内置预设不可删除")

            del presets[preset_id]
            await self._write_json(self._presets_path(), presets)

        return True

    # ============================================================
    # 用户配置管理 (UserConfig CRUD)
    # ============================================================

    async def set_user_config(
        self, user_id: str, key: str, value: str
    ) -> Dict[str, Any]:
        """设置用户配置项（Upsert 语义）。"""
        from src.models.schemas import _now

        self._ensure_initialized()
        now = _now()

        async with self._lock:
            configs = await self._read_json(self._user_configs_path())
            if user_id not in configs:
                configs[user_id] = {}
            configs[user_id][key] = value
            await self._write_json(self._user_configs_path(), configs)

        return {
            "user_id": user_id,
            "key": key,
            "value": value,
            "updated_at": now,
        }

    async def get_user_config(self, user_id: str, key: str) -> Optional[str]:
        """获取用户配置项的值。"""
        self._ensure_initialized()
        configs = await self._read_json(self._user_configs_path())
        user_configs = configs.get(user_id, {})
        return user_configs.get(key)

    async def get_all_user_configs(self, user_id: str) -> Dict[str, str]:
        """获取用户的所有配置项。"""
        self._ensure_initialized()
        configs = await self._read_json(self._user_configs_path())
        return dict(configs.get(user_id, {}))

    async def delete_user_config(self, user_id: str, key: str) -> bool:
        """删除用户配置项。"""
        self._ensure_initialized()

        async with self._lock:
            configs = await self._read_json(self._user_configs_path())
            if user_id not in configs or key not in configs[user_id]:
                return False
            del configs[user_id][key]
            await self._write_json(self._user_configs_path(), configs)

        return True
