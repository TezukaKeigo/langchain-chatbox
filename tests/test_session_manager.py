"""
会话管理器单元测试 — 覆盖 SessionManager 全部业务逻辑。

测试策略：
- 使用 SQLite 后端（轻量、快速）
- 每个测试独立创建/清理数据
- 覆盖：会话 CRUD / 消息保存 / Token 累计 / 标题生成 / 导出 / 搜索
"""

import os
import tempfile

import pytest
from src.core.session_manager import SessionManager


class TestSessionCreation:
    """会话创建与获取"""

    async def test_get_or_create_creates_new(self, sqlite_backend, state, config_manager):
        u = await sqlite_backend.create_user("sess_user")
        sm = SessionManager(sqlite_backend, state, config_manager)

        session = await sm.get_or_create_session(u["id"], model_name="gpt-4o")
        assert session["title"] == "新会话"
        assert session["user_id"] == u["id"]
        assert session["model_name"] == "gpt-4o"
        assert state["current_session_id"] == session["id"]

    async def test_get_or_create_returns_existing(self, sqlite_backend, state, config_manager):
        u = await sqlite_backend.create_user("exist_user")
        sm = SessionManager(sqlite_backend, state, config_manager)

        s1 = await sm.get_or_create_session(u["id"])
        # 第二次调用应返回同一会话
        s2 = await sm.get_or_create_session(u["id"])
        assert s2["id"] == s1["id"]

    async def test_create_new_session(self, sqlite_backend, state, config_manager):
        u = await sqlite_backend.create_user("new_user")
        sm = SessionManager(sqlite_backend, state, config_manager)

        s1 = await sm.create_new_session(u["id"], model_name="kimi 2.6")
        s2 = await sm.create_new_session(u["id"], model_name="qwen-plus")

        assert s1["id"] != s2["id"]
        assert state["current_session_id"] == s2["id"]

    async def test_create_new_session_preserves_old(self, sqlite_backend, state, config_manager):
        """新建会话后旧会话数据保留"""
        u = await sqlite_backend.create_user("preserve_user")
        sm = SessionManager(sqlite_backend, state, config_manager)

        s1 = await sm.get_or_create_session(u["id"])
        await sm.save_user_message(s1["id"], "hello")
        await sm.save_ai_message(s1["id"], "hi", prompt_tokens=10, completion_tokens=5)

        s2 = await sm.create_new_session(u["id"])
        # 旧会话消息仍存在
        msgs = await sm.load_messages(s1["id"])
        assert len(msgs) == 2


class TestMessageSave:
    """消息保存与加载"""

    async def test_save_user_message(self, sqlite_backend, state, config_manager):
        u = await sqlite_backend.create_user("msg_user")
        sm = SessionManager(sqlite_backend, state, config_manager)
        s = await sm.get_or_create_session(u["id"])

        m = await sm.save_user_message(s["id"], "你好世界")
        assert m["role"] == "human"
        assert m["content"] == "你好世界"

    async def test_save_ai_message(self, sqlite_backend, state, config_manager):
        u = await sqlite_backend.create_user("ai_user")
        sm = SessionManager(sqlite_backend, state, config_manager)
        s = await sm.get_or_create_session(u["id"])

        m = await sm.save_ai_message(s["id"], "回复内容", prompt_tokens=50, completion_tokens=30)
        assert m["role"] == "ai"
        assert m["prompt_tokens"] == 50
        assert m["completion_tokens"] == 30

    async def test_load_messages(self, sqlite_backend, state, config_manager):
        u = await sqlite_backend.create_user("load_user")
        sm = SessionManager(sqlite_backend, state, config_manager)
        s = await sm.get_or_create_session(u["id"])

        await sm.save_user_message(s["id"], "Q1")
        await sm.save_ai_message(s["id"], "A1")
        await sm.save_user_message(s["id"], "Q2")
        await sm.save_ai_message(s["id"], "A2")

        msgs = await sm.load_messages(s["id"])
        assert len(msgs) == 4
        assert msgs[0]["content"] == "Q1"
        assert msgs[3]["content"] == "A2"

    async def test_load_messages_empty(self, sqlite_backend, state, config_manager):
        u = await sqlite_backend.create_user("empty_user")
        sm = SessionManager(sqlite_backend, state, config_manager)
        s = await sm.get_or_create_session(u["id"])
        msgs = await sm.load_messages(s["id"])
        assert msgs == []


class TestAutoSaveTurn:
    """一站式保存一轮对话"""

    async def test_auto_save_turn(self, sqlite_backend, state, config_manager):
        u = await sqlite_backend.create_user("turn_user")
        sm = SessionManager(sqlite_backend, state, config_manager)
        s = await sm.get_or_create_session(u["id"])

        await sm.auto_save_turn(
            s["id"],
            user_message="用户问题",
            ai_response="AI回答",
            prompt_tokens=100,
            completion_tokens=50,
        )

        msgs = await sm.load_messages(s["id"])
        assert len(msgs) == 2
        assert msgs[0]["role"] == "human"
        assert msgs[1]["role"] == "ai"

    async def test_auto_save_turn_accumulates_tokens(self, sqlite_backend, state, config_manager):
        u = await sqlite_backend.create_user("token_user")
        sm = SessionManager(sqlite_backend, state, config_manager)
        s = await sm.get_or_create_session(u["id"])

        await sm.auto_save_turn(s["id"], "Q1", "A1", prompt_tokens=100, completion_tokens=50)
        await sm.auto_save_turn(s["id"], "Q2", "A2", prompt_tokens=80, completion_tokens=40)

        tokens = await sm.get_total_tokens(s["id"])
        assert tokens["prompt"] == 180
        assert tokens["completion"] == 90
        assert tokens["total"] == 270

    async def test_auto_save_turn_zero_tokens(self, sqlite_backend, state, config_manager):
        """零 Token 轮次不累加"""
        u = await sqlite_backend.create_user("zero_token")
        sm = SessionManager(sqlite_backend, state, config_manager)
        s = await sm.get_or_create_session(u["id"])

        await sm.auto_save_turn(s["id"], "Q1", "A1", prompt_tokens=100, completion_tokens=50)
        await sm.auto_save_turn(s["id"], "Q2", "A2")  # 默认 0

        tokens = await sm.get_total_tokens(s["id"])
        assert tokens["total"] == 150  # 仅第一轮


class TestAutoTitle:
    """自动标题生成"""

    async def test_short_title(self, sqlite_backend, state, config_manager):
        u = await sqlite_backend.create_user("title_user")
        sm = SessionManager(sqlite_backend, state, config_manager)
        s = await sm.get_or_create_session(u["id"])

        title = await sm.auto_title(s["id"], "简短问题")
        assert title == "简短问题"
        assert state["current_session_title"] == "简短问题"

    async def test_long_title_truncated(self, sqlite_backend, state, config_manager):
        u = await sqlite_backend.create_user("long_title")
        sm = SessionManager(sqlite_backend, state, config_manager)
        s = await sm.get_or_create_session(u["id"])

        long_msg = "这是一个非常非常非常非常非常非常长的用户消息用来测试标题截断功能"
        title = await sm.auto_title(s["id"], long_msg)
        max_len = config_manager.session_title_max_length
        assert len(title) <= max_len + 3  # +3 for "..."
        assert title.endswith("...")

    async def test_title_strips_newlines(self, sqlite_backend, state, config_manager):
        u = await sqlite_backend.create_user("newline_user")
        sm = SessionManager(sqlite_backend, state, config_manager)
        s = await sm.get_or_create_session(u["id"])

        title = await sm.auto_title(s["id"], "第一行\n第二行\n第三行")
        assert "\n" not in title
        assert "\r" not in title


class TestSessionManagement:
    """会话管理：列表/重命名/删除/切换"""

    async def test_list_user_sessions(self, sqlite_backend, state, config_manager):
        u = await sqlite_backend.create_user("list_sess")
        sm = SessionManager(sqlite_backend, state, config_manager)
        await sm.create_new_session(u["id"])
        await sm.create_new_session(u["id"])

        sessions = await sm.list_user_sessions(u["id"])
        assert len(sessions) == 2

    async def test_rename_session(self, sqlite_backend, state, config_manager):
        u = await sqlite_backend.create_user("rename_user")
        sm = SessionManager(sqlite_backend, state, config_manager)
        s = await sm.get_or_create_session(u["id"])

        updated = await sm.rename_session(s["id"], "新标题")
        assert updated["title"] == "新标题"

    async def test_rename_nonexistent_session(self, sqlite_backend, state, config_manager):
        u = await sqlite_backend.create_user("bad_rename")
        sm = SessionManager(sqlite_backend, state, config_manager)
        with pytest.raises(ValueError):
            await sm.rename_session("nonexistent", "test")

    async def test_rename_current_syncs_state(self, sqlite_backend, state, config_manager):
        u = await sqlite_backend.create_user("sync_user")
        sm = SessionManager(sqlite_backend, state, config_manager)
        s = await sm.get_or_create_session(u["id"])

        await sm.rename_session(s["id"], "同步标题")
        assert state["current_session_title"] == "同步标题"

    async def test_delete_session(self, sqlite_backend, state, config_manager):
        u = await sqlite_backend.create_user("del_sess")
        sm = SessionManager(sqlite_backend, state, config_manager)
        s = await sm.get_or_create_session(u["id"])

        assert await sm.delete_session(s["id"]) is True
        assert await sm.get_session_info(s["id"]) is None

    async def test_delete_current_clears_state(self, sqlite_backend, state, config_manager):
        u = await sqlite_backend.create_user("del_current")
        sm = SessionManager(sqlite_backend, state, config_manager)
        s = await sm.get_or_create_session(u["id"])

        await sm.delete_session(s["id"])
        assert state["current_session_id"] is None
        assert state["current_session_title"] is None

    async def test_delete_nonexistent_session(self, sqlite_backend, state, config_manager):
        u = await sqlite_backend.create_user("no_del")
        sm = SessionManager(sqlite_backend, state, config_manager)
        assert await sm.delete_session("nonexistent") is False

    async def test_switch_to_session(self, sqlite_backend, state, config_manager):
        u = await sqlite_backend.create_user("switch_user")
        sm = SessionManager(sqlite_backend, state, config_manager)

        s1 = await sm.create_new_session(u["id"])
        s2 = await sm.create_new_session(u["id"])
        # 当前是 s2
        assert state["current_session_id"] == s2["id"]

        # 切换到 s1
        sm.switch_to_session(s1)
        assert state["current_session_id"] == s1["id"]
        assert state["current_session_title"] == s1["title"]

        # get_or_create 应返回 s1
        session = await sm.get_or_create_session(u["id"])
        assert session["id"] == s1["id"]

    async def test_clear_current_session(self, sqlite_backend, state, config_manager):
        u = await sqlite_backend.create_user("clear_sess")
        sm = SessionManager(sqlite_backend, state, config_manager)
        await sm.get_or_create_session(u["id"])

        sm.clear_current_session()
        assert state["current_session_id"] is None
        assert state["current_session_title"] is None


class TestSessionExport:
    """会话导出为 Markdown"""

    async def test_export_basic(self, sqlite_backend, state, config_manager):
        u = await sqlite_backend.create_user("export_user")
        sm = SessionManager(sqlite_backend, state, config_manager)
        s = await sm.get_or_create_session(u["id"], model_name="deepseek-v4-flash")
        await sm.save_user_message(s["id"], "你好")
        await sm.save_ai_message(s["id"], "你好！")

        with tempfile.TemporaryDirectory() as tmp:
            config_manager._config["export"] = {
                "path_template": f"{tmp}/{{username}}/{{session_title}}_{{date}}.md"
            }
            file_path = await sm.export_session(s["id"], "export_user")
            assert os.path.exists(file_path)
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            assert "你好" in content
            assert "deepseek-v4-flash" in content

    async def test_export_nonexistent_session(self, sqlite_backend, state, config_manager):
        u = await sqlite_backend.create_user("noexp_user")
        sm = SessionManager(sqlite_backend, state, config_manager)
        with pytest.raises(ValueError, match="不存在"):
            await sm.export_session("nonexistent-id", "user")

    async def test_export_empty_session(self, sqlite_backend, state, config_manager):
        u = await sqlite_backend.create_user("empty_exp")
        sm = SessionManager(sqlite_backend, state, config_manager)
        s = await sm.get_or_create_session(u["id"])

        with tempfile.TemporaryDirectory() as tmp:
            config_manager._config["export"] = {
                "path_template": f"{tmp}/{{username}}/{{session_title}}_{{date}}.md"
            }
            file_path = await sm.export_session(s["id"], "empty_exp")
            assert os.path.exists(file_path)


class TestSessionSearch:
    """消息搜索"""

    async def test_search_messages(self, sqlite_backend, state, config_manager):
        u = await sqlite_backend.create_user("search_user")
        sm = SessionManager(sqlite_backend, state, config_manager)
        s = await sm.get_or_create_session(u["id"])
        await sm.save_user_message(s["id"], "Python入门")
        await sm.save_ai_message(s["id"], "Python很好学")

        results = await sm.search_messages(u["id"], "Python")
        assert len(results) == 2

    async def test_search_no_match(self, sqlite_backend, state, config_manager):
        u = await sqlite_backend.create_user("nomatch")
        sm = SessionManager(sqlite_backend, state, config_manager)
        s = await sm.get_or_create_session(u["id"])
        await sm.save_user_message(s["id"], "hello")

        results = await sm.search_messages(u["id"], "ZZZNOTEXIST")
        assert results == []

    async def test_search_results_have_session_title(self, sqlite_backend, state, config_manager):
        u = await sqlite_backend.create_user("title_search")
        sm = SessionManager(sqlite_backend, state, config_manager)
        s = await sm.get_or_create_session(u["id"])
        await sm.save_user_message(s["id"], "test message")

        results = await sm.search_messages(u["id"], "test")
        assert len(results) >= 1
        assert "session_title" in results[0]


class TestTokenStats:
    """Token 统计"""

    async def test_get_total_tokens(self, sqlite_backend, state, config_manager):
        u = await sqlite_backend.create_user("token_stats")
        sm = SessionManager(sqlite_backend, state, config_manager)
        s = await sm.get_or_create_session(u["id"])

        tokens = await sm.get_total_tokens(s["id"])
        assert tokens == {"prompt": 0, "completion": 0, "total": 0}

        await sm.auto_save_turn(s["id"], "Q", "A", prompt_tokens=200, completion_tokens=100)
        tokens = await sm.get_total_tokens(s["id"])
        assert tokens["prompt"] == 200
        assert tokens["completion"] == 100
        assert tokens["total"] == 300

    async def test_get_total_tokens_nonexistent(self, sqlite_backend, state, config_manager):
        u = await sqlite_backend.create_user("no_token")
        sm = SessionManager(sqlite_backend, state, config_manager)
        tokens = await sm.get_total_tokens("nonexistent")
        assert tokens == {"prompt": 0, "completion": 0, "total": 0}
