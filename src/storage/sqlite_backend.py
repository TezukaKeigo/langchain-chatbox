"""
SQLite 存储后端 — 基于 aiosqlite 的异步 SQLite 实现。

本模块实现 StorageBackend 抽象基类，提供：
- 数据库初始化（建库、建表、启用外键）
- 五个实体（User/Session/Message/Preset/UserConfig）的完整 CRUD
- 自动创建数据目录和数据库文件

设计决策：
- 使用 aiosqlite.Row 作为行工厂，返回类字典对象
- 日期时间统一用 ISO 格式字符串存储（SQLite 无原生的 DATETIME 类型）
- 所有写入操作在方法内部 commit，读取操作不需要
- 外键约束 ON DELETE CASCADE 保证数据一致性
- 数据库文件路径不存在时自动创建父目录

使用方式：
    backend = SQLiteBackend("data/sqlite/app.db")
    await backend.initialize()       # 建表
    user = await backend.create_user("alice")
    await backend.close()            # 关闭连接
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite

from .base import StorageBackend


# ============================================================
# SQL 建表语句
# ============================================================

# 按照外键依赖顺序排列：先创建被引用的表
# users 和 presets 无外键，先创建
# sessions 引用 users
# messages 引用 sessions
# user_configs 引用 users

_CREATE_TABLE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id              TEXT PRIMARY KEY,
    username        TEXT UNIQUE NOT NULL,
    default_model   TEXT DEFAULT 'gpt-4o-mini',
    default_preset_id TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
"""

_CREATE_TABLE_PRESETS = """
CREATE TABLE IF NOT EXISTS presets (
    id              TEXT PRIMARY KEY,
    user_id         TEXT,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    system_prompt   TEXT NOT NULL,
    is_builtin      INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

_CREATE_TABLE_SESSIONS = """
CREATE TABLE IF NOT EXISTS sessions (
    id                      TEXT PRIMARY KEY,
    user_id                 TEXT NOT NULL,
    title                   TEXT DEFAULT '新会话',
    model_name              TEXT DEFAULT 'gpt-4o-mini',
    preset_id               TEXT,
    total_prompt_tokens     INTEGER DEFAULT 0,
    total_completion_tokens INTEGER DEFAULT 0,
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

_CREATE_TABLE_MESSAGES = """
CREATE TABLE IF NOT EXISTS messages (
    id                  TEXT PRIMARY KEY,
    session_id          TEXT NOT NULL,
    role                TEXT NOT NULL,
    content             TEXT DEFAULT '',
    prompt_tokens       INTEGER DEFAULT 0,
    completion_tokens   INTEGER DEFAULT 0,
    created_at          TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
"""

_CREATE_TABLE_USER_CONFIGS = """
CREATE TABLE IF NOT EXISTS user_configs (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    key         TEXT NOT NULL,
    value       TEXT DEFAULT '',
    updated_at  TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(user_id, key)
);
"""

# 按外键依赖顺序执行建表
_ALL_CREATE_STATEMENTS = [
    _CREATE_TABLE_USERS,
    _CREATE_TABLE_PRESETS,
    _CREATE_TABLE_SESSIONS,
    _CREATE_TABLE_MESSAGES,
    _CREATE_TABLE_USER_CONFIGS,
]


# ============================================================
# 辅助函数
# ============================================================

def _to_iso(dt: Optional[datetime]) -> Optional[str]:
    """将 datetime 对象转为 ISO 格式字符串。

    SQLite 不原生支持 DATETIME 类型，统一用 ISO 8601 文本存储。

    Args:
        dt: datetime 对象或 None

    Returns:
        ISO 格式字符串，如 "2024-01-15T14:30:00"；None 保持不变
    """
    if dt is None:
        return None
    return dt.isoformat()


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    """将 ISO 字符串解析为 datetime 对象。

    从数据库读取时的逆向转换。

    Args:
        value: ISO 格式字符串或 None

    Returns:
        datetime 对象；解析失败或为空时返回 None
    """
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


# ============================================================
# SQLiteBackend
# ============================================================

class SQLiteBackend(StorageBackend):
    """SQLite 异步存储后端。

    实现 StorageBackend 定义的所有抽象方法，
    使用 aiosqlite 进行异步数据库操作。

    Attributes:
        _db_path: SQLite 数据库文件路径
        _conn: aiosqlite 连接实例（initialize 后可用）
    """

    def __init__(self, db_path: str = "data/sqlite/app.db") -> None:
        """初始化 SQLite 后端。

        Args:
            db_path: 数据库文件路径（相对于项目根目录或绝对路径）
        """
        self._db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    # ============================================================
    # 生命周期
    # ============================================================

    async def initialize(self) -> None:
        """初始化数据库：创建目录、建立连接、建表。

        此方法是幂等的 — 多次调用不会损坏数据：
        - 目录已存在不报错
        - CREATE TABLE IF NOT EXISTS 不重复建表

        调用顺序：
        1. 确保数据目录存在
        2. 建立 aiosqlite 连接
        3. 启用外键约束
        4. 依次建表
        """
        # 1. 确保父目录存在
        db_file = Path(self._db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        # 2. 建立连接（aiosqlite 在 connect 时会自动创建空的 db 文件）
        self._conn = await aiosqlite.connect(str(db_file))
        self._conn.row_factory = aiosqlite.Row  # 类字典行访问

        # 3. 启用外键约束（SQLite 默认不启用）
        await self._conn.execute("PRAGMA foreign_keys = ON;")

        # 4. 按依赖顺序建表
        for sql in _ALL_CREATE_STATEMENTS:
            await self._conn.execute(sql)

        # 持久化建表结果
        await self._conn.commit()

    async def close(self) -> None:
        """关闭数据库连接，释放资源。"""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    # ============================================================
    # 内部辅助
    # ============================================================

    def _ensure_connected(self) -> aiosqlite.Connection:
        """确保数据库已连接。未初始化时抛出明确错误。"""
        if self._conn is None:
            raise RuntimeError("数据库未初始化，请先调用 initialize() 方法")
        return self._conn

    @staticmethod
    def _row_to_dict(row: aiosqlite.Row) -> Dict[str, Any]:
        """将 aiosqlite.Row 转为普通字典。"""
        if row is None:
            return None
        return dict(row)

    @staticmethod
    def _parse_row_datetimes(
        row_dict: Dict[str, Any],
        *fields: str,
    ) -> Dict[str, Any]:
        """将指定字段从 ISO 字符串转为 datetime 对象。"""
        for field in fields:
            if field in row_dict:
                row_dict[field] = _parse_datetime(row_dict[field])
        return row_dict

    # ============================================================
    # 用户管理 (User CRUD)
    # ============================================================

    async def create_user(
        self, username: str, default_model: str = "gpt-4o-mini"
    ) -> Dict[str, Any]:
        """创建新用户。"""
        from src.models.schemas import _new_id, _now
        db = self._ensure_connected()

        user_id = _new_id()
        now = _to_iso(_now())

        try:
            await db.execute(
                """INSERT INTO users (id, username, default_model, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, username, default_model, now, now),
            )
            await db.commit()
        except aiosqlite.IntegrityError:
            raise ValueError(f"用户名 '{username}' 已存在，请使用其他名称") from None

        return {
            "id": user_id,
            "username": username,
            "default_model": default_model,
            "default_preset_id": None,
            "created_at": _parse_datetime(now),
            "updated_at": _parse_datetime(now),
        }

    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """按 ID 获取用户。"""
        db = self._ensure_connected()
        cursor = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._parse_row_datetimes(dict(row), "created_at", "updated_at")

    async def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """按用户名获取用户。"""
        db = self._ensure_connected()
        cursor = await db.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._parse_row_datetimes(dict(row), "created_at", "updated_at")

    async def list_users(self) -> List[Dict[str, Any]]:
        """列出所有用户（按创建时间倒序）。"""
        db = self._ensure_connected()
        cursor = await db.execute("SELECT * FROM users ORDER BY created_at DESC")
        rows = await cursor.fetchall()
        return [
            self._parse_row_datetimes(dict(r), "created_at", "updated_at")
            for r in rows
        ]

    async def update_user(self, user_id: str, **fields) -> Dict[str, Any]:
        """更新用户信息。"""
        db = self._ensure_connected()

        # 先确认用户存在
        existing = await self.get_user(user_id)
        if existing is None:
            raise ValueError(f"用户 {user_id} 不存在")

        # 构建 SET 子句（只更新传入的字段）
        allowed = {"default_model", "default_preset_id", "username"}
        set_parts = []
        params = []

        for key, value in fields.items():
            if key in allowed and value is not None:
                set_parts.append(f"{key} = ?")
                params.append(value)

        if not set_parts:
            return existing  # 无有效更新字段

        # 自动更新 updated_at
        set_parts.append("updated_at = ?")
        params.append(_to_iso(datetime.utcnow()))
        params.append(user_id)

        sql = f"UPDATE users SET {', '.join(set_parts)} WHERE id = ?"
        await db.execute(sql, params)
        await db.commit()

        # 返回更新后的完整用户数据
        return await self.get_user(user_id)

    async def delete_user(self, user_id: str) -> bool:
        """删除用户及其关联数据。

        ON DELETE CASCADE 自动删除：
        - 该用户的所有会话 → 会话的所有消息
        - 该用户的所有自定义预设
        - 该用户的所有配置项
        """
        db = self._ensure_connected()
        cursor = await db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        await db.commit()
        return cursor.rowcount > 0

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
        db = self._ensure_connected()

        session_id = _new_id()
        now = _to_iso(_now())

        await db.execute(
            """INSERT INTO sessions
               (id, user_id, title, model_name, preset_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (session_id, user_id, title, model_name, preset_id, now, now),
        )
        await db.commit()

        return {
            "id": session_id,
            "user_id": user_id,
            "title": title,
            "model_name": model_name,
            "preset_id": preset_id,
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "created_at": _parse_datetime(now),
            "updated_at": _parse_datetime(now),
        }

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """按 ID 获取会话。"""
        db = self._ensure_connected()
        cursor = await db.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._parse_row_datetimes(dict(row), "created_at", "updated_at")

    async def list_sessions_by_user(
        self, user_id: str, limit: int = 50, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """列出用户的所有会话（按更新时间倒序）。"""
        db = self._ensure_connected()
        cursor = await db.execute(
            """SELECT * FROM sessions
               WHERE user_id = ?
               ORDER BY updated_at DESC
               LIMIT ? OFFSET ?""",
            (user_id, limit, offset),
        )
        rows = await cursor.fetchall()
        return [
            self._parse_row_datetimes(dict(r), "created_at", "updated_at")
            for r in rows
        ]

    async def update_session(self, session_id: str, **fields) -> Dict[str, Any]:
        """更新会话信息（标题、模型、Token 计数等）。"""
        db = self._ensure_connected()

        existing = await self.get_session(session_id)
        if existing is None:
            raise ValueError(f"会话 {session_id} 不存在")

        allowed = {
            "title", "model_name", "preset_id",
            "total_prompt_tokens", "total_completion_tokens",
        }
        set_parts = []
        params = []

        for key, value in fields.items():
            if key in allowed and value is not None:
                set_parts.append(f"{key} = ?")
                params.append(value)

        if not set_parts:
            return existing

        set_parts.append("updated_at = ?")
        params.append(_to_iso(datetime.utcnow()))
        params.append(session_id)

        sql = f"UPDATE sessions SET {', '.join(set_parts)} WHERE id = ?"
        await db.execute(sql, params)
        await db.commit()

        return await self.get_session(session_id)

    async def delete_session(self, session_id: str) -> bool:
        """删除会话及其所有消息（CASCADE 自动处理）。"""
        db = self._ensure_connected()
        cursor = await db.execute(
            "DELETE FROM sessions WHERE id = ?", (session_id,)
        )
        await db.commit()
        return cursor.rowcount > 0

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
        """向会话添加一条消息。"""
        from src.models.schemas import _new_id, _now
        db = self._ensure_connected()

        message_id = _new_id()
        now = _to_iso(_now())

        await db.execute(
            """INSERT INTO messages
               (id, session_id, role, content, prompt_tokens, completion_tokens, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (message_id, session_id, role, content, prompt_tokens, completion_tokens, now),
        )
        await db.commit()

        return {
            "id": message_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "created_at": _parse_datetime(now),
        }

    async def list_messages_by_session(
        self, session_id: str, limit: int = 200, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """列出会话中的消息（按时间正序，最早在前）。"""
        db = self._ensure_connected()
        cursor = await db.execute(
            """SELECT * FROM messages
               WHERE session_id = ?
               ORDER BY created_at ASC
               LIMIT ? OFFSET ?""",
            (session_id, limit, offset),
        )
        rows = await cursor.fetchall()
        return [
            self._parse_row_datetimes(dict(r), "created_at")
            for r in rows
        ]

    async def search_messages(
        self, user_id: str, keyword: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """在用户的所有会话中搜索关键词。

        使用 LIKE 进行模糊匹配，搜索范围限定在指定用户的会话中。
        JOIN sessions 表以确保只搜索该用户的会话。

        Args:
            user_id: 用户 ID（限定搜索范围）
            keyword: 搜索关键词（LIKE 模式匹配）
            limit: 返回上限

        Returns:
            匹配的消息列表，每条消息附带所属会话标题
        """
        db = self._ensure_connected()
        # 搜索参数：在关键词前后加 % 实现模糊匹配
        like_pattern = f"%{keyword}%"

        cursor = await db.execute(
            """SELECT m.*, s.title as session_title
               FROM messages m
               INNER JOIN sessions s ON m.session_id = s.id
               WHERE s.user_id = ? AND m.content LIKE ?
               ORDER BY m.created_at DESC
               LIMIT ?""",
            (user_id, like_pattern, limit),
        )
        rows = await cursor.fetchall()
        return [
            self._parse_row_datetimes(dict(r), "created_at")
            for r in rows
        ]

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
        db = self._ensure_connected()

        preset_id = _new_id()
        now = _to_iso(_now())

        await db.execute(
            """INSERT INTO presets
               (id, user_id, name, description, system_prompt, is_builtin, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (preset_id, user_id, name, description, system_prompt, int(is_builtin), now, now),
        )
        await db.commit()

        return {
            "id": preset_id,
            "user_id": user_id,
            "name": name,
            "description": description,
            "system_prompt": system_prompt,
            "is_builtin": is_builtin,
            "created_at": _parse_datetime(now),
            "updated_at": _parse_datetime(now),
        }

    async def get_preset(self, preset_id: str) -> Optional[Dict[str, Any]]:
        """按 ID 获取预设。"""
        db = self._ensure_connected()
        cursor = await db.execute(
            "SELECT * FROM presets WHERE id = ?", (preset_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        result = self._parse_row_datetimes(dict(row), "created_at", "updated_at")
        result["is_builtin"] = bool(result["is_builtin"])
        return result

    async def list_presets(
        self, user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """列出可见预设（系统内置 + 可选的用户私有）。"""
        db = self._ensure_connected()

        if user_id:
            # 系统内置 + 该用户的私有预设
            cursor = await db.execute(
                """SELECT * FROM presets
                   WHERE is_builtin = 1 OR user_id = ?
                   ORDER BY is_builtin DESC, created_at ASC""",
                (user_id,),
            )
        else:
            # 仅系统内置
            cursor = await db.execute(
                """SELECT * FROM presets
                   WHERE is_builtin = 1
                   ORDER BY created_at ASC""",
            )

        rows = await cursor.fetchall()
        results = []
        for r in rows:
            d = self._parse_row_datetimes(dict(r), "created_at", "updated_at")
            d["is_builtin"] = bool(d["is_builtin"])
            results.append(d)
        return results

    async def update_preset(self, preset_id: str, **fields) -> Dict[str, Any]:
        """更新预设。内置预设不可编辑。"""
        db = self._ensure_connected()

        existing = await self.get_preset(preset_id)
        if existing is None:
            raise ValueError(f"预设 {preset_id} 不存在")
        if existing["is_builtin"]:
            raise ValueError("系统内置预设不可编辑")

        allowed = {"name", "description", "system_prompt"}
        set_parts = []
        params = []

        for key, value in fields.items():
            if key in allowed and value is not None:
                set_parts.append(f"{key} = ?")
                params.append(value)

        if not set_parts:
            return existing

        set_parts.append("updated_at = ?")
        params.append(_to_iso(datetime.utcnow()))
        params.append(preset_id)

        sql = f"UPDATE presets SET {', '.join(set_parts)} WHERE id = ?"
        await db.execute(sql, params)
        await db.commit()

        return await self.get_preset(preset_id)

    async def delete_preset(self, preset_id: str) -> bool:
        """删除预设。内置预设不可删除。"""
        db = self._ensure_connected()

        existing = await self.get_preset(preset_id)
        if existing is None:
            return False
        if existing["is_builtin"]:
            raise ValueError("系统内置预设不可删除")

        cursor = await db.execute(
            "DELETE FROM presets WHERE id = ?", (preset_id,)
        )
        await db.commit()
        return cursor.rowcount > 0

    # ============================================================
    # 用户配置管理 (UserConfig CRUD)
    # ============================================================

    async def set_user_config(
        self, user_id: str, key: str, value: str
    ) -> Dict[str, Any]:
        """设置用户配置项（Upsert 语义：存在则更新，不存在则新增）。

        使用 SQLite 的 INSERT OR REPLACE 语法配合 UNIQUE(user_id, key) 约束。
        """
        from src.models.schemas import _new_id, _now
        db = self._ensure_connected()
        now = _to_iso(_now())

        # 先尝试查找已有配置
        cursor = await db.execute(
            "SELECT id FROM user_configs WHERE user_id = ? AND key = ?",
            (user_id, key),
        )
        existing = await cursor.fetchone()

        if existing:
            # 更新已有配置
            await db.execute(
                "UPDATE user_configs SET value = ?, updated_at = ? WHERE user_id = ? AND key = ?",
                (value, now, user_id, key),
            )
        else:
            # 新增配置
            await db.execute(
                """INSERT INTO user_configs (id, user_id, key, value, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (_new_id(), user_id, key, value, now),
            )

        await db.commit()
        return {"user_id": user_id, "key": key, "value": value, "updated_at": _parse_datetime(now)}

    async def get_user_config(self, user_id: str, key: str) -> Optional[str]:
        """获取用户配置项的值。"""
        db = self._ensure_connected()
        cursor = await db.execute(
            "SELECT value FROM user_configs WHERE user_id = ? AND key = ?",
            (user_id, key),
        )
        row = await cursor.fetchone()
        return row["value"] if row else None

    async def get_all_user_configs(self, user_id: str) -> Dict[str, str]:
        """获取用户的所有配置项（key → value 字典）。"""
        db = self._ensure_connected()
        cursor = await db.execute(
            "SELECT key, value FROM user_configs WHERE user_id = ?",
            (user_id,),
        )
        rows = await cursor.fetchall()
        return {row["key"]: row["value"] for row in rows}

    async def delete_user_config(self, user_id: str, key: str) -> bool:
        """删除用户配置项。"""
        db = self._ensure_connected()
        cursor = await db.execute(
            "DELETE FROM user_configs WHERE user_id = ? AND key = ?",
            (user_id, key),
        )
        await db.commit()
        return cursor.rowcount > 0
