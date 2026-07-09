"""
对话视图 — TUI 聊天界面的核心交互组件。

职责：
- 展示对话记录（用户消息 + AI 回复）
- 处理用户输入（单行/多行）
- 流式输出 AI 回复（逐 token 渲染）
- 显示 Token 用量统计

当前状态（Step 2）：
  本模块为骨架占位，提供基本的对话框架和方法签名。
  实际的 LLM 对话功能将在 Step 6（对话引擎）和
  Step 7（TUI 对话对接）中实现。

实现细节：
  - 使用 prompt_toolkit 获取高质量用户输入
  - 使用 Rich 进行 Markdown 渲染和流式输出
  - 支持多行输入（用户需要时可切换到多行模式）
"""

from typing import Any, Dict, Optional


class ChatView:
    """对话视图 — TUI 聊天的界面管理器。

    Step 2 当前为 stub 占位实现。
    完整功能在 Step 6-7 中实现。

    Attributes:
        state: 共享的应用状态字典（当前用户、会话等）
    """

    def __init__(self, state: Dict[str, Any]) -> None:
        """初始化对话视图。

        Args:
            state: 应用全局状态字典，包含：
                - current_user_id: 当前用户 ID
                - current_username: 当前用户名
                - current_session_id: 当前会话 ID
                - current_session_title: 当前会话标题
                - current_model: 当前使用的模型
                - current_preset_id: 当前使用的预设 ID
        """
        self._state = state

    async def render(self) -> None:
        """渲染对话界面主循环。

        当前为占位实现 — 打印提示信息。
        完整实现将在 Step 7 完成，届时会：
        1. 显示对话历史
        2. 等待用户输入
        3. 调用 ChatEngine 进行流式对话
        4. 实时渲染 AI 回复
        5. 显示 Token 用量
        6. 自动保存消息到数据库
        """
        from .widgets import console, print_header, print_info

        console.clear()
        print_header(
            "开始对话",
            subtitle="Step 7 将在此实现完整的实时流式对话功能",
        )

        # 检查前置条件：是否有当前用户
        current_user = self._state.get("current_username")
        if not current_user:
            print_info("请先在「用户管理」中创建或选择一个用户。")
            return

        # 显示当前上下文信息
        session_title = self._state.get("current_session_title", "（无活跃会话）")
        model = self._state.get("current_model", "未设置")
        preset_name = self._state.get("current_preset_name", "无")

        print_info(f"当前用户: {current_user}")
        print_info(f"当前会话: {session_title}")
        print_info(f"使用模型: {model}")
        print_info(f"角色预设: {preset_name}")
        print()
        print_info("对话功能将在 Step 7（核心里程碑）中实现")
        print_info("届时支持多轮流式对话、Token 统计、自动保存")
        print()
        print_info("按 Enter 返回主菜单...")

        # 等待用户按键（模拟 input 的阻塞效果）
        try:
            from prompt_toolkit import prompt
            prompt("", default="")
        except (ImportError, EOFError):
            pass

    # ============================================================
    # 预留接口 — 后续步骤实现
    # ============================================================

    async def append_user_message(self, content: str) -> None:
        """添加用户消息到对话视图（预留）。

        Args:
            content: 用户输入的消息内容
        """
        pass

    async def append_ai_message_start(self) -> None:
        """开始 AI 消息输出（预留）。"""
        pass

    async def append_ai_chunk(self, chunk: str) -> None:
        """追加 AI 消息的流式片段（预留）。

        Args:
            chunk: 单个 token 文本
        """
        pass

    async def append_ai_message_end(self) -> None:
        """结束 AI 消息输出（预留）。"""
        pass

    async def show_token_stats(
        self,
        round_prompt: int,
        round_completion: int,
        total_prompt: int,
        total_completion: int,
    ) -> None:
        """显示 Token 用量统计（预留）。

        Args:
            round_prompt: 本轮 prompt tokens
            round_completion: 本轮 completion tokens
            total_prompt: 会话累计 prompt tokens
            total_completion: 会话累计 completion tokens
        """
        pass
