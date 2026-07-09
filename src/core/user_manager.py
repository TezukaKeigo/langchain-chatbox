"""
用户管理器 — 用户生命周期管理的业务逻辑层。

职责：
1. 用户创建（用户名唯一性校验）
2. 用户列表查询
3. 用户切换（更新全局状态）
4. 用户删除（级联清理 + 二次确认）
5. 当前用户状态管理

本模块是存储层与 UI 层之间的桥梁：
  存储层只做数据存取，用户管理器在其上叠加业务规则和状态管理。

设计原则：
- 所有方法均为 async，匹配全链路异步架构
- 不直接操作数据库，通过 StorageBackend 接口解耦
- 通过共享 state 字典与 UI 层通信（而非回调或事件）

使用方式：
    storage = await StorageFactory.create(config)
    user_mgr = UserManager(storage, state)
    user = await user_mgr.create_user("alice")
    await user_mgr.switch_user(user["id"])
"""

from typing import Any, Dict, List, Optional

from src.storage.base import StorageBackend


class UserManager:
    """用户管理器 — 封装用户相关的全部业务逻辑。

    在存储层的基础上叠加：
    - 用户名合法性校验
    - 唯一性检查
    - 当前用户状态同步
    - 切换用户时自动清理会话上下文

    Attributes:
        _storage: 存储后端实例（SQLite / MySQL / File）
        _state: 应用全局状态字典（与 TUIApp 共享）
    """

    def __init__(self, storage: StorageBackend, state: Dict[str, Any]) -> None:
        """初始化用户管理器。

        Args:
            storage: 已初始化的存储后端实例
            state: 应用全局状态字典，用于跟踪当前用户
        """
        self._storage = storage
        self._state = state

    # ============================================================
    # 用户 CRUD
    # ============================================================

    async def create_user(
        self, username: str, default_model: str = "gpt-4o-mini"
    ) -> Dict[str, Any]:
        """创建新用户。

        业务规则：
        1. 用户名去除首尾空白
        2. 用户名不能为空
        3. 用户名不能超过 50 个字符
        4. 用户名必须全局唯一（大小写敏感）

        Args:
            username: 用户名（1-50 字符，全局唯一）
            default_model: 该用户的默认 LLM 模型

        Returns:
            新创建的 User 数据字典

        Raises:
            ValueError: 用户名不合法或已存在
        """
        # 1. 输入规范化与校验
        username = username.strip()

        if not username:
            raise ValueError("用户名不能为空")

        if len(username) > 50:
            raise ValueError("用户名不能超过 50 个字符")

        # 2. 唯一性检查（委托给存储层，存储层会再次检查）
        existing = await self._storage.get_user_by_username(username)
        if existing is not None:
            raise ValueError(f"用户名 '{username}' 已存在，请使用其他用户名")

        # 3. 创建用户
        user = await self._storage.create_user(username, default_model=default_model)
        return user

    async def list_users(self) -> List[Dict[str, Any]]:
        """列出所有已注册用户。

        Returns:
            User 数据字典列表，按创建时间倒序排列。
            无用户时返回空列表。
        """
        return await self._storage.list_users()

    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """根据 ID 获取用户信息。

        Args:
            user_id: 用户唯一标识

        Returns:
            User 数据字典；不存在时返回 None
        """
        return await self._storage.get_user(user_id)

    async def delete_user(self, user_id: str) -> bool:
        """删除用户及其所有关联数据。

        关联数据包括（由存储层的 ON DELETE CASCADE 自动处理）：
        - 该用户的所有会话及消息
        - 该用户的所有自定义预设
        - 该用户的所有配置项

        如果删除的是当前活跃用户，自动清除当前用户状态。

        Args:
            user_id: 要删除的用户唯一标识

        Returns:
            True 表示删除成功；用户不存在返回 False

        Raises:
            ValueError: 存储层抛出的异常（如外键约束等）
        """
        # 执行删除（存储层处理级联）
        result = await self._storage.delete_user(user_id)

        # 如果删除的是当前活跃用户，清除状态
        if result and user_id == self._state.get("current_user_id"):
            self.clear_current_user()

        return result

    # ============================================================
    # 当前用户状态管理
    # ============================================================

    def set_current_user(self, user: Dict[str, Any]) -> None:
        """设置为当前活跃用户。

        同时清除旧的会话上下文（因为切换用户后，
        旧会话属于上一个用户，不应继续使用）。

        Args:
            user: 用户数据字典（至少包含 id 和 username）
        """
        self._state["current_user_id"] = user["id"]
        self._state["current_username"] = user["username"]

        # 切换用户后清除旧的会话上下文
        self._state["current_session_id"] = None
        self._state["current_session_title"] = None
        self._state["current_preset_id"] = None
        self._state["current_preset_name"] = None

    def clear_current_user(self) -> None:
        """清除当前活跃用户状态。

        通常在以下场景调用：
        - 删除了当前用户
        - 用户主动退出登录（后期扩展）
        """
        self._state["current_user_id"] = None
        self._state["current_username"] = None
        self._state["current_session_id"] = None
        self._state["current_session_title"] = None
        self._state["current_preset_id"] = None
        self._state["current_preset_name"] = None

    def get_current_user_id(self) -> Optional[str]:
        """获取当前活跃用户的 ID。

        Returns:
            用户 ID 字符串；未选择用户时返回 None
        """
        return self._state.get("current_user_id")

    def get_current_username(self) -> Optional[str]:
        """获取当前活跃用户的用户名。

        Returns:
            用户名字符串；未选择用户时返回 None
        """
        return self._state.get("current_username")

    @property
    def is_user_selected(self) -> bool:
        """是否有当前活跃用户。

        Returns:
            True 表示已选择用户
        """
        return self._state.get("current_user_id") is not None
