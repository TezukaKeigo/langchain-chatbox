"""
TUI 主应用 — 菜单路由、状态管理、主事件循环。

本模块是 TUI 层的大脑，负责：
1. 初始化所有视图组件（MenuView、ChatView）
2. 管理应用全局状态（当前用户、会话、模型等）
3. 实现菜单路由（根据用户选择分发到对应视图）
4. 维护主事件循环（显示菜单 → 执行操作 → 返回菜单）
5. 管理存储后端和业务组件的生命周期

设计模式：
- 中介者模式：App 协调各视图，视图之间不直接通信
- 状态容器模式：state 字典作为唯一的状态真相源

依赖关系：
    App
    ├── StorageBackend（数据持久化）
    ├── UserManager（用户业务逻辑，Step 4）
    ├── PresetManager（预设管理，Step 5）
    ├── MenuView（菜单渲染与交互）
    ├── ChatView（对话界面，Step 7 对接）
    └── state（共享状态字典）
"""

import asyncio
import sys
from typing import Any, Dict, Optional

from .widgets import console, print_error, print_header, print_info
from .menu_view import MenuView
from .chat_view import ChatView


class TUIApp:
    """TUI 主应用程序。

    负责 TUI 的全局状态管理和菜单路由。
    在 Step 4 中集成存储后端和用户管理。
    在 Step 5 中集成预设管理。

    使用方式：
        config = ConfigManager()
        storage = await StorageFactory.create(config)
        app = TUIApp(config_manager=config, storage=storage)
        await app.run()

    Attributes:
        config: ConfigManager 实例（全局配置）
        storage: StorageBackend 实例（数据持久化）
        _state: 应用全局状态字典
        _menu_view: 菜单视图管理器
        _chat_view: 对话视图管理器
        _running: 主循环运行标志
    """

    def __init__(
        self,
        config_manager: Optional[Any] = None,
        storage: Optional[Any] = None,
    ) -> None:
        """初始化 TUI 应用。

        Args:
            config_manager: ConfigManager 实例，提供全局配置访问。
                           可选；未提供时，TUI 使用默认值。
            storage: StorageBackend 实例，提供数据持久化。
                     Step 4 起传入，用于用户管理等数据操作。
        """
        self.config = config_manager
        self.storage = storage

        # ----- 全局共享状态 -----
        # state 字典是各视图之间的唯一通信通道
        # 任何视图都可以读写 state，但约定：
        #   - 读取：随时可以
        #   - 写入：仅在自己的处理函数中写入自己的 key
        self._state: Dict[str, Any] = {
            # 当前用户
            "current_user_id": None,
            "current_username": None,
            # 当前会话
            "current_session_id": None,
            "current_session_title": None,
            # 当前设置
            "current_model": None,
            "current_preset_id": None,
            "current_preset_name": None,
            # 配置引用（只读）
            "config": config_manager,
            # 业务组件（Step 4+）
            "user_manager": None,
            # 业务组件（Step 5+）
            "preset_manager": None,
            # 业务组件（Step 7+）
            "session_manager": None,
            "chat_engine": None,
        }

        # 初始化默认值（从配置中读取）
        if config_manager:
            self._state["current_model"] = config_manager.model_name

        # ----- 业务组件 -----
        # Step 4: 如果提供了存储后端，初始化用户管理器
        if storage is not None:
            from src.core.user_manager import UserManager
            self._state["user_manager"] = UserManager(storage, self._state)

        # Step 5: 初始化预设管理器
        if storage is not None and config_manager is not None:
            from src.core.preset_manager import PresetManager
            self._state["preset_manager"] = PresetManager(
                storage, self._state, config_manager
            )

        # Step 7: 初始化会话管理器
        if storage is not None and config_manager is not None:
            from src.core.session_manager import SessionManager
            self._state["session_manager"] = SessionManager(
                storage, self._state, config_manager
            )

        # ----- 视图组件 -----
        self._menu_view = MenuView(self._state)
        self._chat_view = ChatView(self._state)

        # ----- 运行状态 -----
        self._running = False

    # ============================================================
    # 主循环
    # ============================================================

    async def run(self) -> None:
        """启动 TUI 主事件循环。

        循环流程：
        1. 显示主菜单
        2. 获取用户选择
        3. 路由到对应子菜单或视图
        4. 子菜单/视图返回后回到步骤 1
        5. 用户选择"退出"时结束循环

        异常处理：
        - Ctrl+C → 优雅退出
        - 未预期异常 → 显示错误并尝试恢复
        """
        self._running = True

        # Step 5: 同步内置预设到数据库（幂等操作）
        preset_mgr = self._state.get("preset_manager")
        if preset_mgr is not None:
            try:
                loaded = await preset_mgr.load_builtin_presets()
                if loaded > 0:
                    # 仅在首次加载时打印提示（静默启动）
                    pass
            except Exception as e:
                # 预设加载失败不阻止程序启动
                pass

        # 显示欢迎画面
        console.clear()
        print_header(
            "LangChain Chat",
            subtitle="正在启动...",
        )

        try:
            while self._running:
                # 主菜单 → 返回操作指令
                action = await self._menu_view.show_main_menu()

                # 路由分发
                await self._route(action)

        except KeyboardInterrupt:
            # 用户按下 Ctrl+C
            console.print()
            print_info("收到退出信号，正在退出...")
        except Exception as e:
            # 区分终端兼容性错误与其他未预期异常
            error_type = type(e).__name__
            if "Console" in error_type or "ScreenBuffer" in error_type:
                # prompt_toolkit 在 Git Bash / Cygwin 等非标准终端中可能失败
                print_error(
                    "终端兼容性问题 — 当前终端不支持完整的控制台功能。\n"
                    "  请尝试以下终端：\n"
                    "  • cmd.exe（命令提示符）\n"
                    "  • PowerShell\n"
                    "  • Windows Terminal\n"
                    "  • 或在 Git Bash 中使用: winpty uv run python src/main.py"
                )
            else:
                # 其他未预期的异常：显示但不让程序崩溃
                print_error(f"发生未预期错误: {e}")
                console.print_exception(show_locals=False)
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        """优雅关闭应用。

        保存状态、关闭存储连接、清理资源。
        """
        self._running = False

        # 关闭存储后端（释放数据库连接等资源）
        if self.storage is not None:
            try:
                await self.storage.close()
            except Exception as close_err:
                # 关闭失败不应阻止程序退出
                pass

        console.clear()
        print_header("感谢使用 LangChain Chat", subtitle="再见！")
        print()

    # ============================================================
    # 路由分发
    # ============================================================

    async def _route(self, action: str) -> None:
        """根据主菜单选择分发到对应的子视图。

        路由表：
            user_menu    → 用户管理子菜单
            session_menu → 会话管理子菜单
            preset_menu  → 预设管理子菜单
            start_chat   → 对话界面
            settings     → 系统设置
            exit         → 退出程序

        Args:
            action: 操作指令字符串（来自 MenuView.show_main_menu）
        """
        # ----- 路由映射表 -----
        route_handlers = {
            "user_menu":    self._handle_user_menu,
            "session_menu": self._handle_session_menu,
            "preset_menu":  self._handle_preset_menu,
            "start_chat":   self._handle_chat,
            "settings":     self._handle_settings,
            "exit":         self._handle_exit,
        }

        handler = route_handlers.get(action)
        if handler:
            await handler()
        else:
            print_error(f"未知操作: {action}")

    # ============================================================
    # 路由处理函数
    # ============================================================

    async def _handle_user_menu(self) -> None:
        """处理用户管理菜单。"""
        await self._menu_view.show_user_menu()

    async def _handle_session_menu(self) -> None:
        """处理会话管理菜单。

        Step 8: 会话菜单可能返回 "start_chat"，
        表示用户新建/加载会话后要立即进入对话。
        """
        action = await self._menu_view.show_session_menu()
        if action == "start_chat":
            await self._handle_chat()

    async def _handle_preset_menu(self) -> None:
        """处理预设管理菜单。"""
        await self._menu_view.show_preset_menu()

    async def _handle_chat(self) -> None:
        """处理开始对话。

        Step 7 核心里程碑：
        1. 创建 ChatEngine 实例
        2. 加载当前用户的预设（如有）
        3. 获取或创建会话
        4. 加载历史消息
        5. 进入对话循环（输入 → 流式输出 → 保存）

        前置条件检查：必须已选择用户。
        """
        if not self._state.get("current_username"):
            console.clear()
            print_header("开始对话", subtitle="前置条件检查")
            print_error("请先在「用户管理」中创建或选择一个用户")
            print_info("对话功能需要关联用户才能保存会话记录")
            print()
            await self._menu_view._press_enter_to_continue()
            return

        # 检查 API Key（优先使用当前模型专属 key，回退到全局 key）
        if self.config:
            current_model = self._state.get("current_model", self.config.model_name)
            model_cfg = self.config.get_model_config(current_model)
            if not model_cfg["api_key"]:
                console.clear()
                print_header("开始对话", subtitle="配置检查")
                print_error(f"模型 '{current_model}' 的 API Key 未配置")
                print_info("请在 .env 文件中配置对应的 API_KEY 环境变量")
                print_info("参考 .env.example 文件进行配置")
                print()
                await self._menu_view._press_enter_to_continue()
                return

        if not self.config:
            console.clear()
            print_header("开始对话", subtitle="配置检查")
            print_error("配置管理器未初始化")
            print()
            await self._menu_view._press_enter_to_continue()
            return

        from src.core.chat_engine import ChatEngine

        session_mgr = self._state.get("session_manager")

        # 创建对话引擎
        engine = ChatEngine(self.config, self._state)

        # 加载当前选中的预设（如有）
        preset_id = self._state.get("current_preset_id")
        if preset_id:
            try:
                preset = await self.storage.get_preset(preset_id)
                if preset:
                    engine.set_system_prompt(preset["system_prompt"])
            except Exception:
                pass  # 预设加载失败不阻止对话

        try:
            await self._chat_view.render(engine, session_mgr)
        except Exception as e:
            console.print()
            print_error(f"对话异常: {e}")

    async def _handle_settings(self) -> None:
        """处理系统设置。"""
        await self._menu_view.show_settings_menu()

    async def _handle_exit(self) -> None:
        """处理退出请求。"""
        self._running = False
