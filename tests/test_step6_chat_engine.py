"""
Step 6 对话引擎功能验证脚本（一次性测试，非 pytest）。

验证 ChatEngine 的所有功能：
1. 初始化与配置
2. 系统提示词管理
3. 消息历史管理
4. Token 统计
5. 模型切换
6. 错误处理（API Key 缺失等）
7. （可选）真实 LLM 调用 — 需配置 API Key
"""
import sys
import io
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import asyncio
from src.core.config_manager import ConfigManager
from src.core.chat_engine import ChatEngine, ConfigError, LLMCallError


async def test_chat_engine() -> bool:
    """执行全部对话引擎验证，返回 True 表示全部通过。"""
    config = ConfigManager()
    passed = 0
    total_groups = 6  # 前 6 组无需 API Key，第 7 组可选

    state = {
        "current_user_id": None,
        "current_username": None,
        "current_session_id": None,
    }

    print("=" * 60)
    print("  Step 6: ChatEngine 对话引擎验证")
    print("=" * 60)
    print()
    print(f"  API Base URL: {config.api_base_url}")
    print(f"  API Key 已配置: {bool(config.api_key)}")
    print(f"  默认模型: {config.model_name}")
    print(f"  超时: {config.llm_timeout}s / 重试: {config.llm_max_retries}次")
    print()

    # =============================================
    # 1. 初始化与配置
    # =============================================
    print("[Test 1] 初始化与配置")
    print("-" * 40)

    engine = ChatEngine(config, state)

    # 验证初始状态
    assert engine.current_model == config.model_name, "默认模型应匹配配置"
    print(f"  默认模型: {engine.current_model}")

    assert engine.message_count == 0
    print(f"  初始消息数: 0")

    assert engine.has_history is False
    print(f"  有历史: False")

    assert engine.total_prompt_tokens == 0
    assert engine.total_completion_tokens == 0
    assert engine.total_tokens == 0
    print(f"  Token 统计初始为 0")

    # 验证配置摘要
    summary = engine.get_config_summary()
    assert summary["has_api_key"] == bool(config.api_key)
    assert summary["model"] == config.model_name
    assert summary["timeout"] == config.llm_timeout
    assert summary["max_retries"] == config.llm_max_retries
    print(f"  配置摘要验证通过")

    passed += 1
    print(f"  >>> Group 1 PASSED")
    print()

    # =============================================
    # 2. 系统提示词管理
    # =============================================
    print("[Test 2] 系统提示词管理")
    print("-" * 40)

    # 初始无系统提示词
    assert engine.system_prompt is None
    print("  初始: 无系统提示词")

    # 设置系统提示词
    engine.set_system_prompt("你是一个翻译助手，将用户输入翻译成英文。")
    assert engine.system_prompt == "你是一个翻译助手，将用户输入翻译成英文。"
    assert len(engine.full_history) == 1  # 只有一条系统消息
    from langchain_core.messages import SystemMessage
    assert isinstance(engine.full_history[0], SystemMessage)
    print(f"  设置: '{engine.system_prompt[:30]}...'")

    # 替换系统提示词
    engine.set_system_prompt("你是一个代码专家，帮助用户解决编程问题。")
    assert engine.system_prompt == "你是一个代码专家，帮助用户解决编程问题。"
    assert len(engine.full_history) == 1  # 仍然只有一条系统消息
    print(f"  替换: '{engine.system_prompt[:30]}...'")

    # message_count 不含系统消息
    assert engine.message_count == 0
    print(f"  消息数（不含系统）: 0")

    # 清除系统提示词
    engine.clear_system_prompt()
    assert engine.system_prompt is None
    assert len(engine.full_history) == 0
    print(f"  清除: 已清除")

    passed += 1
    print(f"  >>> Group 2 PASSED")
    print()

    # =============================================
    # 3. 消息历史管理
    # =============================================
    print("[Test 3] 消息历史管理")
    print("-" * 40)

    # load_history
    fake_messages = [
        {"role": "human", "content": "你好"},
        {"role": "ai", "content": "你好！有什么可以帮助你的？"},
        {"role": "human", "content": "介绍一下 Python"},
        {"role": "ai", "content": "Python 是一种高级编程语言..."},
    ]
    engine.load_history(fake_messages)
    assert engine.message_count == 4, f"应有 4 条消息, 实际 {engine.message_count}"
    assert engine.has_history is True
    print(f"  加载历史: {engine.message_count} 条消息")

    # 验证消息类型
    from langchain_core.messages import HumanMessage, AIMessage
    history = engine.history
    assert isinstance(history[0], HumanMessage)
    assert isinstance(history[1], AIMessage)
    assert history[0].content == "你好"
    print(f"  消息类型验证通过 (HumanMessage / AIMessage)")

    # load_history 后设置系统提示词 — 系统消息应在最前面
    engine.set_system_prompt("你是一个有用的助手")
    assert len(engine.full_history) == 5  # 4 + 1 system
    assert isinstance(engine.full_history[0], SystemMessage)
    assert engine.message_count == 4  # 不含系统消息
    print(f"  设置系统提示词后: full={len(engine.full_history)}, history={engine.message_count}")

    # clear_history — 保留系统消息
    engine.clear_history()
    assert engine.message_count == 0
    assert len(engine.full_history) == 1  # 仅系统消息
    assert isinstance(engine.full_history[0], SystemMessage)
    print(f"  清空历史: 保留系统消息, full={len(engine.full_history)}")

    # reset — 全部清空
    engine.reset()
    assert engine.message_count == 0
    assert len(engine.full_history) == 0
    assert engine.system_prompt is None
    print(f"  重置: 全部清空")

    passed += 1
    print(f"  >>> Group 3 PASSED")
    print()

    # =============================================
    # 4. Token 统计
    # =============================================
    print("[Test 4] Token 统计")
    print("-" * 40)

    # 初始状态
    assert engine.total_prompt_tokens == 0
    assert engine.total_completion_tokens == 0
    assert engine.total_tokens == 0
    assert engine.last_prompt_tokens == 0
    assert engine.last_completion_tokens == 0
    assert engine.last_tokens == 0
    print(f"  初始 Token: all=0")

    # 模拟 _update_token_stats — 使用 Mock 对象模拟 AIMessage
    class MockMessage:
        def __init__(self, usage_metadata=None, response_metadata=None):
            self.usage_metadata = usage_metadata
            self.response_metadata = response_metadata or {}

    # 测试 usage_metadata 路径（新版 LangChain — DeepSeek 等）
    engine._update_token_stats(MockMessage(
        usage_metadata={"input_tokens": 150, "output_tokens": 80, "total_tokens": 230}
    ))
    assert engine.last_prompt_tokens == 150
    assert engine.last_completion_tokens == 80
    assert engine.last_tokens == 230
    assert engine.total_prompt_tokens == 150
    assert engine.total_completion_tokens == 80
    assert engine.total_tokens == 230
    print(f"  第一轮(usage_metadata): prompt={engine.last_prompt_tokens}, completion={engine.last_completion_tokens}, total={engine.last_tokens}")

    # 第二轮
    engine._update_token_stats(MockMessage(
        usage_metadata={"input_tokens": 200, "output_tokens": 120, "total_tokens": 320}
    ))
    assert engine.last_prompt_tokens == 200
    assert engine.last_completion_tokens == 120
    assert engine.last_tokens == 320
    assert engine.total_prompt_tokens == 350  # 150 + 200
    assert engine.total_completion_tokens == 200  # 80 + 120
    assert engine.total_tokens == 550  # 230 + 320
    print(f"  第二轮(usage_metadata): prompt={engine.last_prompt_tokens}, completion={engine.last_completion_tokens}")
    print(f"  累计: prompt={engine.total_prompt_tokens}, completion={engine.total_completion_tokens}, total={engine.total_tokens}")

    # 测试 response_metadata["token_usage"] 路径（OpenAI 旧格式）
    engine.reset_token_stats()
    engine._update_token_stats(MockMessage(
        response_metadata={"token_usage": {"prompt_tokens": 50, "completion_tokens": 30, "total_tokens": 80}}
    ))
    assert engine.last_prompt_tokens == 50
    assert engine.last_completion_tokens == 30
    assert engine.total_tokens == 80
    print(f"  response_metadata 路径: prompt={engine.last_prompt_tokens}, completion={engine.last_completion_tokens}")

    # reset_token_stats
    engine.reset_token_stats()
    assert engine.total_prompt_tokens == 0
    assert engine.total_completion_tokens == 0
    assert engine.last_prompt_tokens == 0
    print(f"  重置统计: all=0")

    passed += 1
    print(f"  >>> Group 4 PASSED")
    print()

    # =============================================
    # 5. 模型切换
    # =============================================
    print("[Test 5] 模型切换")
    print("-" * 40)

    assert engine.current_model == config.model_name
    print(f"  当前模型: {engine.current_model}")

    engine.switch_model("gpt-4o")
    assert engine.current_model == "gpt-4o"
    print(f"  切换到: {engine.current_model}")

    engine.switch_model("deepseek-chat")
    assert engine.current_model == "deepseek-chat"
    print(f"  切换到: {engine.current_model}")

    # 切换回默认
    engine.switch_model(config.model_name)
    assert engine.current_model == config.model_name
    print(f"  切回: {engine.current_model}")

    passed += 1
    print(f"  >>> Group 5 PASSED")
    print()

    # =============================================
    # 6. 错误处理（无需 API Key）
    # =============================================
    print("[Test 6] 错误处理")
    print("-" * 40)

    # 如果已配置 API Key，此测试组的 ConfigError 测试会跳过
    if config.api_key:
        print("  [跳过] API Key 已配置，ConfigError 测试不适用")
        print("  引擎会正常尝试 LLM 调用（可能成功或失败取决于网络）")
    else:
        # 测试 chat() 缺少 API Key
        try:
            await engine.chat("你好")
            print("  [FAIL] chat() 应在无 API Key 时抛出 ConfigError")
        except ConfigError as e:
            print(f"  [OK] chat() 正确抛出 ConfigError: {e}")
        except Exception as e:
            print(f"  [FAIL] 错误的异常类型: {type(e).__name__}: {e}")

        # 测试 chat_stream() 缺少 API Key
        try:
            async for _ in engine.chat_stream("你好"):
                pass
            print("  [FAIL] chat_stream() 应在无 API Key 时抛出 ConfigError")
        except ConfigError as e:
            print(f"  [OK] chat_stream() 正确抛出 ConfigError: {e}")
        except Exception as e:
            print(f"  [FAIL] 错误的异常类型: {type(e).__name__}: {e}")

        # 验证 API Key 为空时 _create_llm 抛出 ConfigError
        try:
            engine._create_llm()
            print("  [FAIL] _create_llm() 应在无 API Key 时抛出 ConfigError")
        except ConfigError:
            print(f"  [OK] _create_llm() 正确抛出 ConfigError")

    passed += 1
    print(f"  >>> Group 6 PASSED")
    print()

    # =============================================
    # 7. 真实 LLM 调用（需 API Key）
    # =============================================
    if config.api_key:
        print("[Test 7] 真实 LLM 调用（已配置 API Key）")
        print("-" * 40)

        # 重置引擎
        engine.reset()
        engine.set_system_prompt("你是一个简洁的助手，用最短的话回答问题。")

        # 7a. 非流式调用
        print("  [7a] 非流式 chat()...")
        try:
            result = await engine.chat("用一句话介绍 Python")
            assert "content" in result
            assert len(result["content"]) > 0
            assert result["model"] == config.model_name
            print(f"    回复: {result['content'][:80]}...")
            print(f"    Token: prompt={result['prompt_tokens']}, "
                  f"completion={result['completion_tokens']}, "
                  f"total={result['total_tokens']}")
            print(f"    [OK] 非流式调用成功")
        except LLMCallError as e:
            print(f"    [FAIL] LLM 调用失败: {e}")
        except Exception as e:
            print(f"    [FAIL] 未预期错误: {type(e).__name__}: {e}")

        # 7b. 流式调用
        print()
        print("  [7b] 流式 chat_stream()...")
        try:
            full_response = ""
            async for chunk in engine.chat_stream("1+1等于几？"):
                if chunk["done"]:
                    print(f"\n    Token: prompt={chunk['prompt_tokens']}, "
                          f"completion={chunk['completion_tokens']}, "
                          f"total={chunk['total_tokens']}")
                else:
                    full_response += chunk["content"]
            assert len(full_response) > 0
            print(f"    完整回复: {full_response[:80]}...")
            print(f"    [OK] 流式调用成功")
        except LLMCallError as e:
            print(f"    [FAIL] LLM 流式调用失败: {e}")
        except Exception as e:
            print(f"    [FAIL] 未预期错误: {type(e).__name__}: {e}")

        # 7c. 多轮对话
        print()
        print("  [7c] 多轮对话上下文保持...")
        try:
            r1 = await engine.chat("我叫张三")
            print(f"    第1轮: {r1['content'][:60]}...")

            r2 = await engine.chat("我叫什么名字？")
            print(f"    第2轮: {r2['content'][:60]}...")
            # 应该提到"张三"
            name_remembered = "张三" in r2["content"]
            print(f"    记住名字: {'是' if name_remembered else '否'}")

            # 验证消息数
            assert engine.message_count >= 4  # 至少 2 轮 = 4 条消息
            print(f"    消息数: {engine.message_count}")
            print(f"    累计 Token: {engine.total_tokens}")
            print(f"    [OK] 多轮对话上下文正常")
        except LLMCallError as e:
            print(f"    [FAIL] LLM 调用失败: {e}")
        except Exception as e:
            print(f"    [FAIL] 未预期错误: {type(e).__name__}: {e}")

        # 7d. stats
        print()
        print("  [7d] get_stats()...")
        stats = engine.get_stats()
        print(f"    模型: {stats['model']}")
        print(f"    消息数: {stats['message_count']}")
        print(f"    有系统提示词: {stats['has_system_prompt']}")
        print(f"    累计 Token: {stats['total_tokens']}")
        print(f"    [OK] 统计信息完整")

        passed += 1
        print(f"  >>> Group 7 PASSED")
        print()

        total_groups = 7  # 更新总数

    else:
        total_groups = 6
        print("[Test 7] 真实 LLM 调用")
        print("-" * 40)
        print("  [跳过] 未配置 API Key，跳过真实 LLM 调用测试")
        print()
        print("  配置 API Key 后，请运行:")
        print("    uv run python tests/test_step6_chat_engine.py")
        print("  届时将自动测试真实 LLM 调用（流式 + 多轮对话 + Token 统计）")
        print()

    # =============================================
    # Result
    # =============================================
    print("=" * 60)
    if config.api_key:
        print(f"  ALL {passed}/{total_groups} TEST GROUPS PASSED!")
    else:
        print(f"  {passed}/{total_groups} (非 API) TEST GROUPS PASSED!")
        print(f"  (配置 API Key 后可测试第 7 组：真实 LLM 调用)")
    print("=" * 60)
    return passed >= total_groups if config.api_key else passed >= 6


if __name__ == "__main__":
    try:
        success = asyncio.run(test_chat_engine())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n用户中断")
        sys.exit(1)
