"""
对话引擎 — LLM 调用 + Memory + 流式 + 超时重试 + Token 统计。

本模块是项目的核心，负责：
1. 封装 ChatOpenAI（兼容所有 OpenAI 格式的 API）
2. 管理多轮对话的消息历史（Memory）
3. 提供流式输出（逐 token 返回）
4. 自动统计每轮和累计的 Token 用量
5. 超时自动重试（通过 ChatOpenAI 内置机制）
6. 支持系统提示词（预设角色）
7. 支持运行时切换模型

设计原则：
- 引擎只负责 LLM 交互，不直接操作数据库
- 消息历史的持久化由上层（SessionManager，Step 7）负责
- 通过 state 字典与 TUI 层通信当前状态

使用方式：
    engine = ChatEngine(config, state)
    engine.set_system_prompt("你是一个翻译助手...")

    # 流式对话
    async for chunk in engine.chat_stream("你好"):
        print(chunk["content"], end="", flush=True)

    # 查看统计
    print(engine.get_stats())
"""

import time
from typing import Any, AsyncIterator, Dict, List, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

# ============================================================
# 错误类型
# ============================================================


class ChatEngineError(Exception):
    """对话引擎基础异常。"""

    pass


class ConfigError(ChatEngineError):
    """配置错误（API Key 缺失等）。"""

    pass


class LLMCallError(ChatEngineError):
    """LLM 调用失败（网络、超时等）。"""

    pass


# ============================================================
# ChatEngine
# ============================================================


class ChatEngine:
    """对话引擎 — 封装 LLM 调用的全部逻辑。

    职责：
    - 管理与 LLM 的连接（ChatOpenAI）
    - 维护当前会话的消息历史
    - 提供流式和非流式两种对话模式
    - 统计 Token 用量

    不负责：
    - 消息持久化（由 SessionManager 负责）
    - 用户输入/输出渲染（由 TUI 层负责）

    Attributes:
        _config: ConfigManager 实例（读取 API 配置）
        _state: 应用全局状态字典
        _llm: ChatOpenAI 实例（懒初始化，切换模型时重建）
        _history: 当前对话的消息列表（含系统消息）
        _system_prompt: 当前系统提示词文本
        _total_prompt_tokens: 累计 prompt token 消耗
        _total_completion_tokens: 累计 completion token 消耗
        _current_model: 当前使用的模型名称
    """

    def __init__(self, config: Any, state: Optional[Dict[str, Any]] = None) -> None:
        """初始化对话引擎。

        Args:
            config: ConfigManager 实例（提供 API Key / Base URL / 模型配置）
            state: 应用全局状态字典（可选，用于与 TUI 层共享状态）
        """
        self._config = config
        self._state = state or {}

        # LLM 实例（懒初始化）
        self._llm: Optional[ChatOpenAI] = None

        # 消息历史：LangChain BaseMessage 列表
        self._history: List[BaseMessage] = []
        self._system_prompt: Optional[str] = None

        # Token 累计统计
        self._total_prompt_tokens: int = 0
        self._total_completion_tokens: int = 0

        # 上一轮 Token 统计（用于展示"本轮消耗"）
        self._last_prompt_tokens: int = 0
        self._last_completion_tokens: int = 0

        # 当前模型
        self._current_model: str = config.model_name

    # ============================================================
    # LLM 实例管理
    # ============================================================

    def _create_llm(self, model_name: Optional[str] = None) -> ChatOpenAI:
        """创建 ChatOpenAI 实例。

        每次调用都会新建实例，确保配置变更（如模型切换）即时生效。
        ChatOpenAI 的内置 max_retries 和 timeout 自动处理重试与超时。

        Args:
            model_name: 模型名称，默认使用 self._current_model

        Returns:
            配置好的 ChatOpenAI 实例

        Raises:
            ConfigError: API Key 未配置
        """
        model = model_name or self._current_model

        if not self._config.api_key:
            raise ConfigError(
                "API Key 未配置。请编辑 .env 文件，设置 API_KEY=你的密钥"
            )

        return ChatOpenAI(
            base_url=self._config.api_base_url,
            api_key=self._config.api_key,
            model=model,
            streaming=self._config.llm_streaming,
            timeout=self._config.llm_timeout,
            max_retries=self._config.llm_max_retries,
        )

    def _get_llm(self) -> ChatOpenAI:
        """获取当前 LLM 实例（懒初始化 + 自动验证配置）。

        Returns:
            ChatOpenAI 实例

        Raises:
            ConfigError: API Key 未配置
        """
        if self._llm is None:
            self._llm = self._create_llm()
        return self._llm

    # ============================================================
    # 系统提示词管理
    # ============================================================

    @property
    def system_prompt(self) -> Optional[str]:
        """当前系统提示词文本。"""
        return self._system_prompt

    def set_system_prompt(self, system_prompt: str) -> None:
        """设置系统提示词（预设角色）。

        设置后会自动替换消息历史中的旧系统消息。
        如果之前已设置系统提示词，新提示词会覆盖旧的。

        Args:
            system_prompt: 系统提示词文本（如 "你是一个翻译助手..."）
        """
        self._system_prompt = system_prompt
        self._rebuild_system_message()

    def clear_system_prompt(self) -> None:
        """清除系统提示词。

        清空后对话将不再包含系统级角色设定。
        """
        self._system_prompt = None
        self._history = [m for m in self._history if not isinstance(m, SystemMessage)]

    def _rebuild_system_message(self) -> None:
        """在消息历史中重建系统消息。

        策略：
        - 移除所有已有的 SystemMessage
        - 如果当前设定了 system_prompt，将其插入到消息列表最前面
        """
        # 移除旧系统消息
        self._history = [m for m in self._history if not isinstance(m, SystemMessage)]
        # 如有，插入新系统消息到列表头部
        if self._system_prompt:
            self._history.insert(0, SystemMessage(content=self._system_prompt))

    # ============================================================
    # 消息历史管理
    # ============================================================

    @property
    def history(self) -> List[BaseMessage]:
        """当前对话历史（不含系统消息）。

        用于外部查看对话内容，返回 LangChain BaseMessage 列表。
        """
        return [m for m in self._history if not isinstance(m, SystemMessage)]

    @property
    def full_history(self) -> List[BaseMessage]:
        """完整消息历史（含系统消息）。

        Returns:
            LangChain BaseMessage 列表的浅拷贝
        """
        return list(self._history)

    @property
    def message_count(self) -> int:
        """当前会话的消息数量（不含系统消息）。"""
        return len(self.history)

    @property
    def has_history(self) -> bool:
        """是否有对话历史。"""
        return len(self.history) > 0

    def load_history(self, messages: List[Dict[str, Any]]) -> None:
        """从数据库加载历史消息到引擎。

        用于恢复一个已有的会话。加载前会清空当前历史。
        加载后如果之前设置了系统提示词，会自动插入到最前面。

        Args:
            messages: 数据库中的消息记录列表。
                      每条记录至少包含 role（"human"/"ai"/"system"）和 content。
        """
        self._history.clear()

        # 先添加系统提示词
        if self._system_prompt:
            self._history.append(SystemMessage(content=self._system_prompt))

        # 按列表顺序添加历史消息（数据库已按时间排序）
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "human":
                self._history.append(HumanMessage(content=content))
            elif role == "ai":
                self._history.append(AIMessage(content=content))
            elif role == "system":
                # 数据库中的 system 消息：仅在没有显式设置 system_prompt 时才添加
                if not self._system_prompt:
                    self._history.append(SystemMessage(content=content))

    def clear_history(self) -> None:
        """清空对话历史（保留系统提示词）。

        清空操作同时重置 Token 统计，等同于开始一个新对话。
        系统提示词会被保留（如果已设置）。
        """
        # 保存系统消息
        system_msg = None
        if self._history and isinstance(self._history[0], SystemMessage):
            system_msg = self._history[0]

        self._history.clear()

        # 恢复系统消息
        if system_msg:
            self._history.append(system_msg)

        # 重置 Token 统计
        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0
        self._last_prompt_tokens = 0
        self._last_completion_tokens = 0

    # ============================================================
    # 模型切换
    # ============================================================

    def switch_model(self, model_name: str) -> None:
        """运行时切换到不同的模型。

        注意：
        - 切换不会清空对话历史，新模型继承完整上下文
        - 如果新模型与旧模型 token 计数方式不同，
          累计统计会跨模型混合（由上层决定是否需要重置）

        Args:
            model_name: 目标模型名称（如 "gpt-4o"、"deepseek-chat"）
        """
        self._current_model = model_name
        self._llm = None  # 使缓存的 LLM 实例失效，下次调用时懒重建

    @property
    def current_model(self) -> str:
        """当前使用的模型名称。"""
        return self._current_model

    # ============================================================
    # Token 统计
    # ============================================================

    @property
    def total_prompt_tokens(self) -> int:
        """累计 prompt token 消耗。"""
        return self._total_prompt_tokens

    @property
    def total_completion_tokens(self) -> int:
        """累计 completion token 消耗。"""
        return self._total_completion_tokens

    @property
    def total_tokens(self) -> int:
        """累计总 token 消耗（prompt + completion）。"""
        return self._total_prompt_tokens + self._total_completion_tokens

    @property
    def last_prompt_tokens(self) -> int:
        """上一轮对话的 prompt token 消耗。"""
        return self._last_prompt_tokens

    @property
    def last_completion_tokens(self) -> int:
        """上一轮对话的 completion token 消耗。"""
        return self._last_completion_tokens

    @property
    def last_tokens(self) -> int:
        """上一轮对话的总 token 消耗。"""
        return self._last_prompt_tokens + self._last_completion_tokens

    def _update_token_stats(self, response_metadata: Dict[str, Any]) -> None:
        """从 LLM 响应的 metadata 中提取 Token 用量并更新统计。

        OpenAI 兼容 API 的标准响应格式中，token 信息位于
        response_metadata["token_usage"] 中，包含：
        - prompt_tokens
        - completion_tokens
        - total_tokens

        如果上游 API 不返回 token 信息（如部分本地模型），
        则所有统计值保持为 0。

        Args:
            response_metadata: AIMessage.response_metadata 字典
        """
        usage = response_metadata.get("token_usage", {})
        if not usage:
            return

        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        self._last_prompt_tokens = prompt_tokens
        self._last_completion_tokens = completion_tokens
        self._total_prompt_tokens += prompt_tokens
        self._total_completion_tokens += completion_tokens

    def reset_token_stats(self) -> None:
        """重置 Token 统计（不清理消息历史）。

        用于需要重新开始统计的场景（如加载历史会话后）。
        """
        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0
        self._last_prompt_tokens = 0
        self._last_completion_tokens = 0

    # ============================================================
    # 对话接口 — 非流式
    # ============================================================

    async def chat(self, user_input: str) -> Dict[str, Any]:
        """发送消息并获取完整 AI 回复（非流式，等待完整结果）。

        适用场景：
        - 不需要实时展示输出时（如脚本调用、测试）
        - 需要一次性获取完整回复文本

        Args:
            user_input: 用户输入的文本

        Returns:
            {
                "content": str,             # AI 回复的完整文本
                "prompt_tokens": int,       # 本轮 prompt token 消耗
                "completion_tokens": int,   # 本轮 completion token 消耗
                "total_tokens": int,        # 本轮总 token 消耗
                "model": str,               # 使用的模型名称
            }

        Raises:
            ConfigError: API Key 未配置
            LLMCallError: LLM API 调用失败（网络错误、超时等，已自动重试后仍失败）
        """
        if not self._config.api_key:
            raise ConfigError(
                "API Key 未配置。请编辑 .env 文件，设置 API_KEY=你的密钥"
            )

        llm = self._get_llm()

        # 添加用户消息到历史
        self._history.append(HumanMessage(content=user_input))

        try:
            response: AIMessage = await llm.ainvoke(self._history)
        except Exception as e:
            # 调用失败：回滚刚才添加的用户消息，保持历史干净
            self._history.pop()
            raise LLMCallError(
                f"LLM API 调用失败（模型: {self._current_model}）: {e}"
            ) from e

        # 将 AI 回复添加到历史
        self._history.append(response)

        # 提取 Token 统计
        self._update_token_stats(response.response_metadata)

        return {
            "content": response.content,
            "prompt_tokens": self._last_prompt_tokens,
            "completion_tokens": self._last_completion_tokens,
            "total_tokens": self.last_tokens,
            "model": self._current_model,
        }

    # ============================================================
    # 对话接口 — 流式
    # ============================================================

    async def chat_stream(self, user_input: str) -> AsyncIterator[Dict[str, Any]]:
        """发送消息并逐 token 流式返回（异步生成器）。

        每产生一个新的 token chunk 就 yield 一次，TUI 层可逐字渲染。
        流式传输结束时 yield 最后一个包含完整统计信息的 chunk。

        适用场景：
        - TUI 实时打字机效果
        - 用户需要即时看到输出

        Yields 的消息格式：
            # 中间 chunk（可能有多个）
            {
                "content": str,         # 增量文本（1 个或多个 token）
                "done": False,          # 是否已完成
                "prompt_tokens": 0,     # 中间 chunk 不包含统计
                "completion_tokens": 0,
                "total_tokens": 0,
                "model": str,           # 使用的模型名称
            }

            # 最终 chunk（仅一个）
            {
                "content": "",          # 最终 chunk 无内容
                "done": True,           # 标记流结束
                "prompt_tokens": int,   # 本轮 prompt token 消耗
                "completion_tokens": int,
                "total_tokens": int,
                "model": str,
            }

        Raises:
            ConfigError: API Key 未配置
            LLMCallError: LLM 流式调用失败

        Example:
            >>> async for chunk in engine.chat_stream("你好"):
            ...     if chunk["done"]:
            ...         print(f"\\n[Tokens: {chunk['total_tokens']}]")
            ...     else:
            ...         print(chunk["content"], end="", flush=True)
        """
        if not self._config.api_key:
            raise ConfigError(
                "API Key 未配置。请编辑 .env 文件，设置 API_KEY=你的密钥"
            )

        llm = self._get_llm()

        # 添加用户消息到历史
        self._history.append(HumanMessage(content=user_input))

        full_content = ""
        final_chunk = None
        stream_error = None

        try:
            async for chunk in llm.astream(self._history):
                # chunk 是 AIMessageChunk
                delta = chunk.content if hasattr(chunk, "content") else ""
                if isinstance(delta, str) and delta:
                    full_content += delta
                final_chunk = chunk

                yield {
                    "content": delta if isinstance(delta, str) else "",
                    "done": False,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "model": self._current_model,
                }
        except Exception as e:
            # 保存错误，但需要先清理状态
            stream_error = e
        finally:
            if stream_error is None:
                # 成功：将完整 AI 回复添加到历史
                ai_message = AIMessage(content=full_content)
                # 尝试从最后一个 chunk 获取 response_metadata
                if final_chunk and hasattr(final_chunk, "response_metadata"):
                    ai_message.response_metadata = final_chunk.response_metadata
                self._history.append(ai_message)

                # 提取 Token 统计
                if final_chunk and hasattr(final_chunk, "response_metadata"):
                    self._update_token_stats(final_chunk.response_metadata)

        # 如果出错，在清理后抛出
        if stream_error is not None:
            self._history.pop()  # 回滚用户消息
            raise LLMCallError(
                f"LLM 流式调用失败（模型: {self._current_model}）: {stream_error}"
            ) from stream_error

        # 最终 chunk：Token 统计
        yield {
            "content": "",
            "done": True,
            "prompt_tokens": self._last_prompt_tokens,
            "completion_tokens": self._last_completion_tokens,
            "total_tokens": self.last_tokens,
            "model": self._current_model,
        }

    # ============================================================
    # 状态查询
    # ============================================================

    def get_stats(self) -> Dict[str, Any]:
        """获取引擎的当前运行统计。

        Returns:
            包含模型、消息数、Token 消耗等信息的字典
        """
        return {
            "model": self._current_model,
            "message_count": self.message_count,
            "has_system_prompt": self._system_prompt is not None,
            "system_prompt_preview": (
                self._system_prompt[:60] + "..."
                if self._system_prompt and len(self._system_prompt) > 60
                else self._system_prompt
            ),
            "total_prompt_tokens": self._total_prompt_tokens,
            "total_completion_tokens": self._total_completion_tokens,
            "total_tokens": self.total_tokens,
            "last_prompt_tokens": self._last_prompt_tokens,
            "last_completion_tokens": self._last_completion_tokens,
            "last_tokens": self.last_tokens,
        }

    def get_config_summary(self) -> Dict[str, Any]:
        """获取当前 LLM 配置摘要（脱敏）。

        Returns:
            包含 API 端点、模型、超时等配置的字典（不含 API Key）
        """
        return {
            "api_base_url": self._config.api_base_url,
            "model": self._current_model,
            "timeout": self._config.llm_timeout,
            "max_retries": self._config.llm_max_retries,
            "streaming": self._config.llm_streaming,
            "has_api_key": bool(self._config.api_key),
        }

    # ============================================================
    # 生命周期
    # ============================================================

    def reset(self) -> None:
        """完全重置引擎状态。

        清空：
        - 消息历史（含系统提示词）
        - Token 统计
        - LLM 实例（下次使用时重建）
        """
        self._history.clear()
        self._system_prompt = None
        self._llm = None
        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0
        self._last_prompt_tokens = 0
        self._last_completion_tokens = 0
