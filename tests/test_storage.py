"""
存储后端单元测试 — 覆盖 SQLite 和 File 两种后端的全部 CRUD 操作。

测试策略：
- 使用独立的临时数据库/目录，测试间完全隔离
- 每种后端运行相同的测试用例（通过参数化 fixture）
- 覆盖：User/Session/Message/Preset/UserConfig CRUD + 级联删除 + 唯一性校验
"""

import pytest


# ============================================================
# 标记：SQLite 后端测试
# ============================================================

class TestSQLiteUserCRUD:
    """SQLite — 用户管理 CRUD"""

    async def test_create_user(self, sqlite_backend):
        u = await sqlite_backend.create_user("alice", "gpt-4o")
        assert u["username"] == "alice"
        assert u["default_model"] == "gpt-4o"
        assert "id" in u
        assert "created_at" in u

    async def test_create_user_default_model(self, sqlite_backend):
        u = await sqlite_backend.create_user("bob")
        assert u["default_model"] == "gpt-4o-mini"

    async def test_create_duplicate_user(self, sqlite_backend):
        await sqlite_backend.create_user("alice")
        with pytest.raises(ValueError, match="已存在"):
            await sqlite_backend.create_user("alice")

    async def test_get_user(self, sqlite_backend):
        u = await sqlite_backend.create_user("charlie")
        fetched = await sqlite_backend.get_user(u["id"])
        assert fetched["username"] == "charlie"

    async def test_get_nonexistent_user(self, sqlite_backend):
        assert await sqlite_backend.get_user("nonexistent-id") is None

    async def test_get_user_by_username(self, sqlite_backend):
        await sqlite_backend.create_user("dave")
        fetched = await sqlite_backend.get_user_by_username("dave")
        assert fetched is not None
        assert fetched["username"] == "dave"

    async def test_get_user_by_username_not_found(self, sqlite_backend):
        assert await sqlite_backend.get_user_by_username("nobody") is None

    async def test_list_users(self, sqlite_backend):
        await sqlite_backend.create_user("u1")
        await sqlite_backend.create_user("u2")
        users = await sqlite_backend.list_users()
        assert len(users) == 2

    async def test_list_users_empty(self, sqlite_backend):
        users = await sqlite_backend.list_users()
        assert users == []

    async def test_update_user(self, sqlite_backend):
        u = await sqlite_backend.create_user("eve")
        updated = await sqlite_backend.update_user(u["id"], default_model="gpt-4o-mini")
        assert updated["default_model"] == "gpt-4o-mini"

    async def test_update_nonexistent_user(self, sqlite_backend):
        with pytest.raises(ValueError):
            await sqlite_backend.update_user("nonexistent", default_model="x")

    async def test_delete_user(self, sqlite_backend):
        u = await sqlite_backend.create_user("frank")
        assert await sqlite_backend.delete_user(u["id"]) is True
        assert await sqlite_backend.get_user(u["id"]) is None

    async def test_delete_nonexistent_user(self, sqlite_backend):
        assert await sqlite_backend.delete_user("nonexistent") is False


class TestSQLiteSessionCRUD:
    """SQLite — 会话管理 CRUD"""

    async def test_create_session(self, sqlite_backend, test_user):
        s = await sqlite_backend.create_session(test_user["id"], "测试会话", "gpt-4o")
        assert s["title"] == "测试会话"
        assert s["user_id"] == test_user["id"]
        assert s["model_name"] == "gpt-4o"

    async def test_create_session_defaults(self, sqlite_backend, test_user):
        s = await sqlite_backend.create_session(test_user["id"])
        assert s["title"] == "新会话"
        assert s["model_name"] == "gpt-4o-mini"

    async def test_get_session(self, sqlite_backend, test_user):
        s = await sqlite_backend.create_session(test_user["id"])
        fetched = await sqlite_backend.get_session(s["id"])
        assert fetched["title"] == s["title"]

    async def test_get_nonexistent_session(self, sqlite_backend):
        assert await sqlite_backend.get_session("nonexistent") is None

    async def test_list_sessions_by_user(self, sqlite_backend, test_user):
        await sqlite_backend.create_session(test_user["id"], "S1")
        await sqlite_backend.create_session(test_user["id"], "S2")
        sessions = await sqlite_backend.list_sessions_by_user(test_user["id"])
        assert len(sessions) == 2
        # 按更新时间倒序排列
        assert sessions[0]["title"] == "S2"

    async def test_list_sessions_empty(self, sqlite_backend, test_user):
        sessions = await sqlite_backend.list_sessions_by_user(test_user["id"])
        assert sessions == []

    async def test_update_session(self, sqlite_backend, test_user):
        s = await sqlite_backend.create_session(test_user["id"], "旧标题")
        updated = await sqlite_backend.update_session(s["id"], title="新标题")
        assert updated["title"] == "新标题"

    async def test_update_nonexistent_session(self, sqlite_backend):
        with pytest.raises(ValueError):
            await sqlite_backend.update_session("nonexistent", title="x")

    async def test_delete_session(self, sqlite_backend, test_user):
        s = await sqlite_backend.create_session(test_user["id"])
        assert await sqlite_backend.delete_session(s["id"]) is True
        assert await sqlite_backend.get_session(s["id"]) is None

    async def test_delete_nonexistent_session(self, sqlite_backend):
        assert await sqlite_backend.delete_session("nonexistent") is False


class TestSQLiteMessageCRUD:
    """SQLite — 消息管理 CRUD"""

    async def test_add_message(self, sqlite_backend, test_user):
        s = await sqlite_backend.create_session(test_user["id"])
        m = await sqlite_backend.add_message(s["id"], "human", "你好", 10, 0)
        assert m["role"] == "human"
        assert m["content"] == "你好"
        assert m["prompt_tokens"] == 10

    async def test_list_messages_by_session(self, sqlite_backend, test_user):
        s = await sqlite_backend.create_session(test_user["id"])
        await sqlite_backend.add_message(s["id"], "human", "Q1")
        await sqlite_backend.add_message(s["id"], "ai", "A1")
        msgs = await sqlite_backend.list_messages_by_session(s["id"])
        assert len(msgs) == 2
        assert msgs[0]["role"] == "human"
        assert msgs[1]["role"] == "ai"

    async def test_list_messages_empty(self, sqlite_backend, test_user):
        s = await sqlite_backend.create_session(test_user["id"])
        msgs = await sqlite_backend.list_messages_by_session(s["id"])
        assert msgs == []

    async def test_search_messages(self, sqlite_backend, test_user):
        s = await sqlite_backend.create_session(test_user["id"], "搜索测试")
        await sqlite_backend.add_message(s["id"], "human", "Python入门教程")
        await sqlite_backend.add_message(s["id"], "ai", "Python很适合初学者")
        results = await sqlite_backend.search_messages(test_user["id"], "Python")
        assert len(results) == 2
        # 每条结果都应附带 session_title
        for r in results:
            assert r["session_title"] == "搜索测试"

    async def test_search_messages_no_match(self, sqlite_backend, test_user):
        s = await sqlite_backend.create_session(test_user["id"])
        await sqlite_backend.add_message(s["id"], "human", "hello")
        results = await sqlite_backend.search_messages(test_user["id"], "ZZZNOTEXIST")
        assert results == []

    async def test_search_messages_user_isolation(self, sqlite_backend, test_user):
        """搜索只返回当前用户的消息"""
        u2 = await sqlite_backend.create_user("other_user")
        s2 = await sqlite_backend.create_session(u2["id"], "Other Session")
        await sqlite_backend.add_message(s2["id"], "human", "Python for beginners")
        # 用 test_user 搜索不应返回 u2 的消息
        results = await sqlite_backend.search_messages(test_user["id"], "Python")
        assert len(results) == 0


class TestSQLitePresetCRUD:
    """SQLite — 预设管理 CRUD"""

    async def test_create_builtin_preset(self, sqlite_backend):
        p = await sqlite_backend.create_preset(
            "代码助手", "你是一个代码专家...", is_builtin=True
        )
        assert p["name"] == "代码助手"
        assert p["is_builtin"] is True
        assert p["user_id"] is None

    async def test_create_user_preset(self, sqlite_backend, test_user):
        p = await sqlite_backend.create_preset(
            "我的预设", "自定义提示词", user_id=test_user["id"]
        )
        assert p["user_id"] == test_user["id"]
        assert p["is_builtin"] is False

    async def test_get_preset(self, sqlite_backend):
        p = await sqlite_backend.create_preset("翻译官", "翻译文本...", is_builtin=True)
        fetched = await sqlite_backend.get_preset(p["id"])
        assert fetched["name"] == "翻译官"

    async def test_get_nonexistent_preset(self, sqlite_backend):
        assert await sqlite_backend.get_preset("nonexistent") is None

    async def test_list_presets_all(self, sqlite_backend, test_user):
        """list_presets(user_id=None) 只返回内置预设"""
        await sqlite_backend.create_preset("内置1", "p1", is_builtin=True)
        await sqlite_backend.create_preset("内置2", "p2", is_builtin=True)
        await sqlite_backend.create_preset("私有", "p3", user_id=test_user["id"])
        builtins = await sqlite_backend.list_presets(user_id=None)
        assert len(builtins) == 2
        assert all(p["is_builtin"] for p in builtins)

    async def test_list_presets_for_user(self, sqlite_backend, test_user):
        """list_presets(user_id=...) 返回内置 + 用户私有"""
        await sqlite_backend.create_preset("内置", "p1", is_builtin=True)
        await sqlite_backend.create_preset("私有", "p2", user_id=test_user["id"])
        all_presets = await sqlite_backend.list_presets(user_id=test_user["id"])
        assert len(all_presets) == 2

    async def test_update_preset(self, sqlite_backend, test_user):
        p = await sqlite_backend.create_preset("旧名称", "prompt", user_id=test_user["id"])
        updated = await sqlite_backend.update_preset(p["id"], name="新名称")
        assert updated["name"] == "新名称"

    async def test_update_builtin_preset_rejected(self, sqlite_backend):
        """内置预设不可编辑"""
        p = await sqlite_backend.create_preset("内置预设", "prompt", is_builtin=True)
        with pytest.raises(ValueError):
            await sqlite_backend.update_preset(p["id"], name="hack")

    async def test_delete_preset(self, sqlite_backend, test_user):
        p = await sqlite_backend.create_preset("待删除", "prompt", user_id=test_user["id"])
        assert await sqlite_backend.delete_preset(p["id"]) is True

    async def test_delete_builtin_preset_rejected(self, sqlite_backend):
        """内置预设不可删除"""
        p = await sqlite_backend.create_preset("内置", "prompt", is_builtin=True)
        with pytest.raises(ValueError):
            await sqlite_backend.delete_preset(p["id"])

    async def test_delete_nonexistent_preset(self, sqlite_backend):
        assert await sqlite_backend.delete_preset("nonexistent") is False


class TestSQLiteUserConfigCRUD:
    """SQLite — 用户配置 CRUD"""

    async def test_set_user_config(self, sqlite_backend, test_user):
        cfg = await sqlite_backend.set_user_config(test_user["id"], "theme", "dark")
        assert cfg["key"] == "theme"
        assert cfg["value"] == "dark"

    async def test_get_user_config(self, sqlite_backend, test_user):
        await sqlite_backend.set_user_config(test_user["id"], "font_size", "14")
        assert await sqlite_backend.get_user_config(test_user["id"], "font_size") == "14"

    async def test_get_nonexistent_config(self, sqlite_backend, test_user):
        assert await sqlite_backend.get_user_config(test_user["id"], "nonexistent") is None

    async def test_get_all_user_configs(self, sqlite_backend, test_user):
        await sqlite_backend.set_user_config(test_user["id"], "k1", "v1")
        await sqlite_backend.set_user_config(test_user["id"], "k2", "v2")
        all_cfg = await sqlite_backend.get_all_user_configs(test_user["id"])
        assert all_cfg == {"k1": "v1", "k2": "v2"}

    async def test_set_user_config_upsert(self, sqlite_backend, test_user):
        """重复设置同一 key 应更新值"""
        await sqlite_backend.set_user_config(test_user["id"], "theme", "dark")
        await sqlite_backend.set_user_config(test_user["id"], "theme", "light")
        assert await sqlite_backend.get_user_config(test_user["id"], "theme") == "light"

    async def test_delete_user_config(self, sqlite_backend, test_user):
        await sqlite_backend.set_user_config(test_user["id"], "temp", "val")
        assert await sqlite_backend.delete_user_config(test_user["id"], "temp") is True
        assert await sqlite_backend.get_user_config(test_user["id"], "temp") is None

    async def test_delete_nonexistent_config(self, sqlite_backend, test_user):
        assert await sqlite_backend.delete_user_config(test_user["id"], "nonexistent") is False


class TestSQLiteCascadeDelete:
    """SQLite — 级联删除验证"""

    async def test_delete_user_cascades_sessions(self, sqlite_backend):
        u = await sqlite_backend.create_user("cascade_test")
        s = await sqlite_backend.create_session(u["id"], "Session")
        await sqlite_backend.add_message(s["id"], "human", "hello")
        # 删除用户
        await sqlite_backend.delete_user(u["id"])
        # 会话应被级联删除
        assert await sqlite_backend.get_session(s["id"]) is None

    async def test_delete_session_cascades_messages(self, sqlite_backend, test_user):
        s = await sqlite_backend.create_session(test_user["id"], "Session")
        await sqlite_backend.add_message(s["id"], "human", "hello")
        # 删除会话
        await sqlite_backend.delete_session(s["id"])
        # 消息应被级联删除
        msgs = await sqlite_backend.list_messages_by_session(s["id"])
        assert msgs == []

    async def test_delete_user_cascades_presets(self, sqlite_backend):
        u = await sqlite_backend.create_user("preset_cascade")
        p = await sqlite_backend.create_preset("我的预设", "prompt", user_id=u["id"])
        await sqlite_backend.delete_user(u["id"])
        assert await sqlite_backend.get_preset(p["id"]) is None

    async def test_delete_user_cascades_configs(self, sqlite_backend):
        u = await sqlite_backend.create_user("config_cascade")
        await sqlite_backend.set_user_config(u["id"], "key", "val")
        await sqlite_backend.delete_user(u["id"])
        assert await sqlite_backend.get_user_config(u["id"], "key") is None

    async def test_delete_user_preserves_other_users(self, sqlite_backend):
        """删除用户 A 不影响用户 B 的数据"""
        u1 = await sqlite_backend.create_user("user_a")
        u2 = await sqlite_backend.create_user("user_b")
        s1 = await sqlite_backend.create_session(u1["id"], "A-Session")
        s2 = await sqlite_backend.create_session(u2["id"], "B-Session")
        await sqlite_backend.delete_user(u1["id"])
        # u2 的会话应保留
        assert await sqlite_backend.get_session(s2["id"]) is not None
        # u1 的会话应被删除
        assert await sqlite_backend.get_session(s1["id"]) is None


# ============================================================
# 标记：File 后端测试
# ============================================================

class TestFileUserCRUD:
    """File — 用户管理 CRUD"""

    async def test_create_user(self, file_backend):
        u = await file_backend.create_user("alice", "gpt-4o")
        assert u["username"] == "alice"
        assert u["default_model"] == "gpt-4o"
        assert "id" in u

    async def test_create_duplicate_user(self, file_backend):
        await file_backend.create_user("alice")
        with pytest.raises(ValueError, match="已存在"):
            await file_backend.create_user("alice")

    async def test_get_user(self, file_backend):
        u = await file_backend.create_user("bob")
        fetched = await file_backend.get_user(u["id"])
        assert fetched["username"] == "bob"

    async def test_get_nonexistent_user(self, file_backend):
        assert await file_backend.get_user("nonexistent") is None

    async def test_get_user_by_username(self, file_backend):
        await file_backend.create_user("charlie")
        fetched = await file_backend.get_user_by_username("charlie")
        assert fetched is not None

    async def test_list_users(self, file_backend):
        await file_backend.create_user("u1")
        await file_backend.create_user("u2")
        users = await file_backend.list_users()
        assert len(users) == 2

    async def test_update_user(self, file_backend):
        u = await file_backend.create_user("dave")
        updated = await file_backend.update_user(u["id"], default_model="claude-4")
        assert updated["default_model"] == "claude-4"

    async def test_delete_user(self, file_backend):
        u = await file_backend.create_user("eve")
        assert await file_backend.delete_user(u["id"]) is True
        assert await file_backend.get_user(u["id"]) is None


class TestFileSessionCRUD:
    """File — 会话管理 CRUD"""

    async def test_create_and_get_session(self, file_backend):
        u = await file_backend.create_user("sess_user")
        s = await file_backend.create_session(u["id"], "测试会话", "gpt-4o")
        fetched = await file_backend.get_session(s["id"])
        assert fetched["title"] == "测试会话"

    async def test_list_sessions_by_user(self, file_backend):
        u = await file_backend.create_user("list_user")
        await file_backend.create_session(u["id"], "S1")
        await file_backend.create_session(u["id"], "S2")
        sessions = await file_backend.list_sessions_by_user(u["id"])
        assert len(sessions) == 2

    async def test_update_session(self, file_backend):
        u = await file_backend.create_user("update_user")
        s = await file_backend.create_session(u["id"], "旧标题")
        updated = await file_backend.update_session(s["id"], title="新标题")
        assert updated["title"] == "新标题"

    async def test_delete_session(self, file_backend):
        u = await file_backend.create_user("del_user")
        s = await file_backend.create_session(u["id"])
        assert await file_backend.delete_session(s["id"]) is True


class TestFileMessageCRUD:
    """File — 消息管理 CRUD"""

    async def test_add_and_list_messages(self, file_backend):
        u = await file_backend.create_user("msg_user")
        s = await file_backend.create_session(u["id"])
        await file_backend.add_message(s["id"], "human", "Q1", 10, 0)
        await file_backend.add_message(s["id"], "ai", "A1", 0, 5)
        msgs = await file_backend.list_messages_by_session(s["id"])
        assert len(msgs) == 2
        assert msgs[0]["role"] == "human"

    async def test_search_messages(self, file_backend):
        u = await file_backend.create_user("search_user")
        s = await file_backend.create_session(u["id"], "搜索会话")
        await file_backend.add_message(s["id"], "human", "Python基础教程")
        await file_backend.add_message(s["id"], "ai", "我们来学习Python")
        results = await file_backend.search_messages(u["id"], "Python")
        assert len(results) == 2
        for r in results:
            assert r["session_title"] == "搜索会话"

    async def test_search_no_match(self, file_backend):
        u = await file_backend.create_user("nomatch_user")
        s = await file_backend.create_session(u["id"])
        await file_backend.add_message(s["id"], "human", "hello")
        results = await file_backend.search_messages(u["id"], "ZZZ")
        assert results == []


class TestFilePresetCRUD:
    """File — 预设管理 CRUD"""

    async def test_create_preset(self, file_backend):
        p = await file_backend.create_preset("助手", "你是一个助手", is_builtin=True)
        assert p["name"] == "助手"
        assert p["is_builtin"] is True

    async def test_list_presets(self, file_backend):
        u = await file_backend.create_user("preset_user")
        await file_backend.create_preset("内置", "p1", is_builtin=True)
        await file_backend.create_preset("私有", "p2", user_id=u["id"])
        builtins = await file_backend.list_presets(user_id=None)
        assert len(builtins) == 1
        all_for_user = await file_backend.list_presets(user_id=u["id"])
        assert len(all_for_user) == 2

    async def test_update_builtin_rejected(self, file_backend):
        p = await file_backend.create_preset("内置", "prompt", is_builtin=True)
        with pytest.raises(ValueError):
            await file_backend.update_preset(p["id"], name="hack")

    async def test_delete_builtin_rejected(self, file_backend):
        p = await file_backend.create_preset("内置", "prompt", is_builtin=True)
        with pytest.raises(ValueError):
            await file_backend.delete_preset(p["id"])


class TestFileUserConfigCRUD:
    """File — 用户配置 CRUD"""

    async def test_set_and_get_config(self, file_backend):
        u = await file_backend.create_user("cfg_user")
        await file_backend.set_user_config(u["id"], "theme", "dark")
        assert await file_backend.get_user_config(u["id"], "theme") == "dark"

    async def test_upsert_config(self, file_backend):
        u = await file_backend.create_user("upsert_user")
        await file_backend.set_user_config(u["id"], "k", "v1")
        await file_backend.set_user_config(u["id"], "k", "v2")
        assert await file_backend.get_user_config(u["id"], "k") == "v2"

    async def test_get_all_configs(self, file_backend):
        u = await file_backend.create_user("all_cfg")
        await file_backend.set_user_config(u["id"], "a", "1")
        await file_backend.set_user_config(u["id"], "b", "2")
        all_cfg = await file_backend.get_all_user_configs(u["id"])
        assert all_cfg == {"a": "1", "b": "2"}

    async def test_delete_config(self, file_backend):
        u = await file_backend.create_user("del_cfg")
        await file_backend.set_user_config(u["id"], "temp", "val")
        assert await file_backend.delete_user_config(u["id"], "temp") is True
        assert await file_backend.get_user_config(u["id"], "temp") is None


class TestFileCascadeDelete:
    """File — 级联删除验证（手动实现）"""

    async def test_delete_user_cascades(self, file_backend):
        u = await file_backend.create_user("cascade")
        s = await file_backend.create_session(u["id"])
        await file_backend.add_message(s["id"], "human", "hello")
        p = await file_backend.create_preset("我的", "prompt", user_id=u["id"])
        await file_backend.set_user_config(u["id"], "k", "v")

        await file_backend.delete_user(u["id"])

        # 所有关联数据都应被清理
        assert await file_backend.get_user(u["id"]) is None
        assert await file_backend.get_session(s["id"]) is None
        assert await file_backend.get_preset(p["id"]) is None
        assert await file_backend.get_user_config(u["id"], "k") is None

    async def test_delete_session_cascades_messages(self, file_backend):
        u = await file_backend.create_user("sess_cascade")
        s = await file_backend.create_session(u["id"])
        await file_backend.add_message(s["id"], "human", "hello")
        await file_backend.delete_session(s["id"])
        msgs = await file_backend.list_messages_by_session(s["id"])
        assert msgs == []


# ============================================================
# Factory 测试
# ============================================================

class TestStorageFactory:
    """存储工厂测试"""

    async def test_create_sqlite(self, temp_dir, config_manager):
        """工厂创建 SQLite 后端"""
        from src.storage.factory import StorageFactory
        from src.storage.sqlite_backend import SQLiteBackend

        config_manager._config["storage"] = config_manager._config.get("storage", {})
        config_manager._config["storage"]["type"] = "sqlite"
        config_manager._config["storage"]["sqlite"] = {"path": f"{temp_dir}/app.db"}

        storage = await StorageFactory.create(config_manager)
        assert isinstance(storage, SQLiteBackend)
        await storage.close()

    async def test_create_file(self, temp_dir, config_manager):
        """工厂创建 File 后端"""
        from src.storage.factory import StorageFactory
        from src.storage.file_backend import FileBackend

        config_manager._config["storage"] = config_manager._config.get("storage", {})
        config_manager._config["storage"]["type"] = "file"
        config_manager._config["storage"]["file"] = {
            "path": f"{temp_dir}/file_store",
            "format": "json",
        }

        storage = await StorageFactory.create(config_manager)
        assert isinstance(storage, FileBackend)
        await storage.close()

    async def test_unsupported_backend(self, config_manager):
        """不支持的存储类型抛出 ValueError"""
        from src.storage.factory import StorageFactory

        config_manager._config["storage"] = config_manager._config.get("storage", {})
        config_manager._config["storage"]["type"] = "mongodb"

        with pytest.raises(ValueError, match="不支持"):
            await StorageFactory.create(config_manager)

    async def test_supported_backends_list(self):
        """验证支持的后端列表"""
        from src.storage.factory import StorageFactory
        assert "sqlite" in StorageFactory._SUPPORTED_BACKENDS
        assert "mysql" in StorageFactory._SUPPORTED_BACKENDS
        assert "file" in StorageFactory._SUPPORTED_BACKENDS


# ============================================================
# 跨后端一致性测试
# ============================================================

class TestCrossBackendConsistency:
    """验证 SQLite 和 File 后端行为一致"""

    async def test_user_crud_consistent(self, sqlite_backend, file_backend):
        """两种后端的 User CRUD 返回结构一致"""
        for backend in [sqlite_backend, file_backend]:
            u = await backend.create_user("consistency_test", "gpt-4o")
            assert u["username"] == "consistency_test"
            assert u["default_model"] == "gpt-4o"
            assert "id" in u
            assert "created_at" in u
            # 清理
            await backend.delete_user(u["id"])

    async def test_session_crud_consistent(self, sqlite_backend, file_backend):
        """两种后端的 Session CRUD 返回结构一致"""
        for backend in [sqlite_backend, file_backend]:
            u = await backend.create_user("sess_consistency")
            s = await backend.create_session(u["id"], "测试", "gpt-4o")
            assert s["title"] == "测试"
            assert s["user_id"] == u["id"]
            assert s["model_name"] == "gpt-4o"
            await backend.delete_user(u["id"])

    async def test_message_roundtrip(self, sqlite_backend, file_backend):
        """消息写入后能正确读取"""
        for backend in [sqlite_backend, file_backend]:
            u = await backend.create_user("msg_roundtrip")
            s = await backend.create_session(u["id"])
            await backend.add_message(s["id"], "human", "你好", 10, 0)
            await backend.add_message(s["id"], "ai", "你好！", 5, 3)
            msgs = await backend.list_messages_by_session(s["id"])
            assert len(msgs) == 2
            assert msgs[0]["content"] == "你好"
            assert msgs[1]["content"] == "你好！"
            await backend.delete_user(u["id"])
