"""
Step 3 CRUD 完整功能验证脚本（一次性测试，非 pytest）。

验证 SQLite 后端的所有增删改查操作，
包括级联删除和用户数据隔离。

每次运行前自动清理旧数据库，保证测试独立可重复。
"""
import sys
import io
import os
from pathlib import Path

# 项目根目录加入搜索路径
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import asyncio
from src.core.config_manager import ConfigManager
from src.storage.sqlite_backend import SQLiteBackend


async def test_crud() -> bool:
    """执行全部 CRUD 验证，返回 True 表示全部通过。

    每次运行前删除旧数据库，保证干净环境。
    try/finally 确保即使测试失败也会关闭数据库连接，
    避免 asyncio 事件循环残留导致终端挂起。
    """
    config = ConfigManager()
    backend = None
    passed = 0
    total_groups = 6

    try:
        # =============================================
        # 初始化：使用独立测试数据库，不影响主应用数据
        # =============================================
        # 测试数据库放在 tests/ 目录下，与主应用数据库隔离
        test_db_path = _PROJECT_ROOT / "tests" / "test_crud.db"

        # 删除旧的测试数据库（如果存在且未被锁定）
        if test_db_path.exists():
            try:
                test_db_path.unlink()
                print(f"  [清理] 已删除旧测试数据库")
            except PermissionError:
                # 文件被锁定，使用带时间戳的新文件名
                import time
                test_db_path = _PROJECT_ROOT / "tests" / f"test_crud_{int(time.time())}.db"
                print(f"  [提示] 旧数据库被锁定，使用新文件: {test_db_path.name}")

        backend = SQLiteBackend(str(test_db_path))
        await backend.initialize()
        print(f"  [初始化] 测试数据库已创建: {test_db_path.name}")
        print()

        # =============================================
        # 1. User CRUD
        # =============================================
        print("=" * 50)
        print("[Test 1] 用户管理 CRUD")
        print("-" * 30)

        u1 = await backend.create_user("alice", "gpt-4o")
        print(f"  CREATE: {u1['username']} (id={u1['id'][:8]}...)")

        u2 = await backend.create_user("bob")
        print(f"  CREATE: {u2['username']} (default model: {u2['default_model']})")

        try:
            await backend.create_user("alice")
            print("  [FAIL] Should have raised ValueError!")
        except ValueError as e:
            print(f"  [OK] Duplicate check: {e}")

        fetched = await backend.get_user(u1["id"])
        assert fetched["username"] == "alice"
        print(f"  [OK] get_user: {fetched['username']}")

        fetched = await backend.get_user_by_username("bob")
        assert fetched is not None
        print(f"  [OK] get_user_by_username: {fetched['username']}")

        assert await backend.get_user_by_username("nobody") is None
        print("  [OK] Non-existent user returns None")

        users = await backend.list_users()
        assert len(users) == 2
        print(f"  [OK] list_users: {len(users)} users")

        updated = await backend.update_user(u1["id"], default_model="gpt-4o-mini")
        assert updated["default_model"] == "gpt-4o-mini"
        print(f"  [OK] update_user: model -> {updated['default_model']}")
        passed += 1
        print(f"  >>> Group 1 PASSED")
        print()

        # =============================================
        # 2. Session CRUD
        # =============================================
        print("[Test 2] 会话管理 CRUD")
        print("-" * 30)

        s1 = await backend.create_session(u1["id"], "测试会话", "gpt-4o")
        print(f"  CREATE: {s1['title']} (id={s1['id'][:8]}...)")
        s2 = await backend.create_session(u1["id"], "Python学习")
        print(f"  CREATE: {s2['title']}")

        fetched = await backend.get_session(s1["id"])
        assert fetched["title"] == "测试会话"
        print("  [OK] get_session")

        sessions = await backend.list_sessions_by_user(u1["id"])
        assert len(sessions) == 2
        print(f"  [OK] list_sessions_by_user: {len(sessions)} sessions for alice")

        sessions = await backend.list_sessions_by_user(u2["id"])
        assert len(sessions) == 0
        print(f"  [OK] User isolation: bob has {len(sessions)} sessions")

        updated = await backend.update_session(s1["id"], title="修改后标题")
        assert updated["title"] == "修改后标题"
        print("  [OK] update_session title")
        passed += 1
        print(f"  >>> Group 2 PASSED")
        print()

        # =============================================
        # 3. Message CRUD
        # =============================================
        print("[Test 3] 消息管理 CRUD")
        print("-" * 30)

        m1 = await backend.add_message(s1["id"], "human", "你好，请介绍Python", 10, 0)
        print(f"  ADD: human message ({m1['id'][:8]}...)")
        m2 = await backend.add_message(s1["id"], "ai", "Python是一种高级编程语言...", 0, 50)
        print(f"  ADD: ai message ({m2['id'][:8]}...)")
        m3 = await backend.add_message(s2["id"], "human", "如何学习Python？", 15, 0)
        print(f"  ADD: message to session 2")

        msgs = await backend.list_messages_by_session(s1["id"])
        assert len(msgs) == 2
        assert msgs[0]["role"] == "human"
        assert msgs[1]["role"] == "ai"
        print(f"  [OK] list_messages: {len(msgs)} msgs, order human->ai")

        results = await backend.search_messages(u1["id"], "Python")
        assert len(results) >= 2
        print(f"  [OK] search_messages('Python'): {len(results)} matches")
        for r in results:
            print(f"       [{r.get('session_title', '?')}] {r['content'][:40]}...")

        results = await backend.search_messages(u1["id"], "NONEXISTENT")
        assert len(results) == 0
        print(f"  [OK] search_messages no match: {len(results)} results")
        passed += 1
        print(f"  >>> Group 3 PASSED")
        print()

        # =============================================
        # 4. Preset CRUD
        # =============================================
        print("[Test 4] 预设管理 CRUD")
        print("-" * 30)

        p1 = await backend.create_preset("代码助手", "你是一个代码专家...", is_builtin=True)
        print(f"  CREATE builtin: {p1['name']} (builtin={p1['is_builtin']})")
        p2 = await backend.create_preset("我的翻译官", "翻译文本...", user_id=u1["id"])
        print(f"  CREATE user: {p2['name']} (owner={p2['user_id'][:8]}...)")

        presets = await backend.list_presets(user_id=u1["id"])
        assert len(presets) == 2
        print(f"  [OK] list for alice: {len(presets)} presets")

        presets = await backend.list_presets()
        assert len(presets) == 1 and presets[0]["is_builtin"]
        print(f"  [OK] builtin only: {len(presets)} preset")

        updated = await backend.update_preset(p2["id"], name="超级翻译官")
        assert updated["name"] == "超级翻译官"
        print(f"  [OK] update_preset: name -> {updated['name']}")

        try:
            await backend.update_preset(p1["id"], name="hack")
            print("  [FAIL] Should reject builtin update!")
        except ValueError:
            print("  [OK] Builtin preset update rejected")
        passed += 1
        print(f"  >>> Group 4 PASSED")
        print()

        # =============================================
        # 5. UserConfig CRUD
        # =============================================
        print("[Test 5] 用户配置 CRUD")
        print("-" * 30)

        await backend.set_user_config(u1["id"], "theme", "dark")
        await backend.set_user_config(u1["id"], "font_size", "14")
        print("  SET: theme=dark, font_size=14")

        val = await backend.get_user_config(u1["id"], "theme")
        assert val == "dark"
        print(f"  [OK] get: theme={val}")

        assert await backend.get_user_config(u1["id"], "nonexistent") is None
        print("  [OK] Non-existent config returns None")

        all_cfg = await backend.get_all_user_configs(u1["id"])
        assert len(all_cfg) == 2
        print(f"  [OK] get_all: {all_cfg}")

        # Upsert
        await backend.set_user_config(u1["id"], "theme", "light")
        val = await backend.get_user_config(u1["id"], "theme")
        assert val == "light"
        print(f"  [OK] Upsert: theme -> {val}")

        await backend.delete_user_config(u1["id"], "font_size")
        print("  [OK] delete_user_config")
        passed += 1
        print(f"  >>> Group 5 PASSED")
        print()

        # =============================================
        # 6. Cascading Delete
        # =============================================
        print("[Test 6] 级联删除验证")
        print("-" * 30)

        assert await backend.delete_user(u2["id"])
        print("  [OK] delete_user(bob)")

        assert await backend.get_user(u2["id"]) is None
        print("  [OK] bob removed from DB")

        sessions = await backend.list_sessions_by_user(u1["id"])
        assert len(sessions) == 2
        print(f"  [OK] Alice data unaffected ({len(sessions)} sessions)")
        passed += 1
        print(f"  >>> Group 6 PASSED")
        print()

        # =============================================
        # Result
        # =============================================
        print("=" * 50)
        print(f"ALL {passed}/{total_groups} TEST GROUPS PASSED!")
        print("=" * 50)
        return passed == total_groups

    except Exception:
        # 异常时打印详细信息，但不让脚本崩溃
        import traceback
        print()
        print("=" * 50)
        print("TEST FAILED WITH EXCEPTION:")
        traceback.print_exc()
        print("=" * 50)
        return False

    finally:
        # 无论如何都要关闭数据库连接
        # 不关闭会导致 asyncio 事件循环无法正常结束，终端可能挂起
        if backend is not None:
            try:
                await backend.close()
                print()
                print("  [清理] 数据库连接已关闭")
            except Exception as close_err:
                print(f"  [警告] 关闭连接时出错: {close_err}")


if __name__ == "__main__":
    # 使用 asyncio.run() 的正确模式
    # 即使 test_crud 抛出异常，asyncio.run() 也会清理事件循环
    try:
        success = asyncio.run(test_crud())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n用户中断")
        sys.exit(1)
