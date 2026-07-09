"""
Step 7 会话管理 + TUI 对话对接验证脚本（一次性测试，非 pytest）。

验证内容：
1. SessionManager — 会话 CRUD
2. SessionManager — 消息保存与加载
3. SessionManager — 自动标题生成
4. SessionManager — Token 累计
5. ChatView — 组件初始化
6. 集成：ChatEngine + SessionManager + Storage
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
from src.storage.sqlite_backend import SQLiteBackend
from src.core.session_manager import SessionManager
from src.core.chat_engine import ChatEngine, ConfigError
from src.ui.tui.chat_view import ChatView


async def test_step7() -> bool:
    """执行全部 Step 7 验证，返回 True 表示全部通过。"""
    config = ConfigManager()
    backend = None
    passed = 0
    total_groups = 7

    try:
        # 使用独立测试数据库
        test_db_path = _PROJECT_ROOT / "tests" / "test_step7.db"
        if test_db_path.exists():
            try:
                test_db_path.unlink()
            except PermissionError:
                import time
                test_db_path = _PROJECT_ROOT / "tests" / f"test_step7_{int(time.time())}.db"

        backend = SQLiteBackend(str(test_db_path))
        await backend.initialize()

        state = {
            "current_user_id": None,
            "current_username": None,
            "current_session_id": None,
            "current_session_title": None,
            "current_model": config.model_name,
            "current_preset_id": None,
            "current_preset_name": None,
            "config": config,
        }

        # 创建测试用户
        user = await backend.create_user("_testuser7")
        state["current_user_id"] = user["id"]
        state["current_username"] = user["username"]

        session_mgr = SessionManager(backend, state, config)

        print("=" * 60)
        print("  Step 7: 会话管理 + 对话对接验证")
        print("=" * 60)
        print()

        # =============================================
        # 1. 会话创建
        # =============================================
        print("[Test 1] 会话创建")
        print("-" * 40)

        # 无当前会话时自动创建
        session = await session_mgr.get_or_create_session(
            user_id=user["id"],
            model_name="gpt-4o-mini",
        )
        assert session["title"] == "新会话"
        assert session["user_id"] == user["id"]
        assert session["model_name"] == "gpt-4o-mini"
        assert state["current_session_id"] == session["id"]
        print(f"  自动创建: id={session['id'][:8]}..., title='{session['title']}'")

        # 已有会话时返回已有会话
        same_session = await session_mgr.get_or_create_session(user_id=user["id"])
        assert same_session["id"] == session["id"]
        print(f"  获取已有: 相同会话 id={same_session['id'][:8]}...")

        passed += 1
        print(f"  >>> Group 1 PASSED")
        print()

        # =============================================
        # 2. 消息保存与加载
        # =============================================
        print("[Test 2] 消息保存与加载")
        print("-" * 40)

        # 保存用户消息
        msg1 = await session_mgr.save_user_message(session["id"], "你好，Python是什么？")
        assert msg1["role"] == "human"
        assert msg1["content"] == "你好，Python是什么？"
        print(f"  保存用户消息: ok")

        # 保存 AI 消息
        msg2 = await session_mgr.save_ai_message(
            session["id"],
            "Python是一种高级编程语言。",
            prompt_tokens=50,
            completion_tokens=20,
        )
        assert msg2["role"] == "ai"
        assert msg2["prompt_tokens"] == 50
        assert msg2["completion_tokens"] == 20
        print(f"  保存 AI 消息: ok (含 Token)")

        # 加载消息
        messages = await session_mgr.load_messages(session["id"])
        assert len(messages) == 2
        assert messages[0]["role"] == "human"
        assert messages[1]["role"] == "ai"
        print(f"  加载消息: {len(messages)} 条, 顺序正确")

        passed += 1
        print(f"  >>> Group 2 PASSED")
        print()

        # =============================================
        # 3. auto_save_turn 一站式保存
        # =============================================
        print("[Test 3] auto_save_turn 一站式保存")
        print("-" * 40)

        await session_mgr.auto_save_turn(
            session_id=session["id"],
            user_message="什么是异步编程？",
            ai_response="异步编程是一种并发编程范式，允许程序在等待I/O时执行其他任务。",
            prompt_tokens=80,
            completion_tokens=35,
        )

        # 验证消息已保存
        messages = await session_mgr.load_messages(session["id"])
        assert len(messages) == 4  # 之前 2 条 + 新 2 条
        assert messages[2]["role"] == "human"
        assert messages[2]["content"] == "什么是异步编程？"
        assert messages[3]["role"] == "ai"
        print(f"  保存一轮对话: 共 {len(messages)} 条消息")

        # 验证会话 Token 累计
        # 注意：save_ai_message() 只保存消息记录，不更新会话 Token 累计
        # 只有 auto_save_turn() 会调用 _accumulate_tokens() 更新会话级统计
        session_info = await session_mgr.get_session_info(session["id"])
        assert session_info["total_prompt_tokens"] == 80   # 仅 auto_save_turn 的 80
        assert session_info["total_completion_tokens"] == 35  # 仅 auto_save_turn 的 35
        print(f"  Token 累计: prompt={session_info['total_prompt_tokens']}, "
              f"completion={session_info['total_completion_tokens']}")

        passed += 1
        print(f"  >>> Group 3 PASSED")
        print()

        # =============================================
        # 4. 自动标题生成
        # =============================================
        print("[Test 4] 自动标题生成")
        print("-" * 40)

        # 短消息 — 完整作为标题
        short_session = await backend.create_session(user["id"], "新会话")
        title = await session_mgr.auto_title(
            short_session["id"],
            "简短问题",
        )
        assert title == "简短问题"
        print(f"  短标题: '{title}'")

        # 长消息 — 截断
        long_msg = "这是一个非常非常非常长的用户消息用来测试标题截断功能是否能够正常工作"
        title2 = await session_mgr.auto_title(
            short_session["id"],
            long_msg,
        )
        max_len = config.session_title_max_length
        assert len(title2) <= max_len + 3  # +3 for "..."
        assert title2.endswith("...")
        print(f"  长标题({len(title2)}字符): '{title2}'")

        passed += 1
        print(f"  >>> Group 4 PASSED")
        print()

        # =============================================
        # 5. 创建新会话
        # =============================================
        print("[Test 5] 创建新会话")
        print("-" * 40)

        old_id = state["current_session_id"]
        new_session = await session_mgr.create_new_session(user["id"])
        assert new_session["id"] != old_id
        assert state["current_session_id"] == new_session["id"]
        assert state["current_session_title"] == "新会话"

        # 验证旧会话数据仍存在
        old_messages = await session_mgr.load_messages(old_id)
        assert len(old_messages) == 4  # 旧数据未丢失
        print(f"  旧会话: {len(old_messages)} 条消息保留")
        print(f"  新会话: id={new_session['id'][:8]}..., 0 条消息")

        passed += 1
        print(f"  >>> Group 5 PASSED")
        print()

        # =============================================
        # 6. 与 ChatEngine 集成
        # =============================================
        print("[Test 6] ChatEngine + SessionManager 集成")
        print("-" * 40)

        engine = ChatEngine(config, state)
        engine.set_system_prompt("你是一个测试助手")

        # 加载旧会话消息到引擎
        old_messages = await session_mgr.load_messages(old_id)
        engine.load_history(old_messages)
        assert engine.message_count == 4
        assert engine.has_history
        print(f"  引擎加载历史: {engine.message_count} 条消息")

        # 保存消息 → 验证可以从 DB 恢复引擎状态
        engine.clear_history()
        assert engine.message_count == 0
        engine.load_history(old_messages)
        assert engine.message_count == 4
        print(f"  从 DB 恢复引擎: {engine.message_count} 条消息")

        # 验证历史消息内容
        history = engine.history
        assert history[2].content == "什么是异步编程？"
        print(f"  消息内容验证通过")

        passed += 1
        print(f"  >>> Group 6 PASSED")
        print()

        # =============================================
        # 7. ChatView 组件验证
        # =============================================
        print("[Test 7] ChatView 组件验证")
        print("-" * 40)

        view = ChatView(state)
        assert view._state is state
        print(f"  ChatView 初始化: ok")

        # 在真实 App 中，session_manager 由 app.py 初始化后放入 state
        state["session_manager"] = session_mgr
        assert state.get("session_manager") is not None
        print(f"  SessionManager 已注入 state: ok")

        print(f"  注: 完整 TUI 交互测试需在终端中运行 uv run python src/main.py")
        print(f"      届时选择「开始对话」即可体验流式多轮对话")

        passed += 1
        print(f"  >>> Group 7 PASSED")
        print()

        # =============================================
        # Result
        # =============================================
        print("=" * 60)
        print(f"  ALL {passed}/{total_groups} TEST GROUPS PASSED!")
        print("=" * 60)
        return passed == total_groups

    except Exception:
        import traceback
        print()
        print("=" * 60)
        print("TEST FAILED WITH EXCEPTION:")
        traceback.print_exc()
        print("=" * 60)
        return False

    finally:
        if backend is not None:
            try:
                await backend.close()
                print()
                print("  [清理] 数据库连接已关闭")
            except Exception as close_err:
                print(f"  [警告] 关闭连接时出错: {close_err}")


if __name__ == "__main__":
    try:
        success = asyncio.run(test_step7())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n用户中断")
        sys.exit(1)
