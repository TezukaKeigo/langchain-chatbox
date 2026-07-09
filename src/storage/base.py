"""
存储层抽象基类 — 定义可插拔存储后端的统一接口。

所有存储后端（SQLite / MySQL / File）必须继承 StorageBackend
并实现全部抽象方法，保证业务层不依赖具体存储实现。

设计模式：
- 抽象基类模式 (ABC)：强制接口一致性
- 工厂模式 (StorageFactory)：运行时根据配置创建具体后端

每个实体对应一组 CRUD 方法：
- User：create / get / get_by_username / list / update / delete
- Session：create / get / list_by_user / update / delete
- Message：add / list_by_session / search
- Preset：create / get / list_all / list_builtin / list_by_user / update / delete
- UserConfig：set / get / delete
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class StorageBackend(ABC):
    """存储后端的抽象基类。

    定义了所有数据实体的增删改查接口规范。
    每个具体后端实现（SQLiteBackend / MySQLBackend / FileBackend）
    必须实现此接口中的所有抽象方法。

    设计考量：
    - 所有方法均为 async，匹配全链路异步架构
    - 方法命名遵循 get_* / list_* / create_* / update_* / delete_* 惯例
    - 参数和返回值使用 Python 原生类型，不依赖特定 ORM
    """

    # ============================================================
    # 生命周期方法
    # ============================================================

    @abstractmethod
    async def initialize(self) -> None:
        """初始化存储后端。

        职责：
        - 创建数据库连接池（SQLite/MySQL）
        - 执行数据库迁移（建表）
        - 加载内置预设数据
        - 创建必要的目录结构（File 后端）

        此方法在应用启动时由工厂方法调用一次。
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """关闭存储后端。

        职责：
        - 关闭数据库连接池
        - 刷新缓冲区
        - 释放系统资源

        此方法在应用退出时调用。
        """
        ...

    # ============================================================
    # 用户管理 (User CRUD)
    # ============================================================

    @abstractmethod
    async def create_user(self, username: str, default_model: str = "gpt-4o-mini") -> Dict[str, Any]:
        """创建新用户。

        Args:
            username: 用户名（需全局唯一）
            default_model: 用户默认使用的 LLM 模型

        Returns:
            新创建的 User 数据字典

        Raises:
            ValueError: 用户名已存在
        """
        ...

    @abstractmethod
    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """根据 ID 获取用户。

        Args:
            user_id: 用户唯一标识

        Returns:
            User 数据字典；不存在时返回 None
        """
        ...

    @abstractmethod
    async def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """根据用户名获取用户。

        Args:
            username: 用户名

        Returns:
            User 数据字典；不存在时返回 None
        """
        ...

    @abstractmethod
    async def list_users(self) -> List[Dict[str, Any]]:
        """列出所有用户。

        Returns:
            User 数据字典列表，按创建时间倒序排列
        """
        ...

    @abstractmethod
    async def update_user(self, user_id: str, **fields) -> Dict[str, Any]:
        """更新用户信息。

        Args:
            user_id: 用户唯一标识
            **fields: 要更新的字段（如 default_model、default_preset_id）

        Returns:
            更新后的 User 数据字典

        Raises:
            ValueError: 用户不存在
        """
        ...

    @abstractmethod
    async def delete_user(self, user_id: str) -> bool:
        """删除用户及其所有关联数据。

        关联数据包括：
        - 该用户的所有会话及消息
        - 该用户的所有自定义预设
        - 该用户的所有配置项

        Args:
            user_id: 用户唯一标识

        Returns:
            True 表示删除成功；用户不存在返回 False
        """
        ...

    # ============================================================
    # 会话管理 (Session CRUD)
    # ============================================================

    @abstractmethod
    async def create_session(
        self,
        user_id: str,
        title: str = "新会话",
        model_name: str = "gpt-4o-mini",
        preset_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """创建新会话。

        Args:
            user_id: 所属用户 ID
            title: 会话标题
            model_name: 使用的模型名称
            preset_id: 使用的预设 ID（可选）

        Returns:
            新创建的 Session 数据字典
        """
        ...

    @abstractmethod
    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """根据 ID 获取会话。

        Args:
            session_id: 会话唯一标识

        Returns:
            Session 数据字典；不存在时返回 None
        """
        ...

    @abstractmethod
    async def list_sessions_by_user(
        self, user_id: str, limit: int = 50, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """列出某用户的所有会话。

        Args:
            user_id: 用户唯一标识
            limit: 返回数量上限（用于分页）
            offset: 偏移量（用于分页）

        Returns:
            Session 数据字典列表，按更新时间倒序排列
        """
        ...

    @abstractmethod
    async def update_session(self, session_id: str, **fields) -> Dict[str, Any]:
        """更新会话信息。

        Args:
            session_id: 会话唯一标识
            **fields: 要更新的字段（如 title、model_name、preset_id、token 计数）

        Returns:
            更新后的 Session 数据字典

        Raises:
            ValueError: 会话不存在
        """
        ...

    @abstractmethod
    async def delete_session(self, session_id: str) -> bool:
        """删除会话及其所有关联消息。

        Args:
            session_id: 会话唯一标识

        Returns:
            True 表示删除成功；会话不存在返回 False
        """
        ...

    # ============================================================
    # 消息管理 (Message CRUD)
    # ============================================================

    @abstractmethod
    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> Dict[str, Any]:
        """向会话中添加一条消息。

        Args:
            session_id: 所属会话 ID
            role: 消息角色（human / ai / system）
            content: 消息正文
            prompt_tokens: 该消息的 prompt token 消耗
            completion_tokens: 该消息的 completion token 消耗

        Returns:
            新创建的 Message 数据字典
        """
        ...

    @abstractmethod
    async def list_messages_by_session(
        self, session_id: str, limit: int = 200, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """列出会话中的所有消息。

        Args:
            session_id: 会话唯一标识
            limit: 返回数量上限
            offset: 偏移量

        Returns:
            Message 数据字典列表，按时间正序排列（最早在前）
        """
        ...

    @abstractmethod
    async def search_messages(
        self, user_id: str, keyword: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """在用户的所有会话中搜索包含关键词的消息。

        Args:
            user_id: 用户唯一标识（限定搜索范围）
            keyword: 搜索关键词
            limit: 返回数量上限

        Returns:
            匹配的 Message 数据字典列表，附带所属会话标题
        """
        ...

    # ============================================================
    # 预设管理 (Preset CRUD)
    # ============================================================

    @abstractmethod
    async def create_preset(
        self,
        name: str,
        system_prompt: str,
        user_id: Optional[str] = None,
        description: str = "",
        is_builtin: bool = False,
    ) -> Dict[str, Any]:
        """创建预设角色。

        Args:
            name: 预设名称
            system_prompt: 系统提示词
            user_id: 所属用户 ID（None 表示系统内置）
            description: 预设描述
            is_builtin: 是否系统内置

        Returns:
            新创建的 Preset 数据字典
        """
        ...

    @abstractmethod
    async def get_preset(self, preset_id: str) -> Optional[Dict[str, Any]]:
        """根据 ID 获取预设。

        Args:
            preset_id: 预设唯一标识

        Returns:
            Preset 数据字典；不存在时返回 None
        """
        ...

    @abstractmethod
    async def list_presets(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出可见的预设。

        规则：
        - 所有系统内置预设（is_builtin=True）始终可见
        - 如果指定 user_id，额外列出该用户的私有预设
        - 如果不指定 user_id，只列出系统内置预设

        Args:
            user_id: 可选，限定可见范围

        Returns:
            Preset 数据字典列表
        """
        ...

    @abstractmethod
    async def update_preset(self, preset_id: str, **fields) -> Dict[str, Any]:
        """更新预设信息。

        系统内置预设不可被编辑（is_builtin=True 的预设会拒绝更新）。

        Args:
            preset_id: 预设唯一标识
            **fields: 要更新的字段

        Returns:
            更新后的 Preset 数据字典

        Raises:
            ValueError: 预设不存在或为系统内置预设
        """
        ...

    @abstractmethod
    async def delete_preset(self, preset_id: str) -> bool:
        """删除预设。

        系统内置预设不可被删除。

        Args:
            preset_id: 预设唯一标识

        Returns:
            True 表示删除成功

        Raises:
            ValueError: 预设为系统内置预设
        """
        ...

    # ============================================================
    # 用户配置管理 (UserConfig CRUD)
    # ============================================================

    @abstractmethod
    async def set_user_config(self, user_id: str, key: str, value: str) -> Dict[str, Any]:
        """设置用户配置项。

        如果 key 已存在则更新，否则新建（Upsert 语义）。

        Args:
            user_id: 用户唯一标识
            key: 配置键名
            value: 配置值

        Returns:
            UserConfig 数据字典
        """
        ...

    @abstractmethod
    async def get_user_config(self, user_id: str, key: str) -> Optional[str]:
        """获取用户配置项的值。

        Args:
            user_id: 用户唯一标识
            key: 配置键名

        Returns:
            配置值字符串；不存在时返回 None
        """
        ...

    @abstractmethod
    async def get_all_user_configs(self, user_id: str) -> Dict[str, str]:
        """获取用户的所有配置项。

        Args:
            user_id: 用户唯一标识

        Returns:
            键值对字典（key → value）
        """
        ...

    @abstractmethod
    async def delete_user_config(self, user_id: str, key: str) -> bool:
        """删除用户配置项。

        Args:
            user_id: 用户唯一标识
            key: 配置键名

        Returns:
            True 表示删除成功；key 不存在返回 False
        """
        ...
