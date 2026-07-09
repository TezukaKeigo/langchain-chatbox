"""
UI 协议接口 — 定义所有 UI 实现层必须遵循的抽象规范。

设计目的：
1. **解耦业务与 UI**：核心业务层只依赖此协议，不依赖具体 UI 实现
2. **多 UI 支持**：TUI 和 WebUI 通过实现同一接口对接业务层
3. **未来扩展**：新增 UI 类型（如 REST API、桌面 GUI）只需实现此接口

依赖关系：
    业务层(core) ──依赖──▶ 接口层(interface/ui_protocol.py)
                                ▲
                    实现 (implements)
                            ╱       ╲
                TUI (ui/tui)         WebUI (ui/web)

使用方式：
    class TUIApp(AbstractUI):
        async def start(self) -> None:
            ...
        async def display_message(self, content: str) -> None:
            ...
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class AbstractUI(ABC):
    """UI 实现的抽象协议。

    所有 UI 实现（TUI / WebUI / API 等）必须实现此接口的全部方法。
    业务层通过此接口与 UI 交互，无需知道具体 UI 类型。
    """

    # ============================================================
    # 生命周期
    # ============================================================

    @abstractmethod
    async def start(self) -> None:
        """启动 UI 主循环。

        这是 UI 的入口方法，负责：
        - 初始化 UI 组件
        - 显示启动画面
        - 进入主事件循环
        - 处理用户输入直到退出

        TUI 实现中对应 app.run() 或 app.start() 方法。
        WebUI 实现中对应 FastAPI 的 uvicorn.run()。
        """
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """关闭 UI，释放资源。

        负责：
        - 保存状态
        - 关闭连接
        - 清理临时资源
        """
        ...

    # ============================================================
    # 消息显示
    # ============================================================

    @abstractmethod
    async def display_message(self, role: str, content: str) -> None:
        """向用户显示一条消息。

        Args:
            role: 消息角色（human / ai / system）
            content: 消息正文内容
        """
        ...

    @abstractmethod
    async def display_streaming_chunk(self, chunk: str) -> None:
        """显示流式输出的单个 token 片段。

        流式场景：LLM 生成一个 token，UI 立即渲染一个 token，
        不等完整回复。这要求 UI 支持增量输出。

        Args:
            chunk: 单个 token 文本片段
        """
        ...

    @abstractmethod
    async def display_streaming_end(self) -> None:
        """流式输出结束的信号。

        UI 收到此信号后可以进行：
        - 换行或添加结束标记
        - 更新 Token 用量统计显示
        - 恢复正常的输入提示
        """
        ...

    # ============================================================
    # 用户输入
    # ============================================================

    @abstractmethod
    async def get_user_input(self, prompt_text: str = "") -> str:
        """获取用户文本输入。

        Args:
            prompt_text: 输入提示文字

        Returns:
            用户输入的文本
        """
        ...

    @abstractmethod
    async def get_user_confirmation(self, message: str) -> bool:
        """获取用户确认（是/否）。

        用于删除用户、删除会话等不可逆操作前的二次确认。

        Args:
            message: 确认提示信息

        Returns:
            True 表示用户确认，False 表示取消
        """
        ...

    # ============================================================
    # 菜单与选择
    # ============================================================

    @abstractmethod
    async def show_menu(
        self,
        title: str,
        options: List[Dict[str, Any]],
        allow_back: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """显示菜单并获取用户选择。

        Args:
            title: 菜单标题
            options: 菜单选项列表，每项包含 {'key': str, 'label': str, 'description': str}
            allow_back: 是否允许返回上一级

        Returns:
            用户选择的选项字典；返回上级时返回 None
        """
        ...

    # ============================================================
    # 状态显示
    # ============================================================

    @abstractmethod
    async def show_status(self, message: str, status_type: str = "info") -> None:
        """显示状态信息。

        Args:
            message: 状态消息
            status_type: 状态类型（info / success / warning / error）
        """
        ...

    @abstractmethod
    async def show_token_usage(
        self, prompt_tokens: int, completion_tokens: int, total_prompt: int, total_completion: int
    ) -> None:
        """显示 Token 用量统计。

        Args:
            prompt_tokens: 本轮 prompt tokens
            completion_tokens: 本轮 completion tokens
            total_prompt: 会话累计 prompt tokens
            total_completion: 会话累计 completion tokens
        """
        ...

    # ============================================================
    # 上下文管理
    # ============================================================

    @abstractmethod
    def set_current_user(self, user_id: str, username: str) -> None:
        """设置当前活跃用户。

        Args:
            user_id: 用户 ID
            username: 用户名（用于 UI 显示）
        """
        ...

    @abstractmethod
    def set_current_session(self, session_id: str, title: str) -> None:
        """设置当前活跃会话。

        Args:
            session_id: 会话 ID
            title: 会话标题（用于 UI 显示）
        """
        ...

    @abstractmethod
    def clear_current_session(self) -> None:
        """清除当前活跃会话状态。"""
        ...
