"""
对话视图 — TUI 聊天界面的核心交互组件。

本模块负责：
1. 展示对话记录（历史消息 + 实时流式输出）
2. 处理用户输入（单行 Enter 发送，Alt+Enter 多行模式）
3. 流式渲染 AI 回复（逐 token 打字机效果）
4. 每轮对话后自动保存到数据库
5. 显示 Token 用量统计（本轮 + 累计）
6. 首条消息自动生成会话标题

当前状态（Step 7）：
  核心里程碑 — 完整的流式多轮对话功能已实现。

交互约定：
  - 输入消息后按 Enter 发送
  - Alt+Enter 或 Esc+Enter 进入多行编辑模式
  - 输入 /exit 或 /quit 退出对话
  - 输入 /new 开始新会话
  - 输入 /clear 清空当前会话历史
  - Ctrl+C 中断当前 AI 回复

设计原则：
  - ChatView 只负责界面渲染和用户交互
  - 对话逻辑由 ChatEngine 处理
  - 持久化由 SessionManager 处理
"""

from typing import Any, Dict, Optional, TYPE_CHECKING

from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.styles import Style as PTStyle
from rich.panel import Panel
from rich.text import Text

from .widgets import (
    Theme,
    console,
    print_error,
    print_info,
    print_success,
    print_warning,
    truncate,
)

if TYPE_CHECKING:
    from src.core.chat_engine import ChatEngine
    from src.core.session_manager import SessionManager


# ============================================================
# prompt_toolkit 样式
# ============================================================

_CHAT_INPUT_STYLE = PTStyle.from_dict({
    "prompt": "bold #00ff00",
    "": "#ffffff",
    "bottom-toolbar": "bg:#222222 #888888",
})


# ============================================================
# ChatView
# ============================================================

class ChatView:
    """对话视图 — TUI 聊天的界面管理器。

    提供完整的对话交互体验：
    - 历史消息回显
    - 流式 AI 输出
    - 自动持久化
    - Token 统计展示

    Attributes:
        _state: 共享的应用状态字典
        _engine: ChatEngine 实例（由外部注入）
        _session_mgr: SessionManager 实例（由外部注入）
    """

    def __init__(self, state: Dict[str, Any]) -> None:
        """初始化对话视图。

        Args:
            state: 应用全局状态字典
        """
        self._state = state

    # ============================================================
    # 主渲染入口
    # ============================================================

    async def render(self, engine: "ChatEngine", session_mgr: "SessionManager") -> None:
        """渲染对话界面并启动主循环。

        这是对话视图的唯一入口。由 App._handle_chat() 调用。

        流程：
        1. 获取或创建会话
        2. 加载历史消息（如有）
        3. 打印对话头部信息
        4. 进入「输入 → 流式输出 → 保存」循环
        5. 用户退出时返回

        Args:
            engine: 对话引擎实例（已配置系统提示词）
            session_mgr: 会话管理器实例
        """
        self._engine = engine
        self._session_mgr = session_mgr

        user_id = self._state["current_user_id"]
        model_name = self._state.get("current_model", "unknown")
        preset_id = self._state.get("current_preset_id")

        # Step 1: 获取或创建会话
        session = await session_mgr.get_or_create_session(
            user_id=user_id,
            model_name=model_name,
            preset_id=preset_id,
        )
        session_id = session["id"]

        # Step 2: 加载历史消息
        messages = await session_mgr.load_messages(session_id)
        is_new_session = len(messages) == 0

        # 将历史消息加载到引擎（实现多轮对话上下文）
        if messages:
            engine.load_history(messages)

        # 同步引擎的 Token 统计与会话记录
        session_info = await session_mgr.get_session_info(session_id)
        if session_info:
            saved_prompt = session_info.get("total_prompt_tokens", 0)
            saved_completion = session_info.get("total_completion_tokens", 0)
            if saved_prompt > 0 or saved_completion > 0:
                engine._total_prompt_tokens = saved_prompt
                engine._total_completion_tokens = saved_completion

        # Step 3: 打印对话界面头部
        self._print_chat_header(session, messages)

        # Step 4: 主对话循环
        try:
            await self._chat_loop(session, is_new_session)
        finally:
            self._engine = None
            self._session_mgr = None

    # ============================================================
    # 对话循环
    # ============================================================

    async def _chat_loop(self, session: Dict[str, Any], is_new_session: bool) -> None:
        """主对话循环：输入 → 流式输出 → 保存。

        Args:
            session: 当前会话数据字典
            is_new_session: 是否为新会话（用于判断是否需要自动标题）
        """
        session_id = session["id"]

        while True:
            # 获取用户输入
            user_input = await self._get_user_input()

            if user_input is None:
                break

            user_input = user_input.strip()

            # 特殊命令处理
            if user_input.lower() in ("/exit", "/quit"):
                print_info("退出对话，返回主菜单...")
                break

            if user_input.lower() == "/new":
                await self._handle_new_session()
                return

            if user_input.lower() == "/clear":
                self._engine.clear_history()
                console.clear()
                self._print_chat_header(session, [])
                print_info("对话历史已清空（会话记录仍保留在数据库中）")
                console.print()
                continue

            if user_input.lower() == "/model":
                await self._switch_model_in_chat()
                console.clear()
                self._print_chat_header(session, messages=[])
                print_info("模型已切换，可以继续对话")
                console.print()
                continue

            if not user_input:
                continue

            # --- 自动标题（仅新会话的首条消息） ---
            if is_new_session and self._engine.message_count == 0:
                await self._session_mgr.auto_title(session_id, user_input)
                session["title"] = self._state.get("current_session_title", session["title"])
                is_new_session = False

            # --- 显示 AI 回复标签 ---
            console.print()
            self._print_role_label("AI", Theme.AI_ROLE)
            console.print()

            # --- 流式调用 ChatEngine ---
            full_response = ""

            try:
                async for chunk in self._engine.chat_stream(user_input):
                    if chunk["done"]:
                        self._print_token_stats(
                            round_prompt=chunk["prompt_tokens"],
                            round_completion=chunk["completion_tokens"],
                            round_total=chunk["total_tokens"],
                            total_prompt=self._engine.total_prompt_tokens,
                            total_completion=self._engine.total_completion_tokens,
                            total_all=self._engine.total_tokens,
                        )
                    else:
                        console.print(chunk["content"], end="", highlight=False)
                        full_response += chunk["content"]

                console.print()

            except KeyboardInterrupt:
                console.print()
                print_warning("AI 回复已被中断")
                if full_response:
                    from langchain_core.messages import AIMessage
                    self._engine._history.append(AIMessage(content=full_response))

            except Exception as e:
                console.print()
                print_error(f"LLM 调用失败: {e}")
                continue

            # --- 自动保存本轮对话 ---
            if full_response:
                try:
                    await self._session_mgr.auto_save_turn(
                        session_id=session_id,
                        user_message=user_input,
                        ai_response=full_response,
                        prompt_tokens=self._engine.last_prompt_tokens,
                        completion_tokens=self._engine.last_completion_tokens,
                    )
                except Exception as save_err:
                    print_error(f"消息保存失败: {save_err}")

            console.print()

    # ============================================================
    # 会话操作
    # ============================================================

    async def _handle_new_session(self) -> None:
        """创建新会话并在当前界面中开始。"""
        console.print()
        print_info("创建新会话...")
        self._engine.reset()
        self._session_mgr.clear_current_session()
        console.print()
        print_success("已切换到新会话")
        console.print()

    async def _switch_model_in_chat(self) -> None:
        """在对话中切换 LLM 模型（Step 10）。

        从配置的 available_models 中展示可选模型，
        用户选择后更新引擎和全局状态。
        切换后保留对话历史，使用新模型继续对话。
        """
        from prompt_toolkit import prompt as pt_prompt
        from prompt_toolkit.styles import Style as PTStyle

        config = self._state.get("config")
        if config is None:
            print_error("配置管理器尚未初始化")
            return

        available = config.available_models
        if not available:
            print_warning("未配置可用模型列表")
            return

        current_model = self._state.get("current_model", "")

        # 展示可用模型
        console.print()
        info = Text()
        info.append("  i ", style=Theme.MUTED)
        info.append("可用模型列表（输入编号切换，直接回车取消）:", style=Theme.MUTED)
        console.print(info)

        for i, m in enumerate(available, 1):
            name = m.get("name", "?")
            desc = m.get("description", "")
            is_current = name == current_model
            marker = " ★ 当前" if is_current else ""
            console.print(
                f"    [{Theme.HIGHLIGHT}]{i}.[/{Theme.HIGHLIGHT}] "
                f"[bold]{name}[/bold]{marker}"
                f"  [{Theme.MUTED}]{desc}[/{Theme.MUTED}]"
            )

        console.print()

        # 获取用户选择
        valid_keys = [str(i) for i in range(1, len(available) + 1)] + [""]
        _CHAT_MODEL_STYLE = PTStyle.from_dict({
            "prompt": "bold #ff00ff",
            "": "#ffffff",
        })

        try:
            choice = pt_prompt(
                [("class:prompt", f"  选择模型 [1-{len(available)}] > ")],
                style=_CHAT_MODEL_STYLE,
                default="",
                in_thread=True,
            )
        except (KeyboardInterrupt, EOFError):
            return

        choice = choice.strip()
        if not choice:
            print_info("已取消")
            return

        if choice not in valid_keys:
            print_error(f"无效选择: {choice}")
            return

        idx = int(choice) - 1
        selected = available[idx]
        new_model = selected.get("name", "")

        if new_model == current_model:
            print_info(f"已经是当前模型: {new_model}")
            return

        # 更新状态和引擎
        old_model = current_model
        self._state["current_model"] = new_model

        # 更新引擎的模型配置
        if hasattr(self._engine, "_current_model"):
            self._engine._current_model = new_model
            # 重新创建 LLM 实例以使用新模型的 API 配置
            if hasattr(self._engine, "_create_llm"):
                try:
                    self._engine._llm = self._engine._create_llm(new_model)
                except Exception:
                    pass  # 将在下次对话时延迟创建

        print_success(f"模型已切换: '{old_model}' → '{new_model}'")
        print_info("对话历史已保留，下一轮对话使用新模型")

    # ============================================================
    # 界面渲染辅助
    # ============================================================

    def _print_chat_header(
        self,
        session: Dict[str, Any],
        messages: list,
    ) -> None:
        """打印对话界面的头部信息。

        Args:
            session: 当前会话数据字典
            messages: 历史消息列表
        """
        console.clear()

        username = self._state.get("current_username", "未知用户")
        model = self._state.get("current_model", "unknown")
        preset = self._state.get("current_preset_name") or "无"
        session_title = session.get("title", "新会话")

        # 标题面板 — 使用 Text 对象避免 Rich markup 注入
        content = Text()
        content.append("LangChain Chat", style="bold " + Theme.PRIMARY)
        content.append("\n用户: ", style=Theme.MUTED)
        content.append(username, style=Theme.HIGHLIGHT)
        content.append(" | 模型: ", style=Theme.MUTED)
        content.append(model, style=Theme.HIGHLIGHT)
        content.append(" | 预设: ", style=Theme.MUTED)
        content.append(preset, style=Theme.HIGHLIGHT)
        content.append("\n会话: ", style=Theme.MUTED)
        content.append(session_title, style=Theme.HIGHLIGHT)

        panel = Panel(
            content,
            border_style=Theme.PRIMARY,
            padding=(1, 2),
        )
        console.print(panel)

        # 操作提示 — 使用 Text 对象
        hints = Text()
        hints.append("Enter 发送", style=Theme.MUTED)
        hints.append(" | /exit 退出", style=Theme.MUTED)
        hints.append(" | /new 新会话", style=Theme.MUTED)
        hints.append(" | /clear 清屏", style=Theme.MUTED)
        hints.append(" | /model 切换模型", style=Theme.MUTED)
        console.print(hints)
        console.print()

        # 显示历史消息数量
        if messages:
            info = Text()
            info.append("  i ", style=Theme.MUTED)
            info.append(f"已加载 {len(messages)} 条历史消息", style=Theme.MUTED)
            console.print(info)
            console.print()
            self._print_history_summary(messages)

    def _print_history_summary(self, messages: list) -> None:
        """回显历史消息摘要。

        Args:
            messages: 历史消息列表
        """
        recent = messages[-6:] if len(messages) > 6 else messages

        # 分隔线 — 使用 Text 对象避免 f-string + Rich markup 括号冲突
        sep = Text()
        sep.append("  ")
        sep.append(f"── 历史消息（最近 {len(recent)} 条）──", style=Theme.MUTED)
        console.print(sep)

        for msg in recent:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "human":
                self._print_chat_bubble("你", content, Theme.USER_ROLE)
            elif role == "ai":
                self._print_chat_bubble("AI", truncate(content, 120), Theme.AI_ROLE)

        footer = Text()
        footer.append("  ")
        footer.append("── 继续对话 ──", style=Theme.MUTED)
        console.print(footer)
        console.print()

    def _print_chat_bubble(self, sender: str, content: str, color: str) -> None:
        """打印一条聊天气泡。

        Args:
            sender: 发送者标签
            content: 消息内容
            color: 标签颜色
        """
        label = Text()
        label.append("  [", style=Theme.MUTED)
        label.append(sender, style="bold " + color)
        label.append("] ", style=Theme.MUTED)
        label.append(truncate(content.replace("\n", " "), 150), style=Theme.MUTED)
        console.print(label)

    @staticmethod
    def _print_role_label(role: str, color: str) -> None:
        """打印发送者角色标签。

        Args:
            role: 角色名称
            color: 标签颜色
        """
        label = Text()
        label.append("  [", style=Theme.MUTED)
        label.append(role, style="bold " + color)
        label.append("] ", style=Theme.MUTED)
        console.print(label)

    def _print_token_stats(
        self,
        round_prompt: int,
        round_completion: int,
        round_total: int,
        total_prompt: int,
        total_completion: int,
        total_all: int,
    ) -> None:
        """打印 Token 用量统计。

        Args:
            round_prompt: 本轮 prompt tokens
            round_completion: 本轮 completion tokens
            round_total: 本轮总 tokens
            total_prompt: 累计 prompt tokens
            total_completion: 累计 completion tokens
            total_all: 累计总 tokens
        """
        console.print()
        stats = Text()
        stats.append("  ", style=Theme.MUTED)
        stats.append("── Token 统计 ──", style=Theme.MUTED)
        if round_total > 0:
            stats.append(
                f"\n  本轮: prompt={round_prompt} completion={round_completion} "
                f"合计={round_total}",
                style=Theme.MUTED,
            )
        stats.append(
            f"\n  累计: prompt={total_prompt} completion={total_completion} "
            f"合计={total_all}",
            style=Theme.MUTED,
        )
        console.print(stats)

    # ============================================================
    # 用户输入
    # ============================================================

    async def _get_user_input(self) -> Optional[str]:
        """获取用户输入。

        使用 prompt_toolkit 提供高质量输入体验：
        - Enter 发送消息
        - Ctrl+C 取消当前输入并询问退出
        - Ctrl+D 退出对话

        Returns:
            用户输入文本；EOF/Ctrl+C 确认退出时返回 None
        """
        session_title = self._state.get("current_session_title", "新会话")

        try:
            user_input = pt_prompt(
                [("class:prompt", "  你 > ")],
                style=_CHAT_INPUT_STYLE,
                multiline=False,
                bottom_toolbar=(
                    "  [Enter] 发送  [/exit] 退出  [/new] 新会话  [/clear] 清屏  [/model] 切换模型"
                    f"    会话: {session_title}"
                ),
                in_thread=True,
            )
            return user_input

        except KeyboardInterrupt:
            console.print()
            try:
                confirm = pt_prompt(
                    [("class:prompt", "  确认退出对话? (y/n) > ")],
                    style=_CHAT_INPUT_STYLE,
                    default="n",
                    in_thread=True,
                )
                if confirm.strip().lower() == "y":
                    return None
                return ""
            except (KeyboardInterrupt, EOFError):
                return None

        except EOFError:
            return None
