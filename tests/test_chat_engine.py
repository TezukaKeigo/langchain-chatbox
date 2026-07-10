"""
对话引擎单元测试 — 覆盖 ChatEngine 全部功能（无需真实 API Key）。

测试策略：
- 所有测试不依赖真实 LLM API（仅测试引擎内部逻辑）
- 使用 ConfigManager 的真实配置（API Key 可能为空）
- 覆盖：初始化 / 系统提示词 / 消息历史 / Token 统计 / 模型切换 / 错误处理
"""

import pytest
from src.core.chat_engine import ChatEngine, ConfigError, LLMCallError


class TestChatEngineInit:
    """引擎初始化"""

    def test_init_with_config(self, config_manager, state):
        engine = ChatEngine(config_manager, state)
        assert engine.current_model == config_manager.model_name
        assert engine.message_count == 0
        assert engine.has_history is False
        assert engine.system_prompt is None
        assert engine.total_prompt_tokens == 0
        assert engine.total_completion_tokens == 0
        assert engine.total_tokens == 0

    def test_init_without_state(self, config_manager):
        engine = ChatEngine(config_manager)
        assert engine.current_model == config_manager.model_name
        assert engine.message_count == 0

    def test_init_uses_state_model(self, config_manager, state):
        state["current_model"] = "gpt-4o"
        engine = ChatEngine(config_manager, state)
        assert engine.current_model == "gpt-4o"

    def test_init_falls_back_to_config_model(self, config_manager, state):
        state["current_model"] = None
        engine = ChatEngine(config_manager, state)
        assert engine.current_model == config_manager.model_name

    def test_get_config_summary(self, config_manager, state):
        engine = ChatEngine(config_manager, state)
        summary = engine.get_config_summary()
        assert summary["model"] == config_manager.model_name
        assert summary["timeout"] == config_manager.llm_timeout
        assert summary["max_retries"] == config_manager.llm_max_retries
        assert summary["streaming"] == config_manager.llm_streaming
        assert "has_api_key" in summary
        assert "api_base_url" in summary

    def test_get_stats_initial(self, config_manager, state):
        engine = ChatEngine(config_manager, state)
        stats = engine.get_stats()
        assert stats["model"] == config_manager.model_name
        assert stats["message_count"] == 0
        assert stats["has_system_prompt"] is False
        assert stats["total_tokens"] == 0


class TestSystemPrompt:
    """系统提示词管理"""

    def test_set_system_prompt(self, config_manager, state):
        engine = ChatEngine(config_manager, state)
        engine.set_system_prompt("你是一个翻译助手")
        assert engine.system_prompt == "你是一个翻译助手"
        assert len(engine.full_history) == 1  # 一条系统消息
        from langchain_core.messages import SystemMessage
        assert isinstance(engine.full_history[0], SystemMessage)

    def test_replace_system_prompt(self, config_manager, state):
        engine = ChatEngine(config_manager, state)
        engine.set_system_prompt("第一个提示词")
        engine.set_system_prompt("第二个提示词")
        assert engine.system_prompt == "第二个提示词"
        # 仍然只有一条系统消息
        assert len(engine.full_history) == 1

    def test_clear_system_prompt(self, config_manager, state):
        engine = ChatEngine(config_manager, state)
        engine.set_system_prompt("提示词")
        engine.clear_system_prompt()
        assert engine.system_prompt is None
        assert len(engine.full_history) == 0

    def test_system_prompt_does_not_count_as_message(self, config_manager, state):
        engine = ChatEngine(config_manager, state)
        engine.set_system_prompt("你是一个助手")
        assert engine.message_count == 0  # 系统消息不计入
        assert engine.has_history is False

    def test_set_system_prompt_after_load_history(self, config_manager, state):
        """设置系统提示词后，它应在历史消息最前面"""
        engine = ChatEngine(config_manager, state)
        engine.load_history([
            {"role": "human", "content": "你好"},
            {"role": "ai", "content": "你好！"},
        ])
        assert engine.message_count == 2

        engine.set_system_prompt("你是一个助手")
        # 系统消息应在最前面
        from langchain_core.messages import SystemMessage
        assert isinstance(engine.full_history[0], SystemMessage)
        assert engine.message_count == 2  # 仍然不含系统消息
        assert len(engine.full_history) == 3  # 含系统消息

    def test_get_stats_shows_system_prompt(self, config_manager, state):
        engine = ChatEngine(config_manager, state)
        engine.set_system_prompt("你是一个代码专家，帮助用户解决编程问题。")
        stats = engine.get_stats()
        assert stats["has_system_prompt"] is True

    def test_get_stats_long_system_prompt_preview(self, config_manager, state):
        engine = ChatEngine(config_manager, state)
        long_prompt = "你是一个专业的Python开发者，精通Django、Flask等框架，" * 5
        engine.set_system_prompt(long_prompt)
        stats = engine.get_stats()
        preview = stats["system_prompt_preview"]
        assert len(preview) <= 63  # 60 + "..."

    def test_reset_clears_system_prompt(self, config_manager, state):
        engine = ChatEngine(config_manager, state)
        engine.set_system_prompt("提示词")
        engine.reset()
        assert engine.system_prompt is None
        assert len(engine.full_history) == 0


class TestMessageHistory:
    """消息历史管理"""

    def test_load_history(self, config_manager, state):
        engine = ChatEngine(config_manager, state)
        messages = [
            {"role": "human", "content": "你好"},
            {"role": "ai", "content": "你好！有什么可以帮助你的？"},
            {"role": "human", "content": "介绍一下 Python"},
            {"role": "ai", "content": "Python 是一种高级编程语言..."},
        ]
        engine.load_history(messages)
        assert engine.message_count == 4
        assert engine.has_history is True

        from langchain_core.messages import HumanMessage, AIMessage
        history = engine.history
        assert isinstance(history[0], HumanMessage)
        assert isinstance(history[1], AIMessage)
        assert history[0].content == "你好"

    def test_load_history_replaces_existing(self, config_manager, state):
        engine = ChatEngine(config_manager, state)
        engine.load_history([{"role": "human", "content": "旧消息"}])
        assert engine.message_count == 1

        engine.load_history([{"role": "human", "content": "新消息"}])
        assert engine.message_count == 1
        assert engine.history[0].content == "新消息"

    def test_load_history_preserves_system_prompt(self, config_manager, state):
        engine = ChatEngine(config_manager, state)
        engine.set_system_prompt("你是一个助手")
        engine.load_history([
            {"role": "human", "content": "你好"},
        ])
        assert len(engine.full_history) == 2  # system + human
        from langchain_core.messages import SystemMessage
        assert isinstance(engine.full_history[0], SystemMessage)

    def test_load_history_with_system_messages(self, config_manager, state):
        """数据库中的 system 消息：无显式 system_prompt 时添加"""
        engine = ChatEngine(config_manager, state)
        engine.load_history([
            {"role": "system", "content": "DB中的系统消息"},
            {"role": "human", "content": "你好"},
        ])
        assert len(engine.full_history) == 2
        from langchain_core.messages import SystemMessage
        assert isinstance(engine.full_history[0], SystemMessage)

    def test_load_history_skips_db_system_if_explicit_set(self, config_manager, state):
        """如果已显式设置 system_prompt，跳过 DB 中的 system 消息"""
        engine = ChatEngine(config_manager, state)
        engine.set_system_prompt("显式设置的系统提示词")
        engine.load_history([
            {"role": "system", "content": "DB中的旧系统消息"},
            {"role": "human", "content": "你好"},
        ])
        # 应该只有一条 system 消息（显式设置的）
        from langchain_core.messages import SystemMessage
        system_msgs = [m for m in engine.full_history if isinstance(m, SystemMessage)]
        assert len(system_msgs) == 1
        assert system_msgs[0].content == "显式设置的系统提示词"

    def test_load_history_empty(self, config_manager, state):
        engine = ChatEngine(config_manager, state)
        engine.load_history([])
        assert engine.message_count == 0

    def test_clear_history(self, config_manager, state):
        engine = ChatEngine(config_manager, state)
        engine.load_history([
            {"role": "human", "content": "你好"},
            {"role": "ai", "content": "你好！"},
        ])
        engine.clear_history()
        assert engine.message_count == 0
        assert engine.has_history is False

    def test_clear_history_preserves_system_prompt(self, config_manager, state):
        engine = ChatEngine(config_manager, state)
        engine.set_system_prompt("保留的提示词")
        engine.load_history([
            {"role": "human", "content": "你好"},
        ])
        engine.clear_history()
        assert engine.message_count == 0
        assert engine.system_prompt == "保留的提示词"
        assert len(engine.full_history) == 1  # 仅系统消息

    def test_clear_history_resets_token_stats(self, config_manager, state):
        engine = ChatEngine(config_manager, state)
        # 模拟有 token 统计
        engine._total_prompt_tokens = 100
        engine._total_completion_tokens = 50
        engine._last_prompt_tokens = 10
        engine._last_completion_tokens = 5

        engine.clear_history()
        assert engine.total_prompt_tokens == 0
        assert engine.total_completion_tokens == 0

    def test_reset_complete(self, config_manager, state):
        engine = ChatEngine(config_manager, state)
        engine.set_system_prompt("提示词")
        engine.load_history([
            {"role": "human", "content": "你好"},
        ])
        engine._total_prompt_tokens = 100

        engine.reset()
        assert engine.message_count == 0
        assert engine.system_prompt is None
        assert engine.total_prompt_tokens == 0
        assert engine.total_completion_tokens == 0
        assert engine._llm is None


class TestTokenStatistics:
    """Token 统计"""

    def test_update_token_stats_usage_metadata(self, config_manager, state):
        """usage_metadata 路径（DeepSeek 新格式）"""
        engine = ChatEngine(config_manager, state)

        class MockMsg:
            usage_metadata = {"input_tokens": 150, "output_tokens": 80, "total_tokens": 230}
            response_metadata = {}

        engine._update_token_stats(MockMsg())
        assert engine.last_prompt_tokens == 150
        assert engine.last_completion_tokens == 80
        assert engine.last_tokens == 230
        assert engine.total_prompt_tokens == 150
        assert engine.total_completion_tokens == 80

    def test_update_token_stats_response_metadata(self, config_manager, state):
        """response_metadata["token_usage"] 路径（OpenAI 旧格式）"""
        engine = ChatEngine(config_manager, state)

        class MockMsg:
            usage_metadata = None
            response_metadata = {
                "token_usage": {"prompt_tokens": 50, "completion_tokens": 30, "total_tokens": 80}
            }

        engine._update_token_stats(MockMsg())
        assert engine.last_prompt_tokens == 50
        assert engine.last_completion_tokens == 30

    def test_update_token_stats_usage_field(self, config_manager, state):
        """response_metadata["usage"] 路径（Kimi/Qwen 格式）"""
        engine = ChatEngine(config_manager, state)

        class MockMsg:
            usage_metadata = None
            response_metadata = {
                "usage": {"prompt_tokens": 60, "completion_tokens": 40}
            }

        engine._update_token_stats(MockMsg())
        assert engine.last_prompt_tokens == 60
        assert engine.last_completion_tokens == 40

    def test_update_token_stats_input_output_keys(self, config_manager, state):
        """usage 字段使用 input_tokens/output_tokens 键名"""
        engine = ChatEngine(config_manager, state)

        class MockMsg:
            usage_metadata = None
            response_metadata = {
                "usage": {"input_tokens": 70, "output_tokens": 45}
            }

        engine._update_token_stats(MockMsg())
        assert engine.last_prompt_tokens == 70
        assert engine.last_completion_tokens == 45

    def test_update_token_stats_accumulates(self, config_manager, state):
        """多次调用累加统计"""
        engine = ChatEngine(config_manager, state)

        class MockMsg1:
            usage_metadata = {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}
            response_metadata = {}

        class MockMsg2:
            usage_metadata = {"input_tokens": 200, "output_tokens": 100, "total_tokens": 300}
            response_metadata = {}

        engine._update_token_stats(MockMsg1())
        engine._update_token_stats(MockMsg2())
        assert engine.total_prompt_tokens == 300
        assert engine.total_completion_tokens == 150
        assert engine.total_tokens == 450

    def test_update_token_stats_empty(self, config_manager, state):
        """无可提取的 token 信息时保持不变"""
        engine = ChatEngine(config_manager, state)

        class MockMsg:
            usage_metadata = None
            response_metadata = {}

        engine._update_token_stats(MockMsg())
        assert engine.total_tokens == 0

    def test_reset_token_stats(self, config_manager, state):
        engine = ChatEngine(config_manager, state)
        engine._total_prompt_tokens = 100
        engine._total_completion_tokens = 50
        engine._last_prompt_tokens = 10
        engine._last_completion_tokens = 5

        engine.reset_token_stats()
        assert engine.total_prompt_tokens == 0
        assert engine.total_completion_tokens == 0
        assert engine.last_prompt_tokens == 0
        assert engine.last_completion_tokens == 0

    def test_usage_metadata_priority(self, config_manager, state):
        """usage_metadata 优先于 response_metadata"""
        engine = ChatEngine(config_manager, state)

        class MockMsg:
            usage_metadata = {"input_tokens": 999, "output_tokens": 888, "total_tokens": 1887}
            response_metadata = {"token_usage": {"prompt_tokens": 1, "completion_tokens": 1}}

        engine._update_token_stats(MockMsg())
        assert engine.last_prompt_tokens == 999  # 使用 usage_metadata
        assert engine.last_completion_tokens == 888


class TestModelSwitch:
    """模型切换"""

    def test_switch_model(self, config_manager, state):
        engine = ChatEngine(config_manager, state)
        old_model = engine.current_model

        engine.switch_model("gpt-4o")
        assert engine.current_model == "gpt-4o"
        assert engine._llm is None  # LLM 实例失效

    def test_switch_model_multiple_times(self, config_manager, state):
        engine = ChatEngine(config_manager, state)
        engine.switch_model("gpt-4o")
        engine.switch_model("qwen-plus")
        engine.switch_model("kimi 2.6")
        assert engine.current_model == "kimi 2.6"

    def test_current_model_property(self, config_manager, state):
        engine = ChatEngine(config_manager, state)
        assert engine.current_model == config_manager.model_name


class TestErrorHandling:
    """错误处理（无需 API Key）"""

    async def test_config_error_no_api_key(self, config_manager):
        """API Key 未配置时，调用应失败"""
        # 如果 API Key 已配置，此测试跳过
        if config_manager.api_key:
            pytest.skip("API Key 已配置，ConfigError 测试不适用")

        engine = ChatEngine(config_manager)

        # chat() 应抛出 ConfigError
        with pytest.raises(ConfigError):
            await engine.chat("你好")

        # chat_stream() 应抛出 ConfigError
        with pytest.raises(ConfigError):
            async for _ in engine.chat_stream("你好"):
                pass

    def test_create_llm_no_api_key(self, config_manager, state):
        """_create_llm 在无 API Key 时抛出 ConfigError"""
        # 这个测试不依赖 state 中的 api_key
        engine = ChatEngine(config_manager, state)
        # 对于当前模型，通过 get_model_config 获取 api_key
        # 如果全局 API_KEY 为空，且模型专属 key 也为空，则抛出 ConfigError
        model_cfg = config_manager.get_model_config(config_manager.model_name)
        if model_cfg["api_key"]:
            pytest.skip("API Key 已配置，ConfigError 测试不适用")
        with pytest.raises(ConfigError):
            engine._create_llm()

    def test_get_llm_lazy_init(self, config_manager, state):
        """_get_llm 懒初始化"""
        engine = ChatEngine(config_manager, state)
        assert engine._llm is None

        model_cfg = config_manager.get_model_config(config_manager.model_name)
        if model_cfg["api_key"]:
            # API Key 已配置，应能正常初始化
            llm = engine._get_llm()
            assert llm is not None
            assert engine._llm is not None
        else:
            with pytest.raises(ConfigError):
                engine._get_llm()


class TestStateIntegration:
    """与 state 字典的集成"""

    def test_state_reflects_engine_model(self, config_manager, state):
        """验证引擎正确读取 state 中的模型"""
        state["current_model"] = "qwen-plus"
        engine = ChatEngine(config_manager, state)
        assert engine.current_model == "qwen-plus"
        # 切换模型后 state 不受影响（由上层负责同步）
        engine.switch_model("deepseek-v4-flash")
        assert state["current_model"] == "qwen-plus"  # 未变
        assert engine.current_model == "deepseek-v4-flash"


class TestEdgeCases:
    """边界情况测试"""

    def test_empty_message_content(self, config_manager, state):
        """加载空内容的消息"""
        engine = ChatEngine(config_manager, state)
        engine.load_history([
            {"role": "human", "content": ""},
            {"role": "ai", "content": ""},
        ])
        assert engine.message_count == 2

    def test_unknown_role_in_load_history(self, config_manager, state):
        """加载未知角色的消息应被忽略"""
        engine = ChatEngine(config_manager, state)
        engine.load_history([
            {"role": "unknown_role", "content": "test"},
            {"role": "human", "content": "real message"},
        ])
        assert engine.message_count == 1

    def test_missing_role_in_load_history(self, config_manager, state):
        """加载缺少 role 字段的消息"""
        engine = ChatEngine(config_manager, state)
        engine.load_history([
            {"content": "no role field"},
            {"role": "human", "content": "real message"},
        ])
        assert engine.message_count == 1

    def test_missing_content_in_load_history(self, config_manager, state):
        """加载缺少 content 字段的消息"""
        engine = ChatEngine(config_manager, state)
        engine.load_history([
            {"role": "human"},
            {"role": "human", "content": "real message"},
        ])
        assert engine.message_count == 2
        assert engine.history[0].content == ""  # 默认空字符串

    def test_chat_engine_error_hierarchy(self):
        """验证异常类继承关系"""
        from src.core.chat_engine import ChatEngineError
        assert issubclass(ConfigError, ChatEngineError)
        assert issubclass(LLMCallError, ChatEngineError)
        assert issubclass(ChatEngineError, Exception)
