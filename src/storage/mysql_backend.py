"""
MySQL 存储后端 — 基于 aiomysql 的异步 MySQL 实现。

本模块实现 StorageBackend 抽象基类，提供：
- 数据库初始化（建库、建表）
- 五个实体（User/Session/Message/Preset/UserConfig）的完整 CRUD
- 连接池管理（aiomysql.Pool）

设计决策：
- 使用 aiomysql 连接池（create_pool），避免每次操作创建新连接
- 使用 %s 作为 SQL 参数占位符（MySQL/aiomysql 标准）
- 日期时间统一用 ISO 格式字符串存储（DATETIME 类型兼容）
- 所有写入操作在方法内部 commit（auto-commit）
- 外键约束 ON DELETE CASCADE 保证数据一致性（InnoDB 引擎）
- 手动将 MySQL 返回的 tuple 转为 dict（aiomysql 无 row_factory）

与 SQLite 后端的差异：
- 参数占位符: %s（MySQL）vs ?（SQLite）
- 连接管理: 连接池 vs 单连接
- 行转换: 手动 tuple→dict vs Row 工厂
- 建表语法: ENGINE=InnoDB、数据类型差异

使用方式：
    backend = MySQLBackend(
        host='localhost', port=3306,
        user='root', password='', database='langchain_chat',
    )
    await backend.initialize()       # 建库建表
    user = await backend.create_user("alice")
    await backend.close()            # 关闭连接池
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base import StorageBackend

# ============================================================
# SQL 建表语句（MySQL 语法）
# ============================================================

# MySQL 使用 InnoDB 引擎以支持事务和外键
# 使用 VARCHAR(36) 存储 UUID 格式的 ID
# 使用 DATETIME 存储日期时间
# 外键约束 ON DELETE CASCADE 与 SQLite 一致

_CREATE_TABLE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id              VARCHAR(36) PRIMARY KEY,
    username        VARCHAR(50) NOT NULL UNIQUE,
    default_model   VARCHAR(100) DEFAULT 'gpt-4o-mini',
    default_preset_id VARCHAR(36),
    created_at      DATETIME NOT NULL,
    updated_at      DATETIME NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

_CREATE_TABLE_PRESETS = """
CREATE TABLE IF NOT EXISTS presets (
    id              VARCHAR(36) PRIMARY KEY,
    user_id         VARCHAR(36),
    name            VARCHAR(100) NOT NULL,
    description     VARCHAR(500) DEFAULT '',
    system_prompt   TEXT NOT NULL,
    is_builtin      TINYINT(1) DEFAULT 0,
    created_at      DATETIME NOT NULL,
    updated_at      DATETIME NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

_CREATE_TABLE_SESSIONS = """
CREATE TABLE IF NOT EXISTS sessions (
    id                      VARCHAR(36) PRIMARY KEY,
    user_id                 VARCHAR(36) NOT NULL,
    title                   VARCHAR(200) DEFAULT '新会话',
    model_name              VARCHAR(100) DEFAULT 'gpt-4o-mini',
    preset_id               VARCHAR(36),
    total_prompt_tokens     INT DEFAULT 0,
    total_completion_tokens INT DEFAULT 0,
    created_at              DATETIME NOT NULL,
    updated_at              DATETIME NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

_CREATE_TABLE_MESSAGES = """
CREATE TABLE IF NOT EXISTS messages (
    id                  VARCHAR(36) PRIMARY KEY,
    session_id          VARCHAR(36) NOT NULL,
    role                VARCHAR(20) NOT NULL,
    content             TEXT,
    prompt_tokens       INT DEFAULT 0,
    completion_tokens   INT DEFAULT 0,
    created_at          DATETIME NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

_CREATE_TABLE_USER_CONFIGS = """
CREATE TABLE IF NOT EXISTS user_configs (
    id          VARCHAR(36) PRIMARY KEY,
    user_id     VARCHAR(36) NOT NULL,
    `key`       VARCHAR(100) NOT NULL,
    value       TEXT,
    updated_at  DATETIME NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(user_id, `key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

# 按外键依赖顺序执行建表
_ALL_CREATE_STATEMENTS = [
    _CREATE_TABLE_USERS,
    _CREATE_TABLE_PRESETS,
    _CREATE_TABLE_SESSIONS,
    _CREATE_TABLE_MESSAGES,
    _CREATE_TABLE_USER_CONFIGS,
]

# 列名顺序 — 用于将 MySQL 返回的 tuple 转为 dict
_USERS_COLUMNS = [
    "id", "username", "default_model", "default_preset_id",
    "created_at", "updated_at",
]
_PRESETS_COLUMNS = [
    "id", "user_id", "name", "description", "system_prompt",
    "is_builtin", "created_at", "updated_at",
]
_SESSIONS_COLUMNS = [
    "id", "user_id", "title", "model_name", "preset_id",
    "total_prompt_tokens", "total_completion_tokens",
    "created_at", "updated_at",
]
_MESSAGES_COLUMNS = [
    "id", "session_id", "role", "content",
    "prompt_tokens", "completion_tokens", "created_at",
]
_USER_CONFIGS_COLUMNS = ["id", "user_id", "key", "value", "updated_at"]


# ============================================================
# 辅助函数
# ============================================================

def _make_dict(columns: List[str], row: tuple) -> Dict[str, Any]:
    """将 MySQL 查询返回的 tuple 转为 dict。

    Args:
        columns: 列名列表
        row: MySQL 返回的 tuple

    Returns:
        以列名为 key 的字典
    """
    if row is None:
        return None
    return dict(zip(columns, row))


def _to_iso(dt: Optional[datetime]) -> Optional[str]:
    """将 datetime 转为 ISO 格式字符串。"""
    if dt is None:
        return None
    return dt.isoformat(sep=" ", timespec="seconds")


def _parse_datetime(value: Any) -> Optional[datetime]:
    """将数据库返回值转为 datetime 对象。

    MySQL 的 DATETIME 类型通过 aiomysql 返回为 datetime 对象，
    所以大多数情况下不需要转换。但兼容字符串情况。
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return None
    return None


# ============================================================
# MySQLBackend
# ============================================================

class MySQLBackend(StorageBackend):
    """MySQL 异步存储后端。

    使用 aiomysql 连接池进行异步数据库操作。

    Attributes:
        _pool: aiomysql 连接池实例
        _host: MySQL 主机地址
        _port: MySQL 端口
        _user: 数据库用户名
        _password: 数据库密码
        _database: 数据库名
        _pool_size: 连接池大小
        _pool_recycle: 连接回收时间（秒）
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 3306,
        user: str = "root",
        password: str = "",
        database: str = "langchain_chat",
        pool_size: int = 5,
        pool_recycle: int = 3600,
    ) -> None:
        """初始化 MySQL 后端。

        Args:
            host: MySQL 主机地址
            port: MySQL 端口
            user: 数据库用户名
            password: 数据库密码
            database: 数据库名
            pool_size: 连接池大小
            pool_recycle: 连接回收时间（秒）
        """
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._database = database
        self._pool_size = pool_size
        self._pool_recycle = pool_recycle
        self._pool = None

    # ============================================================
    # 生命周期
    # ============================================================

    async def initialize(self) -> None:
        """初始化 MySQL 后端：建库、建表、创建连接池。

        步骤：
        1. 先用无数据库的连接创建数据库（如不存在）
        2. 创建连接池
        3. 执行建表语句（抑制已存在警告）
        """
        import warnings
        import aiomysql

        # 1. 创建数据库（如不存在，抑制已存在警告）
        try:
            conn = await aiomysql.connect(
                host=self._host,
                port=self._port,
                user=self._user,
                password=self._password,
                charset="utf8mb4",
            )
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                async with conn.cursor() as cur:
                    await cur.execute(
                        f"CREATE DATABASE IF NOT EXISTS `{self._database}` "
                        f"DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
                    )
            conn.close()
        except Exception as e:
            raise RuntimeError(
                f"无法连接到 MySQL ({self._host}:{self._port}): {e}"
            ) from e

        # 2. 创建连接池
        self._pool = await aiomysql.create_pool(
            host=self._host,
            port=self._port,
            user=self._user,
            password=self._password,
            db=self._database,
            charset="utf8mb4",
            minsize=1,
            maxsize=self._pool_size,
            pool_recycle=self._pool_recycle,
            autocommit=True,
        )

        # 3. 建表（抑制 MySQL 的 "already exists" / "deprecated" 类 warning）
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cur:
                    for sql in _ALL_CREATE_STATEMENTS:
                        await cur.execute(sql)

    async def close(self) -> None:
        """关闭连接池，释放资源。"""
        if self._pool is not None:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None

    # ============================================================
    # 内部辅助
    # ============================================================

    def _ensure_pool(self):
        """确保连接池已初始化。"""
        if self._pool is None:
            raise RuntimeError(
                "MySQL 连接池未初始化，请先调用 initialize() 方法"
            )
        return self._pool

    # ============================================================
    # 用户管理 (User CRUD)
    # ============================================================

    async def create_user(
        self, username: str, default_model: str = "gpt-4o-mini"
    ) -> Dict[str, Any]:
        """创建新用户。"""
        from src.models.schemas import _new_id, _now
        pool = self._ensure_pool()

        user_id = _new_id()
        now = _now().isoformat(sep=" ", timespec="seconds")

        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                try:
                    await cur.execute(
                        """INSERT INTO users (id, username, default_model, created_at, updated_at)
                           VALUES (%s, %s, %s, %s, %s)""",
                        (user_id, username, default_model, now, now),
                    )
                except Exception as e:
                    error_msg = str(e)
                    if "Duplicate" in error_msg or "duplicate" in error_msg:
                        raise ValueError(
                            f"用户名 '{username}' 已存在，请使用其他名称"
                        ) from None
                    raise

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
        pool = self._ensure_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT * FROM users WHERE id = %s", (user_id,)
                )
                row = await cur.fetchone()
        if row is None:
            return None
        result = _make_dict(_USERS_COLUMNS, row)
        result["created_at"] = _parse_datetime(result["created_at"])
        result["updated_at"] = _parse_datetime(result["updated_at"])
        return result

    async def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """按用户名获取用户。"""
        pool = self._ensure_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT * FROM users WHERE username = %s", (username,)
                )
                row = await cur.fetchone()
        if row is None:
            return None
        result = _make_dict(_USERS_COLUMNS, row)
        result["created_at"] = _parse_datetime(result["created_at"])
        result["updated_at"] = _parse_datetime(result["updated_at"])
        return result

    async def list_users(self) -> List[Dict[str, Any]]:
        """列出所有用户（按创建时间倒序）。"""
        pool = self._ensure_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT * FROM users ORDER BY created_at DESC"
                )
                rows = await cur.fetchall()
        results = []
        for row in rows:
            d = _make_dict(_USERS_COLUMNS, row)
            d["created_at"] = _parse_datetime(d["created_at"])
            d["updated_at"] = _parse_datetime(d["updated_at"])
            results.append(d)
        return results

    async def update_user(self, user_id: str, **fields) -> Dict[str, Any]:
        """更新用户信息。"""
        pool = self._ensure_pool()

        # 先确认用户存在
        existing = await self.get_user(user_id)
        if existing is None:
            raise ValueError(f"用户 {user_id} 不存在")

        allowed = {"default_model", "default_preset_id", "username"}
        set_parts = []
        params = []

        for key, value in fields.items():
            if key in allowed and value is not None:
                set_parts.append(f"{key} = %s")
                params.append(value)

        if not set_parts:
            return existing

        set_parts.append("updated_at = %s")
        params.append(datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ", timespec="seconds"))
        params.append(user_id)

        sql = f"UPDATE users SET {', '.join(set_parts)} WHERE id = %s"
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)

        return await self.get_user(user_id)

    async def delete_user(self, user_id: str) -> bool:
        """删除用户及其关联数据（CASCADE 自动处理）。"""
        pool = self._ensure_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM users WHERE id = %s", (user_id,)
                )
                affected = cur.rowcount
        return affected > 0

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
        pool = self._ensure_pool()

        session_id = _new_id()
        now = _now().isoformat(sep=" ", timespec="seconds")

        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """INSERT INTO sessions
                       (id, user_id, title, model_name, preset_id, created_at, updated_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (session_id, user_id, title, model_name, preset_id, now, now),
                )

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
        pool = self._ensure_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT * FROM sessions WHERE id = %s", (session_id,)
                )
                row = await cur.fetchone()
        if row is None:
            return None
        result = _make_dict(_SESSIONS_COLUMNS, row)
        result["created_at"] = _parse_datetime(result["created_at"])
        result["updated_at"] = _parse_datetime(result["updated_at"])
        return result

    async def list_sessions_by_user(
        self, user_id: str, limit: int = 50, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """列出用户的所有会话（按更新时间倒序）。"""
        pool = self._ensure_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """SELECT * FROM sessions
                       WHERE user_id = %s
                       ORDER BY updated_at DESC
                       LIMIT %s OFFSET %s""",
                    (user_id, limit, offset),
                )
                rows = await cur.fetchall()
        results = []
        for row in rows:
            d = _make_dict(_SESSIONS_COLUMNS, row)
            d["created_at"] = _parse_datetime(d["created_at"])
            d["updated_at"] = _parse_datetime(d["updated_at"])
            results.append(d)
        return results

    async def update_session(self, session_id: str, **fields) -> Dict[str, Any]:
        """更新会话信息。"""
        pool = self._ensure_pool()

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
                set_parts.append(f"{key} = %s")
                params.append(value)

        if not set_parts:
            return existing

        set_parts.append("updated_at = %s")
        params.append(datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ", timespec="seconds"))
        params.append(session_id)

        sql = f"UPDATE sessions SET {', '.join(set_parts)} WHERE id = %s"
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)

        return await self.get_session(session_id)

    async def delete_session(self, session_id: str) -> bool:
        """删除会话及其所有消息（CASCADE 自动处理）。"""
        pool = self._ensure_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM sessions WHERE id = %s", (session_id,)
                )
                affected = cur.rowcount
        return affected > 0

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
        pool = self._ensure_pool()

        message_id = _new_id()
        now = _now().isoformat(sep=" ", timespec="seconds")

        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """INSERT INTO messages
                       (id, session_id, role, content, prompt_tokens, completion_tokens, created_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (message_id, session_id, role, content,
                     prompt_tokens, completion_tokens, now),
                )

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
        """列出会话中的消息（按时间正序）。"""
        pool = self._ensure_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """SELECT * FROM messages
                       WHERE session_id = %s
                       ORDER BY created_at ASC
                       LIMIT %s OFFSET %s""",
                    (session_id, limit, offset),
                )
                rows = await cur.fetchall()
        results = []
        for row in rows:
            d = _make_dict(_MESSAGES_COLUMNS, row)
            d["created_at"] = _parse_datetime(d["created_at"])
            results.append(d)
        return results

    async def search_messages(
        self, user_id: str, keyword: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """在用户的所有会话中搜索包含关键词的消息。

        MySQL 的 LIKE 默认不区分大小写（取决于 collation），
        utf8mb4_unicode_ci 是大小写不敏感的。
        """
        pool = self._ensure_pool()
        like_pattern = f"%{keyword}%"

        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """SELECT m.*, s.title as session_title
                       FROM messages m
                       INNER JOIN sessions s ON m.session_id = s.id
                       WHERE s.user_id = %s AND m.content LIKE %s
                       ORDER BY m.created_at DESC
                       LIMIT %s""",
                    (user_id, like_pattern, limit),
                )
                rows = await cur.fetchall()

        # 搜索结果包含了额外的 session_title 列
        search_columns = _MESSAGES_COLUMNS + ["session_title"]
        results = []
        for row in rows:
            d = _make_dict(search_columns, row)
            d["created_at"] = _parse_datetime(d["created_at"])
            results.append(d)
        return results

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
        pool = self._ensure_pool()

        preset_id = _new_id()
        now = _now().isoformat(sep=" ", timespec="seconds")

        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """INSERT INTO presets
                       (id, user_id, name, description, system_prompt, is_builtin,
                        created_at, updated_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    (preset_id, user_id, name, description, system_prompt,
                     int(is_builtin), now, now),
                )

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
        pool = self._ensure_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT * FROM presets WHERE id = %s", (preset_id,)
                )
                row = await cur.fetchone()
        if row is None:
            return None
        result = _make_dict(_PRESETS_COLUMNS, row)
        result["created_at"] = _parse_datetime(result["created_at"])
        result["updated_at"] = _parse_datetime(result["updated_at"])
        result["is_builtin"] = bool(result["is_builtin"])
        return result

    async def list_presets(
        self, user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """列出可见预设（系统内置 + 可选的用户私有）。"""
        pool = self._ensure_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                if user_id:
                    await cur.execute(
                        """SELECT * FROM presets
                           WHERE is_builtin = 1 OR user_id = %s
                           ORDER BY is_builtin DESC, created_at ASC""",
                        (user_id,),
                    )
                else:
                    await cur.execute(
                        """SELECT * FROM presets
                           WHERE is_builtin = 1
                           ORDER BY created_at ASC""",
                    )
                rows = await cur.fetchall()

        results = []
        for row in rows:
            d = _make_dict(_PRESETS_COLUMNS, row)
            d["created_at"] = _parse_datetime(d["created_at"])
            d["updated_at"] = _parse_datetime(d["updated_at"])
            d["is_builtin"] = bool(d["is_builtin"])
            results.append(d)
        return results

    async def update_preset(self, preset_id: str, **fields) -> Dict[str, Any]:
        """更新预设。内置预设不可编辑。"""
        pool = self._ensure_pool()

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
                set_parts.append(f"{key} = %s")
                params.append(value)

        if not set_parts:
            return existing

        set_parts.append("updated_at = %s")
        params.append(datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ", timespec="seconds"))
        params.append(preset_id)

        sql = f"UPDATE presets SET {', '.join(set_parts)} WHERE id = %s"
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)

        return await self.get_preset(preset_id)

    async def delete_preset(self, preset_id: str) -> bool:
        """删除预设。内置预设不可删除。"""
        pool = self._ensure_pool()

        existing = await self.get_preset(preset_id)
        if existing is None:
            return False
        if existing["is_builtin"]:
            raise ValueError("系统内置预设不可删除")

        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM presets WHERE id = %s", (preset_id,)
                )
                affected = cur.rowcount
        return affected > 0

    # ============================================================
    # 用户配置管理 (UserConfig CRUD)
    # ============================================================

    async def set_user_config(
        self, user_id: str, key: str, value: str
    ) -> Dict[str, Any]:
        """设置用户配置项（Upsert 语义）。

        使用 MySQL 的 INSERT ... ON DUPLICATE KEY UPDATE 语法。
        """
        from src.models.schemas import _new_id, _now
        pool = self._ensure_pool()
        now = _now().isoformat(sep=" ", timespec="seconds")

        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """INSERT INTO user_configs (id, user_id, `key`, value, updated_at)
                       VALUES (%s, %s, %s, %s, %s)
                       ON DUPLICATE KEY UPDATE value = VALUES(value),
                                               updated_at = VALUES(updated_at)""",
                    (_new_id(), user_id, key, value, now),
                )

        return {
            "user_id": user_id,
            "key": key,
            "value": value,
            "updated_at": _parse_datetime(now),
        }

    async def get_user_config(self, user_id: str, key: str) -> Optional[str]:
        """获取用户配置项的值。"""
        pool = self._ensure_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT value FROM user_configs WHERE user_id = %s AND `key` = %s",
                    (user_id, key),
                )
                row = await cur.fetchone()
        return row[0] if row else None

    async def get_all_user_configs(self, user_id: str) -> Dict[str, str]:
        """获取用户的所有配置项。"""
        pool = self._ensure_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT `key`, value FROM user_configs WHERE user_id = %s",
                    (user_id,),
                )
                rows = await cur.fetchall()
        return {row[0]: row[1] for row in rows}

    async def delete_user_config(self, user_id: str, key: str) -> bool:
        """删除用户配置项。"""
        pool = self._ensure_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM user_configs WHERE user_id = %s AND `key` = %s",
                    (user_id, key),
                )
                affected = cur.rowcount
        return affected > 0
