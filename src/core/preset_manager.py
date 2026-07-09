"""
预设管理器 — 系统内置预设加载 + 用户自定义预设管理的业务逻辑层。

职责：
1. 启动时将 config/presets.yaml 中的内置预设同步到数据库（幂等）
2. 用户自定义预设的 CRUD（创建/编辑/删除）
3. 预设选择与取消（更新全局状态）

内置预设 vs 自定义预设：
- 内置预设（is_builtin=True, user_id=None）：所有用户共享，不可编辑/删除
- 自定义预设（is_builtin=False, user_id=具体用户）：个人创建，可自由管理

设计原则：
- 与 UserManager 一致，通过共享 state 字典与 UI 层通信
- 不直接操作数据库，通过 StorageBackend 接口解耦

使用方式：
    preset_mgr = PresetManager(storage, state, config)
    await preset_mgr.load_builtin_presets()  # 首次启动时同步
    presets = await preset_mgr.list_presets(user_id)
"""

from typing import Any, Dict, List, Optional

from src.storage.base import StorageBackend


class PresetManager:
    """预设管理器 — 封装预设相关的全部业务逻辑。

    在存储层的基础上叠加：
    - 内置预设的自动同步
    - 内置预设的修改保护（再校验一层）
    - 当前预设的状态同步

    Attributes:
        _storage: 存储后端实例
        _state: 应用全局状态字典
        _config: ConfigManager 实例（读取内置预设配置）
    """

    def __init__(
        self,
        storage: StorageBackend,
        state: Dict[str, Any],
        config: Any,
    ) -> None:
        """初始化预设管理器。

        Args:
            storage: 已初始化的存储后端实例
            state: 应用全局状态字典
            config: ConfigManager 实例
        """
        self._storage = storage
        self._state = state
        self._config = config

    # ============================================================
    # 内置预设同步
    # ============================================================

    async def load_builtin_presets(self) -> int:
        """将 config/presets.yaml 中的内置预设同步到数据库。

        按名称逐条检查，仅创建数据库中不存在的预设。
        这种逐条比对策略比「只要有 builtin 就全跳过」更健壮：
        - 数据库中有残留旧预设时不会阻塞新预设的加载
        - 后续在 YAML 中新增预设会自动同步

        Returns:
            本次新加载的预设数量
        """
        # 获取数据库中已有的内置预设名称集合
        existing_builtins = await self._storage.list_presets(user_id=None)
        existing_names = {p["name"] for p in existing_builtins}

        # 从配置中读取内置预设，跳过已存在的
        presets_config = self._config.presets
        count = 0
        for preset_data in presets_config:
            if preset_data["name"] in existing_names:
                continue  # 已存在，跳过

            await self._storage.create_preset(
                name=preset_data["name"],
                system_prompt=preset_data["system_prompt"],
                description=preset_data.get("description", ""),
                is_builtin=True,
            )
            count += 1

        return count

    # ============================================================
    # 预设查询
    # ============================================================

    async def list_presets(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出用户可见的预设。

        规则（由存储层实现）：
        - 所有内置预设始终可见
        - 如指定 user_id，额外返回该用户的私有预设

        Args:
            user_id: 用户 ID（None 时仅返回内置预设）

        Returns:
            Preset 数据字典列表
        """
        return await self._storage.list_presets(user_id=user_id)

    async def get_preset(self, preset_id: str) -> Optional[Dict[str, Any]]:
        """根据 ID 获取预设详情。

        Args:
            preset_id: 预设唯一标识

        Returns:
            Preset 数据字典；不存在时返回 None
        """
        return await self._storage.get_preset(preset_id)

    # ============================================================
    # 自定义预设 CRUD
    # ============================================================

    async def create_preset(
        self,
        user_id: str,
        name: str,
        system_prompt: str,
        description: str = "",
    ) -> Dict[str, Any]:
        """创建用户自定义预设。

        业务规则：
        1. 名称不能为空
        2. 系统提示词不能为空
        3. 名称不超过 100 字符

        Args:
            user_id: 所属用户 ID
            name: 预设名称
            system_prompt: 系统提示词
            description: 预设描述（可选）

        Returns:
            新创建的 Preset 数据字典

        Raises:
            ValueError: 参数不合法
        """
        name = name.strip()
        system_prompt = system_prompt.strip()

        if not name:
            raise ValueError("预设名称不能为空")
        if len(name) > 100:
            raise ValueError("预设名称不能超过 100 个字符")
        if not system_prompt:
            raise ValueError("系统提示词不能为空")

        return await self._storage.create_preset(
            name=name,
            system_prompt=system_prompt,
            user_id=user_id,
            description=description.strip(),
            is_builtin=False,
        )

    async def update_preset(
        self,
        preset_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """更新自定义预设。

        不可编辑内置预设（存储层会再次校验）。

        Args:
            preset_id: 预设唯一标识
            name: 新的预设名称（None 表示不修改）
            description: 新的描述
            system_prompt: 新的系统提示词

        Returns:
            更新后的 Preset 数据字典

        Raises:
            ValueError: 预设为内置预设或不存在
        """
        fields = {}
        if name is not None:
            name = name.strip()
            if not name:
                raise ValueError("预设名称不能为空")
            if len(name) > 100:
                raise ValueError("预设名称不能超过 100 个字符")
            fields["name"] = name
        if description is not None:
            fields["description"] = description.strip()
        if system_prompt is not None:
            system_prompt = system_prompt.strip()
            if not system_prompt:
                raise ValueError("系统提示词不能为空")
            fields["system_prompt"] = system_prompt

        if not fields:
            raise ValueError("没有需要更新的字段")

        return await self._storage.update_preset(preset_id, **fields)

    async def delete_preset(self, preset_id: str) -> bool:
        """删除自定义预设。

        内置预设不可删除（存储层会再次校验）。

        Args:
            preset_id: 预设唯一标识

        Returns:
            True 表示删除成功

        Raises:
            ValueError: 预设为内置预设
        """
        return await self._storage.delete_preset(preset_id)

    # ============================================================
    # 预设选择状态管理
    # ============================================================

    def select_preset(self, preset: Dict[str, Any]) -> None:
        """选择预设为当前会话的角色设定。

        更新全局状态中的 current_preset_id 和 current_preset_name。

        Args:
            preset: Preset 数据字典（至少包含 id 和 name）
        """
        self._state["current_preset_id"] = preset["id"]
        self._state["current_preset_name"] = preset["name"]

    def clear_preset(self) -> None:
        """取消当前预设选择（回到不使用预设的状态）。"""
        self._state["current_preset_id"] = None
        self._state["current_preset_name"] = None

    def get_current_preset_id(self) -> Optional[str]:
        """获取当前选中的预设 ID。

        Returns:
            预设 ID 字符串；未选择时返回 None
        """
        return self._state.get("current_preset_id")

    def get_current_preset_name(self) -> Optional[str]:
        """获取当前选中的预设名称。

        Returns:
            预设名称字符串；未选择时返回 None
        """
        return self._state.get("current_preset_name")
