"""
用户管理器单元测试 — 覆盖 UserManager 全部业务逻辑。

测试策略：
- 使用 SQLite 后端（轻量、快速）
- 每个测试独立创建/清理用户数据
- 覆盖：创建/列表/获取/删除 + 校验规则 + 当前用户状态管理
"""

import pytest
from src.core.user_manager import UserManager


class TestUserCreation:
    """用户创建与校验"""

    async def test_create_user_basic(self, sqlite_backend, state):
        um = UserManager(sqlite_backend, state)
        user = await um.create_user("alice", default_model="gpt-4o")
        assert user["username"] == "alice"
        assert user["default_model"] == "gpt-4o"
        assert "id" in user

    async def test_create_user_default_model(self, sqlite_backend, state):
        um = UserManager(sqlite_backend, state)
        user = await um.create_user("bob")
        assert user["default_model"] == "gpt-4o-mini"

    async def test_create_user_strips_whitespace(self, sqlite_backend, state):
        um = UserManager(sqlite_backend, state)
        user = await um.create_user("  charlie  ")
        assert user["username"] == "charlie"

    async def test_create_user_empty_username(self, sqlite_backend, state):
        um = UserManager(sqlite_backend, state)
        with pytest.raises(ValueError, match="不能为空"):
            await um.create_user("")

    async def test_create_user_whitespace_only(self, sqlite_backend, state):
        um = UserManager(sqlite_backend, state)
        with pytest.raises(ValueError, match="不能为空"):
            await um.create_user("   ")

    async def test_create_user_too_long(self, sqlite_backend, state):
        um = UserManager(sqlite_backend, state)
        long_name = "a" * 51
        with pytest.raises(ValueError, match="50"):
            await um.create_user(long_name)

    async def test_create_user_max_length(self, sqlite_backend, state):
        """50 字符用户名应允许"""
        um = UserManager(sqlite_backend, state)
        name = "a" * 50
        user = await um.create_user(name)
        assert user["username"] == name

    async def test_create_duplicate_username(self, sqlite_backend, state):
        um = UserManager(sqlite_backend, state)
        await um.create_user("alice")
        with pytest.raises(ValueError, match="已存在"):
            await um.create_user("alice")

    async def test_create_duplicate_case_sensitive(self, sqlite_backend, state):
        """用户名大小写敏感"""
        um = UserManager(sqlite_backend, state)
        await um.create_user("Alice")
        # "alice" 不同于 "Alice"
        user = await um.create_user("alice")
        assert user["username"] == "alice"


class TestUserQuery:
    """用户查询"""

    async def test_list_users(self, sqlite_backend, state):
        um = UserManager(sqlite_backend, state)
        await um.create_user("u1")
        await um.create_user("u2")
        users = await um.list_users()
        assert len(users) == 2

    async def test_list_users_empty(self, sqlite_backend, state):
        um = UserManager(sqlite_backend, state)
        users = await um.list_users()
        assert users == []

    async def test_get_user(self, sqlite_backend, state):
        um = UserManager(sqlite_backend, state)
        created = await um.create_user("dave")
        fetched = await um.get_user(created["id"])
        assert fetched["username"] == "dave"

    async def test_get_nonexistent_user(self, sqlite_backend, state):
        um = UserManager(sqlite_backend, state)
        assert await um.get_user("nonexistent-id") is None


class TestUserDeletion:
    """用户删除"""

    async def test_delete_user(self, sqlite_backend, state):
        um = UserManager(sqlite_backend, state)
        user = await um.create_user("frank")
        assert await um.delete_user(user["id"]) is True
        assert await um.get_user(user["id"]) is None

    async def test_delete_nonexistent_user(self, sqlite_backend, state):
        um = UserManager(sqlite_backend, state)
        assert await um.delete_user("nonexistent") is False

    async def test_delete_current_user_clears_state(self, sqlite_backend, state):
        """删除当前活跃用户后，自动清除状态"""
        um = UserManager(sqlite_backend, state)
        user = await um.create_user("temp_user")
        um.set_current_user(user)
        assert state["current_user_id"] == user["id"]

        await um.delete_user(user["id"])
        assert state["current_user_id"] is None
        assert state["current_username"] is None

    async def test_delete_other_user_preserves_state(self, sqlite_backend, state):
        """删除非活跃用户不影响当前状态"""
        um = UserManager(sqlite_backend, state)
        active = await um.create_user("active_user")
        other = await um.create_user("other_user")
        um.set_current_user(active)

        await um.delete_user(other["id"])
        # 当前用户状态应保持不变
        assert state["current_user_id"] == active["id"]
        assert state["current_username"] == "active_user"


class TestCurrentUserState:
    """当前用户状态管理"""

    async def test_set_current_user(self, sqlite_backend, state):
        um = UserManager(sqlite_backend, state)
        user = await um.create_user("current", default_model="kimi 2.6")
        um.set_current_user(user)

        assert state["current_user_id"] == user["id"]
        assert state["current_username"] == "current"
        assert state["current_model"] == "kimi 2.6"
        # 切换用户后清除旧会话上下文
        assert state["current_session_id"] is None
        assert state["current_session_title"] is None
        assert state["current_preset_id"] is None
        assert state["current_preset_name"] is None

    async def test_set_current_user_default_model(self, sqlite_backend, state):
        """用户无 default_model 时回退到 deepseek-v4-flash"""
        um = UserManager(sqlite_backend, state)
        user = await um.create_user("no_model")
        # 手动移除 default_model 模拟边缘情况
        user_no_model = {k: v for k, v in user.items() if k != "default_model"}
        um.set_current_user(user_no_model)
        assert state["current_model"] == "deepseek-v4-flash"

    async def test_clear_current_user(self, sqlite_backend, state):
        um = UserManager(sqlite_backend, state)
        user = await um.create_user("clear_test")
        um.set_current_user(user)
        um.clear_current_user()

        assert state["current_user_id"] is None
        assert state["current_username"] is None
        assert state["current_model"] is None
        assert state["current_session_id"] is None

    async def test_get_current_user_id(self, sqlite_backend, state):
        um = UserManager(sqlite_backend, state)
        assert um.get_current_user_id() is None
        user = await um.create_user("id_test")
        um.set_current_user(user)
        assert um.get_current_user_id() == user["id"]

    async def test_get_current_username(self, sqlite_backend, state):
        um = UserManager(sqlite_backend, state)
        assert um.get_current_username() is None
        user = await um.create_user("name_test")
        um.set_current_user(user)
        assert um.get_current_username() == "name_test"

    async def test_is_user_selected(self, sqlite_backend, state):
        um = UserManager(sqlite_backend, state)
        assert um.is_user_selected is False
        user = await um.create_user("selected")
        um.set_current_user(user)
        assert um.is_user_selected is True

    async def test_switch_user_clears_session(self, sqlite_backend, state):
        """切换用户时应清除旧会话上下文"""
        um = UserManager(sqlite_backend, state)
        u1 = await um.create_user("user_one")
        u2 = await um.create_user("user_two")

        um.set_current_user(u1)
        # 模拟有活跃会话
        state["current_session_id"] = "some-session"
        state["current_session_title"] = "Some Title"
        state["current_preset_id"] = "some-preset"

        # 切换到 u2
        um.set_current_user(u2)
        assert state["current_user_id"] == u2["id"]
        assert state["current_session_id"] is None
        assert state["current_preset_id"] is None
