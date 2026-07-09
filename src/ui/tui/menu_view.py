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

当前状态（Step 2）：
  除主菜单外的所有操作均为 stub 占位 — 显示"将在 Step X 中实现"提示。
  用户管理和预设管理的部分基础交互在 Step 4-5 实现。
  会话管理在 Step 7-8 实现。
"""

from typing import Any, Dict, List, Optional

from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.styles import Style

from .widgets import (
    Theme,
    console,
    print_error,
    print_header,
    print_info,
    print_menu_options,
    print_success,
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
                await self._stub_create_user()
            elif choice == "2":
                await self._stub_switch_user()
            elif choice == "3":
                await self._stub_delete_user()
            elif choice == "4":
                await self._stub_list_users()

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
        Step 2 中所有操作均为 stub 占位，
        完整实现将在 Step 5 完成。

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

            stub_messages = {
                "1": "系统内置预设浏览将在 Step 5 中实现。届时将展示：翻译助手、代码专家、创意写手、英语老师等角色",
                "2": "个人自定义预设管理将在 Step 5 中实现",
                "3": "新建自定义预设功能将在 Step 5 中实现",
                "4": "选择预设功能将在 Step 5 中实现",
            }
            print_info(stub_messages[choice])
            await self._press_enter_to_continue()

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
    # Stub 占位方法 — 用户管理
    # ============================================================

    async def _stub_create_user(self) -> None:
        """Stub: 创建新用户。

        Step 4 将实现完整的用户创建逻辑：
        1. 提示输入用户名
        2. 校验唯一性
        3. 写入数据库
        4. 自动设置为当前用户
        """
        console.clear()
        print_header("创建新用户", subtitle="Step 4 将实现完整的用户管理系统")

        print_info("请输入用户名（当前为演示模式）:")
        try:
            username = await self._get_text_input("用户名: ")
            if username:
                print_warning(f"用户名 '{username}' 暂未实际创建")
                print_info("用户创建功能将在 Step 4 中实现")
                print_info("届时将校验唯一性并持久化到数据库")
            else:
                print_info("已取消")
        except (KeyboardInterrupt, EOFError):
            print_info("已取消")

        await self._press_enter_to_continue()

    async def _stub_switch_user(self) -> None:
        """Stub: 切换用户。"""
        console.clear()
        print_header("切换用户", subtitle="Step 4 将实现完整的用户切换功能")
        print_info("用户列表和切换功能将在 Step 4 中实现")
        print_info("届时将展示所有已注册用户并可选择切换")
        await self._press_enter_to_continue()

    async def _stub_delete_user(self) -> None:
        """Stub: 删除用户。"""
        console.clear()
        print_header("删除用户", subtitle="Step 4 将实现用户删除功能")
        print_warning("此操作将删除用户及其所有关联数据")
        print_info("Step 4 将实现完整的二次确认和数据清理流程")
        await self._press_enter_to_continue()

    async def _stub_list_users(self) -> None:
        """Stub: 用户列表。"""
        console.clear()
        print_header("用户列表", subtitle="Step 4 将展示所有已注册用户")
        print_info("用户列表功能将在 Step 4 与 SQLite 数据库对接中实现")
        print_info("届时将以表格形式展示：用户名 / 默认模型 / 创建时间")
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
