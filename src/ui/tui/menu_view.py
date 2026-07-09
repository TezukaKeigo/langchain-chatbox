"""
菜单视图 — TUI 菜单系统的渲染与交互逻辑。

本模块负责：
1. 主菜单：应用的顶级导航
2. 用户管理菜单：创建 / 切换 / 删除用户
3. 会话管理菜单：新建 / 加载 / 重命名 / 删除会话
4. 预设管理菜单：浏览 / 选择 / 新增 / 编辑 / 删除预设
5. 系统设置菜单：模型配置等

所有菜单使用统一的交互模式：
  显示选项列表 → 等待键盘输入 → 执行对应操作 → 返回结果

当前状态（Step 5）：
  用户管理（创建/切换/删除/列表）：已完整实现，对接 SQLite 数据库。
  预设管理（浏览内置/自定义CRUD/选择切换）：已完整实现。
  会话管理：仍为 stub 占位，将在 Step 7-8 实现。
"""

from typing import Any, Dict, List, Optional

from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.styles import Style

from rich.panel import Panel

from .widgets import (
    Theme,
    console,
    print_error,
    print_header,
    print_info,
    print_menu_options,
    print_success,
    print_table,
    print_warning,
)


# ============================================================
# prompt_toolkit 样式
# ============================================================

# prompt_toolkit 的颜色命名与 Rich 不同，使用 hex 码确保兼容性
# Rich 颜色名（如 bright_cyan）只在 Rich Console 中有效
_MENU_STYLE = Style.from_dict({
    "prompt": "bold #ff00ff",                   # 品红提示符
    "": "#00ffff",                              # 青色输入文字
    "bottom-toolbar": "bg:#333333 #888888",     # 深灰底 + 灰文字底部栏
})


# ============================================================
# 菜单选项数据结构
# ============================================================

def _opt(key: str, label: str, desc: str = "") -> Dict[str, str]:
    """创建菜单选项数据结构的便捷函数。

    Args:
        key: 选项按键（数字或字母）
        label: 选项名称
        desc: 选项描述

    Returns:
        标准化的菜单选项字典
    """
    return {"key": key, "label": label, "desc": desc}


# ============================================================
# MenuView — 菜单视图主类
# ============================================================

class MenuView:
    """TUI 菜单视图管理器。

    提供主菜单和所有子菜单的渲染与交互逻辑。
    所有操作函数接收 state 字典以读写共享状态。

    Attributes:
        state: 应用全局状态字典，在 app.py 中创建，各视图共享
    """

    def __init__(self, state: Dict[str, Any]) -> None:
        """初始化菜单视图。

        Args:
            state: 应用全局状态字典
        """
        self._state = state

    # ============================================================
    # 主菜单
    # ============================================================

    async def show_main_menu(self) -> str:
        """显示主菜单并返回用户选择的操作指令。

        主菜单是应用的总入口，列出所有可用功能模块。

        Returns:
            操作指令字符串，由 app.py 的路由器分发：
            - "user_menu"    — 进入用户管理子菜单
            - "session_menu" — 进入会话管理子菜单
            - "preset_menu"  — 进入预设管理子菜单
            - "start_chat"   — 进入对话界面
            - "settings"     — 进入系统设置
            - "exit"         — 退出程序
        """
        console.clear()
        print_header(
            "LangChain Chat",
            subtitle="基于 LangChain 的多轮对话系统 | TUI 命令行界面",
        )

        # 显示当前上下文状态
        self._print_current_context()

        # 主菜单选项
        options = [
            _opt("1", "用户管理", "创建 / 切换 / 删除用户"),
            _opt("2", "会话管理", "新建 / 加载 / 重命名 / 删除会话"),
            _opt("3", "预设管理", "浏览 / 选择 / 管理角色预设"),
            _opt("4", "开始对话", "进入多轮流式对话"),
            _opt("5", "系统设置", "模型配置 / 存储切换"),
            _opt("0", "退出程序", "保存数据并退出"),
        ]

        print()
        console.print(f"  [{Theme.PRIMARY}]── 主菜单 ──[/{Theme.PRIMARY}]")
        print()
        print_menu_options(options)
        print()

        # 获取用户选择
        choice = await self._get_choice("请选择操作 [0-5]", valid_keys=["0", "1", "2", "3", "4", "5"])

        route_map = {
            "1": "user_menu",
            "2": "session_menu",
            "3": "preset_menu",
            "4": "start_chat",
            "5": "settings",
            "0": "exit",
        }
        return route_map[choice]

    # ============================================================
    # 用户管理子菜单
    # ============================================================

    async def show_user_menu(self) -> Optional[str]:
        """显示用户管理子菜单。

        包含用户的创建、切换、删除操作。
        Step 2 中所有操作均为 stub 占位，
        完整实现将在 Step 4 完成。

        Returns:
            子操作指令字符串，或 None 返回主菜单
        """
        while True:
            console.clear()
            print_header("用户管理", subtitle="创建 / 切换 / 删除用户")

            # 显示当前用户信息
            current_user = self._state.get("current_username")
            if current_user:
                print_info(f"当前用户: {current_user}")
            else:
                print_warning("尚未选择用户，请先创建或切换用户")

            options = [
                _opt("1", "创建新用户", "首次使用时创建唯一用户名"),
                _opt("2", "切换用户", "切换到其他已存在的用户"),
                _opt("3", "删除用户", "删除用户及其所有数据（需二次确认）"),
                _opt("4", "用户列表", "查看所有已注册用户"),
                _opt("0", "返回主菜单", ""),
            ]

            print()
            console.print(f"  [{Theme.PRIMARY}]── 用户管理 ──[/{Theme.PRIMARY}]")
            print()
            print_menu_options(options)
            print()

            choice = await self._get_choice(
                "请选择操作 [0-4]", valid_keys=["0", "1", "2", "3", "4"]
            )

            if choice == "0":
                break

            if choice == "1":
                await self._create_user()
            elif choice == "2":
                await self._switch_user()
            elif choice == "3":
                await self._delete_user()
            elif choice == "4":
                await self._list_users()

        return None

    # ============================================================
    # 会话管理子菜单
    # ============================================================

    async def show_session_menu(self) -> Optional[str]:
        """显示会话管理子菜单。

        包含会话的新建、加载、重命名、删除操作。
        Step 2 中所有操作均为 stub 占位，
        完整实现将在 Step 7-8 完成。

        Returns:
            子操作指令字符串，或 None 返回主菜单
        """
        while True:
            console.clear()
            print_header("会话管理", subtitle="新建 / 加载 / 重命名 / 删除会话")

            current_session = self._state.get("current_session_title")
            if current_session:
                print_info(f"当前会话: {current_session}")

            options = [
                _opt("1", "新建会话", "清空上下文，开始全新对话"),
                _opt("2", "加载历史会话", "浏览并加载之前的对话"),
                _opt("3", "会话列表", "查看当前用户的所有会话"),
                _opt("4", "重命名会话", "修改会话标题"),
                _opt("5", "删除会话", "删除指定会话及其所有消息"),
                _opt("0", "返回主菜单", ""),
            ]

            print()
            console.print(f"  [{Theme.PRIMARY}]── 会话管理 ──[/{Theme.PRIMARY}]")
            print()
            print_menu_options(options)
            print()

            choice = await self._get_choice(
                "请选择操作 [0-5]", valid_keys=["0", "1", "2", "3", "4", "5"]
            )

            if choice == "0":
                break

            stub_messages = {
                "1": "新建会话功能将在 Step 7（核心里程碑）中实现",
                "2": "加载历史会话功能将在 Step 8 中实现",
                "3": "会话列表功能将在 Step 8 中实现",
                "4": "重命名会话功能将在 Step 8 中实现",
                "5": "删除会话功能将在 Step 8 中实现",
            }
            print_info(stub_messages[choice])
            await self._press_enter_to_continue()

        return None

    # ============================================================
    # 预设管理子菜单
    # ============================================================

    async def show_preset_menu(self) -> Optional[str]:
        """显示预设管理子菜单。

        包含系统内置预设浏览、用户自定义预设的管理。
        Step 5 完整实现所有预设操作。

        Returns:
            子操作指令字符串，或 None 返回主菜单
        """
        while True:
            console.clear()
            print_header("预设管理", subtitle="浏览 / 选择 / 管理角色预设")

            current_preset = self._state.get("current_preset_name")
            if current_preset:
                print_info(f"当前预设: {current_preset}")
            else:
                print_info("当前未使用预设角色")

            options = [
                _opt("1", "浏览系统内置预设", "查看所有用户共享的预设角色"),
                _opt("2", "我的自定义预设", "管理个人创建的预设"),
                _opt("3", "新建自定义预设", "创建专属的角色设定"),
                _opt("4", "选择预设", "为当前会话选择一个预设角色"),
                _opt("0", "返回主菜单", ""),
            ]

            print()
            console.print(f"  [{Theme.PRIMARY}]── 预设管理 ──[/{Theme.PRIMARY}]")
            print()
            print_menu_options(options)
            print()

            choice = await self._get_choice(
                "请选择操作 [0-4]", valid_keys=["0", "1", "2", "3", "4"]
            )

            if choice == "0":
                break

            if choice == "1":
                await self._browse_builtin_presets()
            elif choice == "2":
                await self._my_custom_presets()
            elif choice == "3":
                await self._create_custom_preset()
            elif choice == "4":
                await self._select_preset()

        return None

    # ============================================================
    # 系统设置子菜单
    # ============================================================

    async def show_settings_menu(self) -> Optional[str]:
        """显示系统设置子菜单。

        包含模型配置、存储后端切换等设置项。
        Step 2 中所有操作均为 stub 占位。

        Returns:
            子操作指令字符串，或 None 返回主菜单
        """
        while True:
            console.clear()
            print_header("系统设置", subtitle="模型配置 / 存储切换 / 环境管理")

            current_model = self._state.get("current_model", "未设置")
            print_info(f"当前模型: {current_model}")

            options = [
                _opt("1", "切换模型", "在可用模型列表中选择不同的 LLM 模型"),
                _opt("2", "查看配置", "查看当前的全局配置信息"),
                _opt("3", "关于本系统", "版本信息与技术栈"),
                _opt("0", "返回主菜单", ""),
            ]

            print()
            console.print(f"  [{Theme.PRIMARY}]── 系统设置 ──[/{Theme.PRIMARY}]")
            print()
            print_menu_options(options)
            print()

            choice = await self._get_choice(
                "请选择操作 [0-3]", valid_keys=["0", "1", "2", "3"]
            )

            if choice == "0":
                break

            if choice == "1":
                print_info("模型切换功能将在 Step 10（导出+模型切换）中实现")
                await self._press_enter_to_continue()
            elif choice == "2":
                await self._show_config_info()
            elif choice == "3":
                await self._show_about()

        return None

    # ============================================================
    # 用户管理 — 真实实现（Step 4）
    # ============================================================

    def _get_user_manager(self):
        """安全获取 UserManager 实例。

        Returns:
            UserManager 实例，或 None（存储未初始化时）

        如果存储后端尚未初始化（开发早期），返回 None
        并显示友好提示，而非让程序崩溃。
        """
        user_mgr = self._state.get("user_manager")
        if user_mgr is None:
            print_error("存储后端尚未初始化，请重启程序")
            print_info("如果问题持续存在，请运行: uv run python scripts/init_db.py")
        return user_mgr

    async def _create_user(self) -> None:
        """创建新用户。

        流程：
        1. 提示输入用户名
        2. 校验合法性（非空、长度、唯一性）
        3. 写入数据库
        4. 自动设置为当前活跃用户
        """
        console.clear()
        print_header("创建新用户", subtitle="首次使用时创建唯一用户名")

        user_mgr = self._get_user_manager()
        if user_mgr is None:
            await self._press_enter_to_continue()
            return

        # 1. 输入用户名
        print_info("请输入新用户名（1-50 字符，不可与已有用户重复）")
        print()
        try:
            username = await self._get_text_input("用户名: ")
        except (KeyboardInterrupt, EOFError):
            print_info("已取消")
            await self._press_enter_to_continue()
            return

        username = username.strip()
        if not username:
            print_info("已取消（用户名为空）")
            await self._press_enter_to_continue()
            return

        # 2. 可选：选择默认模型
        config = self._state.get("config")
        default_model = config.model_name if config else "deepseek-v4-flash"
        if config:
            available = config.available_models
            if available:
                print()
                print_info("可选默认模型:")
                for i, m in enumerate(available, 1):
                    console.print(f"    [{Theme.MUTED}]{i}.[/{Theme.MUTED}] {m.get('name', '?')} [{Theme.MUTED}]({m.get('description', '')})[/{Theme.MUTED}]")
                print()
                model_choice = await self._get_text_input(f"选择模型编号（直接回车使用默认 {default_model}）: ")
                if model_choice.strip().isdigit():
                    idx = int(model_choice.strip()) - 1
                    if 0 <= idx < len(available):
                        default_model = available[idx].get("name", default_model)

        # 3. 创建用户
        try:
            user = await user_mgr.create_user(username, default_model=default_model)
        except ValueError as e:
            print()
            print_error(str(e))
            await self._press_enter_to_continue()
            return

        # 4. 自动设置为当前用户
        user_mgr.set_current_user(user)
        print()
        print_success(f"用户 '{username}' 创建成功，已自动切换为当前用户")
        print_info(f"默认模型: {default_model}")
        await self._press_enter_to_continue()

    async def _switch_user(self) -> None:
        """切换到其他已存在用户。

        流程：
        1. 加载全部用户列表
        2. 排除当前用户（切换到自己无意义）
        3. 用户按编号选择目标用户
        4. 更新全局状态
        """
        console.clear()
        print_header("切换用户", subtitle="切换到其他已存在的用户")

        user_mgr = self._get_user_manager()
        if user_mgr is None:
            await self._press_enter_to_continue()
            return

        # 1. 获取用户列表
        try:
            users = await user_mgr.list_users()
        except Exception as e:
            print_error(f"获取用户列表失败: {e}")
            await self._press_enter_to_continue()
            return

        if not users:
            print_warning("暂无已注册用户，请先创建用户")
            await self._press_enter_to_continue()
            return

        # 2. 过滤掉当前用户
        current_id = user_mgr.get_current_user_id()
        other_users = [u for u in users if u["id"] != current_id]

        if not other_users:
            print_info("只有当前一个用户，无需切换")
            print_info("你可以创建新用户后再切换")
            await self._press_enter_to_continue()
            return

        # 3. 展示可选用户列表
        print()
        console.print(f"  [{Theme.PRIMARY}]可切换的用户:[/{Theme.PRIMARY}]")
        print()
        for i, u in enumerate(other_users, 1):
            created = u.get("created_at", "")
            if isinstance(created, str):
                created = created.replace("T", " ")[:16]
            console.print(
                f"    [{Theme.HIGHLIGHT}]{i}.[/{Theme.HIGHLIGHT}] "
                f"[bold]{u['username']}[/bold]  "
                f"[{Theme.MUTED}]模型: {u.get('default_model', '?')}  "
                f"创建于: {created}[/{Theme.MUTED}]"
            )

        print()
        valid_keys = [str(i) for i in range(1, len(other_users) + 1)] + ["0"]
        choice = await self._get_choice(
            f"选择要切换的用户 [1-{len(other_users)}, 0=取消]",
            valid_keys=valid_keys,
        )

        if choice == "0":
            print_info("已取消")
            await self._press_enter_to_continue()
            return

        # 4. 执行切换
        idx = int(choice) - 1
        target = other_users[idx]
        old_username = user_mgr.get_current_username()
        user_mgr.set_current_user(target)
        print()
        print_success(f"已从 '{old_username}' 切换到 '{target['username']}'")
        print_info("会话上下文已重置（切换用户后需新建或加载会话）")
        await self._press_enter_to_continue()

    async def _delete_user(self) -> None:
        """删除用户及其所有关联数据。

        流程：
        1. 加载全部用户列表
        2. 用户按编号选择要删除的用户
        3. 显示警告（级联删除的数据范围）
        4. 二次确认：y/n 菜单选择确认
        5. 执行删除
        6. 若删除的是当前用户，自动清除状态
        """
        console.clear()
        print_header("删除用户", subtitle="删除用户及其所有关联数据（需二次确认）")

        user_mgr = self._get_user_manager()
        if user_mgr is None:
            await self._press_enter_to_continue()
            return

        # 1. 获取用户列表
        try:
            users = await user_mgr.list_users()
        except Exception as e:
            print_error(f"获取用户列表失败: {e}")
            await self._press_enter_to_continue()
            return

        if not users:
            print_warning("暂无已注册用户可删除")
            await self._press_enter_to_continue()
            return

        # 2. 展示用户列表
        print()
        console.print(f"  [{Theme.PRIMARY}]选择要删除的用户:[/{Theme.PRIMARY}]")
        print()
        for i, u in enumerate(users, 1):
            is_current = u["id"] == user_mgr.get_current_user_id()
            tag = f" [{Theme.WARNING}](当前用户)[/{Theme.WARNING}]" if is_current else ""
            created = u.get("created_at", "")
            if isinstance(created, str):
                created = created.replace("T", " ")[:16]
            console.print(
                f"    [{Theme.ERROR}]{i}.[/{Theme.ERROR}] "
                f"[bold]{u['username']}[/bold]{tag}  "
                f"[{Theme.MUTED}]创建于: {created}[/{Theme.MUTED}]"
            )

        print()
        valid_keys = [str(i) for i in range(1, len(users) + 1)] + ["0"]
        choice = await self._get_choice(
            f"选择要删除的用户 [1-{len(users)}, 0=取消]",
            valid_keys=valid_keys,
        )

        if choice == "0":
            print_info("已取消")
            await self._press_enter_to_continue()
            return

        # 3. 确认目标用户
        idx = int(choice) - 1
        target = users[idx]

        # 4. 警告 + 二次确认（菜单选择方式，与主菜单同一套稳定输入机制）
        print()
        print_warning("⚠  此操作不可撤销！将永久删除以下数据：")
        print()
        console.print(f"    [{Theme.ERROR}]• 用户账号: {target['username']}[/{Theme.ERROR}]")
        console.print(f"    [{Theme.ERROR}]• 该用户的所有会话及对话记录[/{Theme.ERROR}]")
        console.print(f"    [{Theme.ERROR}]• 该用户的所有自定义预设[/{Theme.ERROR}]")
        console.print(f"    [{Theme.ERROR}]• 该用户的所有个人配置[/{Theme.ERROR}]")
        print()

        # 使用 _get_choice（与菜单选择同一套输入机制），避免 _get_text_input 在 Windows 下
        # 因 pt_prompt(in_thread=True) 返回值含不可见字符导致字符串匹配失败
        print_warning(f"确认删除用户 '{target['username']}'？")
        print()
        confirm_choice = await self._get_choice(
            f"输入 y 确认删除，n 取消",
            valid_keys=["y", "n"],
        )

        if confirm_choice == "n":
            print()
            print_info("已取消")
            await self._press_enter_to_continue()
            return

        # 5. 执行删除
        try:
            success = await user_mgr.delete_user(target["id"])
        except Exception as e:
            print()
            print_error(f"删除失败: {e}")
            await self._press_enter_to_continue()
            return

        if success:
            print()
            print_success(f"用户 '{target['username']}' 及其所有关联数据已删除")
            if target["id"] == user_mgr.get_current_user_id():
                print_info("该用户为当前活跃用户，已自动清除登录状态")
        else:
            print_error(f"用户 '{target['username']}' 不存在或已被删除")

        await self._press_enter_to_continue()

    async def _list_users(self) -> None:
        """显示所有已注册用户列表。

        以 Rich 表格形式展示：
        - 序号
        - 用户名（当前用户加标记）
        - 默认模型
        - 创建时间
        """
        console.clear()
        print_header("用户列表", subtitle="所有已注册用户")

        user_mgr = self._get_user_manager()
        if user_mgr is None:
            await self._press_enter_to_continue()
            return

        # 获取用户列表
        try:
            users = await user_mgr.list_users()
        except Exception as e:
            print_error(f"获取用户列表失败: {e}")
            await self._press_enter_to_continue()
            return

        if not users:
            print_warning("暂无已注册用户")
            print_info("请在「创建新用户」中添加第一个用户")
            await self._press_enter_to_continue()
            return

        # 构建表格数据
        current_id = user_mgr.get_current_user_id()
        columns = [
            {"key": "用户名", "style": "bold"},
            {"key": "默认模型", "style": Theme.MUTED},
            {"key": "创建时间", "style": Theme.MUTED},
            {"key": "状态", "style": Theme.HIGHLIGHT},
        ]
        rows = []
        for u in users:
            is_current = u["id"] == current_id
            created = u.get("created_at", "")
            if isinstance(created, str):
                created = created.replace("T", " ")[:16]
            rows.append([
                u["username"],
                u.get("default_model", "?"),
                created,
                "★ 当前用户" if is_current else "",
            ])

        print()
        print_table("已注册用户", columns, rows, show_index=True)
        print()
        print_info(f"共 {len(users)} 个用户")
        await self._press_enter_to_continue()

    # ============================================================
    # 预设管理 — 真实实现（Step 5）
    # ============================================================

    def _get_preset_manager(self):
        """安全获取 PresetManager 实例。

        Returns:
            PresetManager 实例，或 None（未初始化时）
        """
        preset_mgr = self._state.get("preset_manager")
        if preset_mgr is None:
            print_error("预设管理器尚未初始化，请重启程序")
        return preset_mgr

    async def _browse_builtin_presets(self) -> None:
        """浏览系统内置预设。

        展示所有内置预设的详细信息：
        - 名称和描述
        - 系统提示词全文
        用户可按编号查看详情或直接使用某个预设。
        """
        console.clear()
        print_header("系统内置预设", subtitle="所有用户共享的预设角色")

        preset_mgr = self._get_preset_manager()
        if preset_mgr is None:
            await self._press_enter_to_continue()
            return

        # 获取仅内置预设
        try:
            builtins = await preset_mgr.list_presets(user_id=None)
        except Exception as e:
            print_error(f"获取内置预设失败: {e}")
            await self._press_enter_to_continue()
            return

        if not builtins:
            print_warning("暂无内置预设")
            print_info("请检查 config/presets.yaml 配置文件")
            await self._press_enter_to_continue()
            return

        # 展示列表
        print()
        for i, p in enumerate(builtins, 1):
            desc = p.get("description", "")
            console.print(
                f"  [{Theme.HIGHLIGHT}]{i}.[/{Theme.HIGHLIGHT}] "
                f"[bold]{p['name']}[/bold]"
            )
            if desc:
                console.print(f"     [{Theme.MUTED}]{desc}[/{Theme.MUTED}]")

        print()
        valid_keys = [str(i) for i in range(1, len(builtins) + 1)] + ["0"]
        choice = await self._get_choice(
            f"选择预设查看详情 [1-{len(builtins)}, 0=返回]",
            valid_keys=valid_keys,
        )

        if choice == "0":
            return

        # 显示详情
        idx = int(choice) - 1
        preset = builtins[idx]

        console.clear()
        print_header(f"预设详情: {preset['name']}", subtitle=preset.get("description", ""))

        # 系统提示词
        system_prompt = preset.get("system_prompt", "")
        console.print()
        console.print(f"  [{Theme.PRIMARY}]系统提示词:[/{Theme.PRIMARY}]")
        console.print()
        # 用 Panel 展示长文本
        from rich.text import Text
        prompt_text = Text(system_prompt.strip())
        console.print(Panel(
            prompt_text,
            border_style=Theme.MUTED,
            padding=(1, 2),
        ))

        print()
        print_info("内置预设不可编辑或删除，所有用户共享")
        await self._press_enter_to_continue()

    async def _my_custom_presets(self) -> None:
        """管理个人自定义预设。

        子菜单：
        1. 查看预设详情
        2. 编辑预设（名称/描述/系统提示词）
        3. 删除预设

        需要当前已选择用户。
        """
        preset_mgr = self._get_preset_manager()
        if preset_mgr is None:
            await self._press_enter_to_continue()
            return

        current_user_id = self._state.get("current_user_id")
        if not current_user_id:
            print_warning("请先在「用户管理」中选择一个用户")
            print_info("自定义预设属于个人，需要确定当前用户")
            await self._press_enter_to_continue()
            return

        # 循环管理界面
        while True:
            console.clear()
            print_header("我的自定义预设", subtitle="管理个人创建的预设角色")

            try:
                all_presets = await preset_mgr.list_presets(user_id=current_user_id)
            except Exception as e:
                print_error(f"获取预设列表失败: {e}")
                await self._press_enter_to_continue()
                return

            # 过滤出自定义预设（非内置）
            custom = [p for p in all_presets if not p.get("is_builtin")]

            if not custom:
                print_warning("暂无自定义预设")
                print_info("你可以在「新建自定义预设」中创建专属角色设定")
                print()
                await self._press_enter_to_continue()
                return

            # 展示列表
            print()
            for i, p in enumerate(custom, 1):
                desc = p.get("description", "")
                updated = p.get("updated_at", "")
                if isinstance(updated, str):
                    updated = updated.replace("T", " ")[:16]
                console.print(
                    f"  [{Theme.HIGHLIGHT}]{i}.[/{Theme.HIGHLIGHT}] "
                    f"[bold]{p['name']}[/bold]"
                )
                if desc:
                    console.print(f"     [{Theme.MUTED}]{desc}[/{Theme.MUTED}]")
                console.print(f"     [{Theme.MUTED}]更新于: {updated}[/{Theme.MUTED}]")

            print()
            valid_keys = [str(i) for i in range(1, len(custom) + 1)] + ["0"]
            choice = await self._get_choice(
                f"选择预设 [1-{len(custom)}, 0=返回]",
                valid_keys=valid_keys,
            )

            if choice == "0":
                return

            idx = int(choice) - 1
            preset = custom[idx]

            # 操作子菜单
            await self._custom_preset_actions(preset_mgr, preset)

    async def _custom_preset_actions(
        self, preset_mgr, preset: Dict[str, Any]
    ) -> None:
        """对单个自定义预设的操作子菜单。

        Args:
            preset_mgr: PresetManager 实例
            preset: 当前操作的预设字典
        """
        while True:
            console.clear()
            print_header(f"预设: {preset['name']}", subtitle=preset.get("description", ""))

            # 显示系统提示词摘要
            system_prompt = preset.get("system_prompt", "")
            preview = system_prompt[:120] + "..." if len(system_prompt) > 120 else system_prompt
            console.print(Panel(
                preview,
                title="系统提示词",
                border_style=Theme.MUTED,
                padding=(1, 2),
            ))

            options = [
                _opt("1", "查看完整提示词", ""),
                _opt("2", "编辑预设", "修改名称/描述/系统提示词"),
                _opt("3", "删除预设", "永久删除此自定义预设"),
                _opt("0", "返回", ""),
            ]

            print()
            print_menu_options(options)
            print()

            choice = await self._get_choice(
                "请选择操作 [0-3]", valid_keys=["0", "1", "2", "3"]
            )

            if choice == "0":
                return

            if choice == "1":
                # 查看完整提示词
                console.clear()
                print_header(f"提示词: {preset['name']}", subtitle="完整系统提示词")
                from rich.text import Text
                console.print(Panel(
                    Text(system_prompt.strip()),
                    border_style=Theme.MUTED,
                    padding=(1, 2),
                ))
                print()
                await self._press_enter_to_continue()

            elif choice == "2":
                # 编辑预设
                await self._edit_custom_preset(preset_mgr, preset)
                # 重新获取最新数据
                updated = await preset_mgr.get_preset(preset["id"])
                if updated:
                    preset = updated
                else:
                    return  # 预设已被删除

            elif choice == "3":
                # 删除预设
                await self._delete_custom_preset(preset_mgr, preset)
                return  # 删除后返回上级

    async def _edit_custom_preset(
        self, preset_mgr, preset: Dict[str, Any]
    ) -> None:
        """编辑自定义预设。

        允许修改名称、描述、系统提示词。
        直接回车保留原值不修改。

        Args:
            preset_mgr: PresetManager 实例
            preset: 要编辑的预设字典
        """
        console.clear()
        print_header(f"编辑预设: {preset['name']}", subtitle="直接回车保留原值")

        # 1. 修改名称
        print_info(f"当前名称: {preset['name']}")
        new_name = await self._get_text_input("新名称（直接回车保留）: ")
        new_name = new_name.strip() if new_name else None

        # 2. 修改描述
        print()
        print_info(f"当前描述: {preset.get('description', '（无）')}")
        new_desc = await self._get_text_input("新描述（直接回车保留）: ")
        new_desc = new_desc.strip() if new_desc else None

        # 3. 修改系统提示词
        print()
        current_prompt = preset.get("system_prompt", "")
        preview = current_prompt[:80] + "..." if len(current_prompt) > 80 else current_prompt
        print_info(f"当前提示词: {preview}")
        new_prompt = await self._get_text_input("新提示词（直接回车保留）: ")
        new_prompt = new_prompt.strip() if new_prompt else None

        # 如果全部为空，表示不修改
        if new_name is None and new_desc is None and new_prompt is None:
            print()
            print_info("未做任何修改")
            await self._press_enter_to_continue()
            return

        # 4. 执行更新
        try:
            await preset_mgr.update_preset(
                preset["id"],
                name=new_name,
                description=new_desc,
                system_prompt=new_prompt,
            )
            print()
            print_success(f"预设 '{preset['name']}' 更新成功")
        except ValueError as e:
            print()
            print_error(str(e))

        await self._press_enter_to_continue()

    async def _delete_custom_preset(
        self, preset_mgr, preset: Dict[str, Any]
    ) -> None:
        """删除自定义预设。

        Args:
            preset_mgr: PresetManager 实例
            preset: 要删除的预设字典
        """
        print()
        print_warning(f"确认删除自定义预设 '{preset['name']}'？")
        print_info("此操作不可撤销")

        print()
        confirm = await self._get_choice(
            "输入 y 确认删除，n 取消",
            valid_keys=["y", "n"],
        )

        if confirm == "n":
            print_info("已取消")
            await self._press_enter_to_continue()
            return

        try:
            await preset_mgr.delete_preset(preset["id"])
            print()
            print_success(f"预设 '{preset['name']}' 已删除")
            # 如果删除的是当前选中的预设，清除状态
            if preset["id"] == self._state.get("current_preset_id"):
                preset_mgr.clear_preset()
                print_info("该预设为当前使用预设，已自动清除选择")
        except ValueError as e:
            print()
            print_error(str(e))

        await self._press_enter_to_continue()

    async def _create_custom_preset(self) -> None:
        """新建自定义预设。

        流程：
        1. 输入预设名称
        2. 输入描述（可选）
        3. 输入系统提示词
        4. 保存到数据库

        需要当前已选择用户。
        """
        console.clear()
        print_header("新建自定义预设", subtitle="创建专属的角色设定")

        preset_mgr = self._get_preset_manager()
        if preset_mgr is None:
            await self._press_enter_to_continue()
            return

        current_user_id = self._state.get("current_user_id")
        if not current_user_id:
            print_error("请先在「用户管理」中选择一个用户")
            print_info("自定义预设属于个人，需要确定当前用户")
            await self._press_enter_to_continue()
            return

        # 1. 输入名称
        print_info("请输入预设名称（1-100 字符）")
        name = await self._get_text_input("预设名称: ")
        name = name.strip()
        if not name:
            print_info("已取消（名称为空）")
            await self._press_enter_to_continue()
            return

        # 2. 输入描述
        print()
        print_info("请输入预设描述（可选，直接回车跳过）")
        description = await self._get_text_input("描述: ")
        description = description.strip()

        # 3. 输入系统提示词
        print()
        print_info("请输入系统提示词（必填，定义 AI 的角色行为）")
        print_info("提示：可以直接回车输入单行简短提示词")
        system_prompt = await self._get_text_input("系统提示词: ")
        system_prompt = system_prompt.strip()
        if not system_prompt:
            print_info("已取消（提示词为空）")
            await self._press_enter_to_continue()
            return

        # 4. 创建
        try:
            preset = await preset_mgr.create_preset(
                user_id=current_user_id,
                name=name,
                description=description,
                system_prompt=system_prompt,
            )
            print()
            print_success(f"自定义预设 '{preset['name']}' 创建成功")
        except ValueError as e:
            print()
            print_error(str(e))

        await self._press_enter_to_continue()

    async def _select_preset(self) -> None:
        """选择或取消预设。

        流程：
        1. 显示所有可见预设（内置 + 自定义）
        2. 标注当前选中的预设
        3. 用户按编号选择，或选择 0 取消使用预设
        4. 更新全局状态
        """
        console.clear()
        print_header("选择预设", subtitle="为当前会话选择一个角色预设")

        preset_mgr = self._get_preset_manager()
        if preset_mgr is None:
            await self._press_enter_to_continue()
            return

        current_user_id = self._state.get("current_user_id")
        current_preset_id = self._state.get("current_preset_id")

        # 获取所有可见预设
        try:
            all_presets = await preset_mgr.list_presets(user_id=current_user_id)
        except Exception as e:
            print_error(f"获取预设列表失败: {e}")
            await self._press_enter_to_continue()
            return

        if not all_presets:
            print_warning("暂无可用预设")
            print_info("请检查 config/presets.yaml 或创建自定义预设")
            await self._press_enter_to_continue()
            return

        # 归类展示
        builtins = [p for p in all_presets if p.get("is_builtin")]
        customs = [p for p in all_presets if not p.get("is_builtin")]

        print()
        if builtins:
            console.print(f"  [{Theme.PRIMARY}]── 系统内置预设 ──[/{Theme.PRIMARY}]")
            for i, p in enumerate(builtins, 1):
                marker = " ★" if p["id"] == current_preset_id else ""
                console.print(
                    f"  [{Theme.HIGHLIGHT}]{i}.[/{Theme.HIGHLIGHT}] "
                    f"[bold]{p['name']}[/bold]{marker}"
                    f"  [{Theme.MUTED}]{p.get('description', '')}[/{Theme.MUTED}]"
                )
            print()

        if customs:
            console.print(f"  [{Theme.PRIMARY}]── 自定义预设 ──[/{Theme.PRIMARY}]")
            offset = len(builtins)
            for i, p in enumerate(customs, offset + 1):
                marker = " ★" if p["id"] == current_preset_id else ""
                console.print(
                    f"  [{Theme.HIGHLIGHT}]{i}.[/{Theme.HIGHLIGHT}] "
                    f"[bold]{p['name']}[/bold]{marker}"
                    f"  [{Theme.MUTED}]{p.get('description', '')}[/{Theme.MUTED}]"
                )
            print()

        # 当前状态
        current_name = self._state.get("current_preset_name")
        if current_name:
            print_info(f"当前使用: {current_name}")
        else:
            print_info("当前未使用预设")

        print()
        total = len(all_presets)
        valid_keys = [str(i) for i in range(1, total + 1)] + ["0"]
        choice = await self._get_choice(
            f"选择预设 [1-{total}]，0=不使用预设",
            valid_keys=valid_keys,
        )

        if choice == "0":
            if current_preset_id:
                preset_mgr.clear_preset()
                print()
                print_success("已取消预设选择")
            else:
                print()
                print_info("当前未使用预设")
        else:
            idx = int(choice) - 1
            selected = all_presets[idx]
            preset_mgr.select_preset(selected)
            print()
            print_success(f"已选择预设: {selected['name']}")
            tag = "内置" if selected.get("is_builtin") else "自定义"
            print_info(f"类型: {tag}")

        await self._press_enter_to_continue()

    # ============================================================
    # 系统设置辅助方法
    # ============================================================

    async def _show_config_info(self) -> None:
        """显示当前配置信息摘要。"""
        console.clear()
        print_header("当前配置信息", subtitle="config.yaml 中的主要配置项")

        config = self._state.get("config")
        if config is None:
            print_warning("配置管理器尚未初始化")
            await self._press_enter_to_continue()
            return

        info_lines = [
            ("LLM 默认模型", config.model_name),
            ("API Base URL", config.api_base_url),
            ("流式输出", "是" if config.llm_streaming else "否"),
            ("超时时间", f"{config.llm_timeout}s"),
            ("最大重试", f"{config.llm_max_retries} 次"),
            ("存储类型", config.storage_type),
            ("环境", config.env),
            ("调试模式", "是" if config.debug else "否"),
        ]

        for label, value in info_lines:
            formatted_value = value if value else "[未设置]"
            console.print(f"  [{Theme.MUTED}]{label}:[/{Theme.MUTED}] [{Theme.PRIMARY}]{formatted_value}[/{Theme.PRIMARY}]")

        await self._press_enter_to_continue()

    async def _show_about(self) -> None:
        """显示关于信息。"""
        console.clear()
        from src import __version__

        print_header("关于 LangChain Chat", subtitle="基于 LangChain 的多轮会话系统")

        about_info = [
            ("版本", __version__),
            ("开发语言", "Python 3.10+"),
            ("架构模式", "分层架构（业务层 / 数据模型层 / 存储层 / UI 层）"),
            ("异步模式", "全链路 asyncio 异步"),
            ("核心框架", "LangChain + langchain-openai"),
            ("TUI 界面", "Rich + prompt_toolkit"),
            ("存储后端", "SQLite（默认）/ MySQL / File（可插拔切换）"),
            ("项目定位", "教学项目 + 生产可用的 LLM 对话系统"),
        ]

        for label, value in about_info:
            console.print(f"  [{Theme.MUTED}]{label}:[/{Theme.MUTED}] [{Theme.PRIMARY}]{value}[/{Theme.PRIMARY}]")

        console.print(f"\n  [{Theme.MUTED}]共 16 步（Step 0 ~ Step 15），当前第 2 步[/{Theme.MUTED}]")
        console.print(f"  [{Theme.MUTED}]核心里程碑: Step 7 — 第一次真正的多轮流式对话[/{Theme.MUTED}]")

        await self._press_enter_to_continue()

    # ============================================================
    # 交互辅助方法
    # ============================================================

    async def _get_choice(self, prompt_text: str, valid_keys: List[str]) -> str:
        """获取用户菜单选择。

        循环等待直到用户输入有效的选项按键。

        Args:
            prompt_text: 提示文字（显示在输入框上方）
            valid_keys: 有效选项按键列表，如 ["1", "2", "0"]

        Returns:
            用户选择的有效按键
        """
        # 构建底部提示
        toolbar_hint = f" 输入 {'/'.join(valid_keys)} 选择，Ctrl+C 退出"

        while True:
            try:
                choice = self._get_raw_input(
                    prompt_text,
                    bottom_toolbar=toolbar_hint,
                )
                choice = choice.strip()
                if choice in valid_keys:
                    return choice
                print_error(f"无效选择 '{choice}'，请输入 {'/'.join(valid_keys)}")
            except (KeyboardInterrupt, EOFError):
                # Ctrl+C → 返回最安全的默认值
                return valid_keys[-1]  # 通常是 "0"（返回/退出）

    async def _get_text_input(self, prompt_text: str) -> str:
        """获取用户文本输入。

        Args:
            prompt_text: 输入提示文字

        Returns:
            用户输入的文本
        """
        try:
            return self._get_raw_input(prompt_text)
        except (KeyboardInterrupt, EOFError):
            return ""

    def _get_raw_input(
        self,
        prompt_text: str,
        bottom_toolbar: Optional[str] = None,
    ) -> str:
        """获取用户原始输入（底层封装）。

        使用 prompt_toolkit 的 prompt() 函数替代 input()，
        提供历史记录、光标移动、粘贴等高级功能。

        关键设计：传入 in_thread=True 参数，使 prompt_toolkit
        在后台线程运行其事件循环，避免与主线程的 asyncio.run()
        发生嵌套冲突（"asyncio.run() cannot be called from a
        running event loop" 错误）。

        Args:
            prompt_text: 输入提示文字
            bottom_toolbar: 底部工具栏提示文字

        Returns:
            用户输入的原始文本
        """
        try:
            # in_thread=True: prompt_toolkit 在后台线程创建独立事件循环
            # 主线程阻塞等待，但不会触发嵌套 asyncio.run() 错误
            result = pt_prompt(
                f"{prompt_text}",
                style=_MENU_STYLE,
                bottom_toolbar=bottom_toolbar,
                in_thread=True,
                # 后续步骤可在此添加自动补全和历史记录
            )
            return str(result)
        except (EOFError, KeyboardInterrupt):
            return ""

    async def _press_enter_to_continue(self) -> None:
        """等待用户按 Enter 继续。

        在所有信息展示和 stub 提示后，暂停等待用户确认。
        这给用户时间阅读信息，而不是直接刷屏。
        """
        print()
        try:
            # in_thread=True: 避免嵌套事件循环冲突（同 _get_raw_input 说明）
            pt_prompt(
                "按 Enter 继续...",
                style=_MENU_STYLE,
                default="",
                in_thread=True,
            )
        except (EOFError, KeyboardInterrupt):
            pass

    # ============================================================
    # 状态显示辅助
    # ============================================================

    def _print_current_context(self) -> None:
        """在主菜单顶部显示当前上下文状态。

        展示当前活跃的用户、会话、模型和预设信息，
        让用户一目了然当前的工作上下文。
        """
        parts = []

        username = self._state.get("current_username")
        if username:
            parts.append(f"用户: [{Theme.HIGHLIGHT}]{username}[/{Theme.HIGHLIGHT}]")
        else:
            parts.append(f"用户: [{Theme.WARNING}]未选择[/{Theme.WARNING}]")

        session_title = self._state.get("current_session_title")
        if session_title:
            parts.append(f"会话: [{Theme.HIGHLIGHT}]{session_title}[/{Theme.HIGHLIGHT}]")

        model = self._state.get("current_model")
        if model:
            parts.append(f"模型: [{Theme.MUTED}]{model}[/{Theme.MUTED}]")

        preset = self._state.get("current_preset_name")
        if preset:
            parts.append(f"预设: [{Theme.MUTED}]{preset}[/{Theme.MUTED}]")

        if parts:
            console.print(f"  {' │ '.join(parts)}")
            console.print()
