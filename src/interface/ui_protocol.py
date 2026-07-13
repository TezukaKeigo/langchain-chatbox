"""
UI 协议接口 — 定义所有 UI 实现层必须遵循的抽象规范 + 未来功能扩展预留。

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

扩展预留说明：
    本文件末尾定义了以下未来功能的抽象接口（标记 🔮）：
    - MultiModelUI: 多模型并行对比
    - MultimodalUI: 图文上传
    - VoiceUI: 语音输入
    - ToolCallingUI: LLM Tool Calling
    - DebugUI: 调试面板
    这些接口在 Step 14 定义，供后续版本实现。
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


# ============================================================
# 扩展预留接口 — 未来功能定义（不要求当前版本实现）
# ============================================================
# 以下接口定义了项目未来可能扩展的功能方向。
# 在 Step 14 中预留，后续版本可逐步实现。
#
# 实现方式：
#   1. 当前版本（TUI）：不实现这些接口，标记为 🔮 预留
#   2. 未来版本（WebUI 或其他）：通过多重继承实现对应接口
#      class WebUIApp(AbstractUI, MultiModelUI, MultimodalUI, ...):
#          ...
# ============================================================


class MultiModelUI(ABC):
    """🔮 多模型并行对比接口（预留）。

    允许用户同时向多个模型发送同一问题，
    在 UI 中并排展示各模型的输出结果。

    典型使用场景：
    - 比较不同模型的回答质量
    - A/B 测试不同 prompt 对同一模型的效果
    - 教学演示（展示各模型差异）
    """

    @abstractmethod
    async def select_models_for_comparison(
        self, available_models: List[Dict[str, Any]]
    ) -> List[str]:
        """选择参与对比的模型列表。

        Args:
            available_models: 可用模型列表

        Returns:
            选中的模型名称列表（至少 2 个）
        """
        ...

    @abstractmethod
    async def compare_models(
        self,
        models: List[str],
        user_input: str,
        system_prompt: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """向多个模型发送同一问题并返回结果。

        Args:
            models: 参与对比的模型名称列表
            user_input: 用户输入文本
            system_prompt: 可选的系统提示词

        Returns:
            每个模型的结果列表：
            [{"model": str, "content": str, "tokens": int, "latency_ms": float}, ...]
        """
        ...

    @abstractmethod
    async def display_comparison(
        self, results: List[Dict[str, Any]]
    ) -> None:
        """渲染多模型对比结果。

        实现需支持：
        - 并排或上下分栏展示
        - 高亮差异部分
        - 显示各模型的 Token 和延迟

        Args:
            results: compare_models() 的返回结果
        """
        ...


class MultimodalUI(ABC):
    """🔮 多模态输入接口（预留）。

    支持用户在对话中上传图片、文件等非文本内容。
    需要 LLM 支持视觉模型（如 GPT-4o、Gemini Vision）。
    """

    @abstractmethod
    async def upload_image(self) -> Optional[Dict[str, Any]]:
        """上传图片附件。

        Returns:
            图片元信息：
            {
                "path": str,        # 本地路径或临时路径
                "format": str,      # "png" / "jpg" / "webp"
                "size_bytes": int,  # 文件大小
                "base64": str,      # base64 编码（用于 API 传输）
            }
            用户取消时返回 None
        """
        ...

    @abstractmethod
    async def upload_file(self, allowed_types: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """上传文件附件（PDF、TXT、代码等）。

        Args:
            allowed_types: 允许的文件扩展名列表，如 [".pdf", ".txt", ".py"]

        Returns:
            文件元信息字典；用户取消时返回 None
        """
        ...

    @abstractmethod
    async def preview_attachment(self, attachment: Dict[str, Any]) -> None:
        """预览附件内容。

        Args:
            attachment: upload_image / upload_file 的返回结果
        """
        ...


class VoiceUI(ABC):
    """🔮 语音输入输出接口（预留）。

    支持语音转文字输入（STT）和文字转语音输出（TTS）。
    需要接入语音服务（如 OpenAI Whisper API / Azure Speech）。
    """

    @abstractmethod
    async def start_voice_input(self) -> None:
        """开始语音录制。

        UI 显示录音状态指示（如波形动画）。
        """
        ...

    @abstractmethod
    async def stop_voice_input(self) -> Optional[str]:
        """停止录音并转文字。

        Returns:
            识别出的文本内容；识别失败时返回 None
        """
        ...

    @abstractmethod
    async def synthesize_speech(self, text: str, voice: str = "default") -> Optional[bytes]:
        """将文本转为语音（TTS）。

        Args:
            text: 需要朗读的文本
            voice: 语音风格

        Returns:
            音频数据（WAV/MP3 bytes）；失败时返回 None
        """
        ...

    @property
    @abstractmethod
    def is_voice_supported(self) -> bool:
        """当前环境是否支持语音功能。"""
        ...


class ToolCallingUI(ABC):
    """🔮 LLM Tool Calling 接口（预留）。

    支持 LLM 调用外部工具/函数（Function Calling）。
    例如：查询天气、搜索网页、执行代码等。

    参考：OpenAI Function Calling / LangChain Tool
    """

    @abstractmethod
    async def register_tool(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        handler: Any,  # callable
    ) -> str:
        """注册一个工具。

        Args:
            name: 工具名称（唯一标识）
            description: 工具功能描述（供 LLM 理解）
            parameters: JSON Schema 参数定义
            handler: 工具调用处理函数 async callable

        Returns:
            工具 ID
        """
        ...

    @abstractmethod
    async def unregister_tool(self, tool_id: str) -> bool:
        """注销工具。

        Args:
            tool_id: register_tool() 返回的工具 ID

        Returns:
            True 表示注销成功
        """
        ...

    @abstractmethod
    async def list_tools(self) -> List[Dict[str, Any]]:
        """列出所有已注册的工具。

        Returns:
            工具信息列表
        """
        ...

    @abstractmethod
    async def on_tool_call(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """LLM 发起工具调用时的回调。

        由引擎层调用，通知 UI 层展示工具调用状态。

        Args:
            tool_name: 被调用的工具名称
            arguments: LLM 传入的参数

        Returns:
            工具执行结果
        """
        ...


class DebugUI(ABC):
    """🔮 调试面板接口（预留）。

    提供开发者调试功能：
    - 查看完整 LLM 请求/响应
    - Token 使用趋势图
    - 各模块日志实时查看
    - 消息上下文可视化
    """

    @abstractmethod
    async def enable_debug_panel(self) -> None:
        """开启调试面板。

        在 UI 中展示额外的调试信息区域。
        """
        ...

    @abstractmethod
    async def disable_debug_panel(self) -> None:
        """关闭调试面板。"""
        ...

    @abstractmethod
    async def show_request_debug(
        self, messages: List[Dict[str, Any]], model: str, token_count: int
    ) -> None:
        """显示单次 LLM 请求的调试信息。

        Args:
            messages: 发送给 LLM 的完整消息列表
            model: 使用的模型
            token_count: 预估的 prompt token 数
        """
        ...

    @abstractmethod
    async def show_response_debug(
        self, content: str, usage: Dict[str, int], latency_ms: float
    ) -> None:
        """显示单次 LLM 响应的调试信息。

        Args:
            content: 完整回复文本
            usage: Token 用量详情
            latency_ms: 响应延迟（毫秒）
        """
        ...

    @property
    @abstractmethod
    def is_debug_enabled(self) -> bool:
        """调试面板是否已开启。"""
        ...
