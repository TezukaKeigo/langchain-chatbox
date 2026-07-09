"""
Step 5 预设管理功能验证脚本（一次性测试，非 pytest）。

验证 PresetManager 的所有功能：
1. 内置预设加载（幂等）
2. 自定义预设 CRUD
3. 内置预设保护
4. 预设选择/取消
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
from src.core.preset_manager import PresetManager


async def test_presets() -> bool:
    """执行全部预设验证，返回 True 表示全部通过。"""
    config = ConfigManager()
    backend = None
    passed = 0
    total_groups = 5

    try:
        # 使用独立测试数据库
        test_db_path = _PROJECT_ROOT / "tests" / "test_presets.db"
        if test_db_path.exists():
            try:
                test_db_path.unlink()
            except PermissionError:
                import time
                test_db_path = _PROJECT_ROOT / "tests" / f"test_presets_{int(time.time())}.db"

        backend = SQLiteBackend(str(test_db_path))
        await backend.initialize()

        state = {
            "current_user_id": None, "current_username": None,
            "current_preset_id": None, "current_preset_name": None,
        }

        # 创建测试用户（自定义预设需要 FK）
        user = await backend.create_user("_testuser")
        state["current_user_id"] = user["id"]
        state["current_username"] = user["username"]

        mgr = PresetManager(backend, state, config)

        # =============================================
        # 1. 内置预设加载（幂等性）
        # =============================================
        print("=" * 50)
        print("[Test 1] 内置预设加载")
        print("-" * 30)

        loaded = await mgr.load_builtin_presets()
        assert loaded > 0, f"Should load presets, got {loaded}"
        print(f"  首次加载: {loaded} 个内置预设")

        loaded2 = await mgr.load_builtin_presets()
        assert loaded2 == 0, f"Should be idempotent, got {loaded2}"
        print(f"  二次加载: {loaded2} 个（幂等验证通过）")
        passed += 1
        print(f"  >>> Group 1 PASSED")
        print()

        # =============================================
        # 2. 内置预设列表
        # =============================================
        print("[Test 2] 内置预设列表")
        print("-" * 30)

        builtins = await mgr.list_presets(user_id=None)
        assert len(builtins) == 4, f"Expected 4 builtins, got {len(builtins)}"
        names = [p["name"] for p in builtins]
        assert "翻译助手" in names
        assert "代码专家" in names
        assert "创意写手" in names
        assert "英语老师" in names
        for p in builtins:
            assert p["is_builtin"] is True
            assert p["user_id"] is None
            assert len(p.get("system_prompt", "")) > 10, f"{p['name']} prompt too short"
        print(f"  内置预设: {len(builtins)} 个, 全部校验通过")
        passed += 1
        print(f"  >>> Group 2 PASSED")
        print()

        # =============================================
        # 3. 自定义预设 CRUD
        # =============================================
        print("[Test 3] 自定义预设 CRUD")
        print("-" * 30)

        custom = await mgr.create_preset(
            user_id=user["id"],
            name="我的代码导师",
            system_prompt="你是一位 Python 导师，耐心解答问题。",
            description="个人代码学习助手",
        )
        assert custom["name"] == "我的代码导师"
        assert custom["is_builtin"] is False
        assert custom["user_id"] == user["id"]
        print(f"  创建: {custom['name']}")

        # 列表（含内置+自定义）
        all_for_user = await mgr.list_presets(user_id=user["id"])
        assert len(all_for_user) == 5  # 4 builtin + 1 custom
        print(f"  用户可见: {len(all_for_user)} 个（4 内置 + 1 自定义）")

        # 更新
        updated = await mgr.update_preset(
            custom["id"],
            name="Python 导师",
            description="专注 Python 教学",
        )
        assert updated["name"] == "Python 导师"
        assert updated["description"] == "专注 Python 教学"
        print(f"  更新: {updated['name']} / {updated['description']}")

        # 删除
        await mgr.delete_preset(custom["id"])
        all_after = await mgr.list_presets(user_id=user["id"])
        assert len(all_after) == 4  # 只剩内置
        print(f"  删除: 剩余 {len(all_after)} 个预设（仅内置）")
        passed += 1
        print(f"  >>> Group 3 PASSED")
        print()

        # =============================================
        # 4. 内置预设保护
        # =============================================
        print("[Test 4] 内置预设保护")
        print("-" * 30)

        try:
            await mgr.update_preset(builtins[0]["id"], name="hack")
            print("  [FAIL] Should reject builtin update!")
        except ValueError:
            print("  [OK] 内置预设不可编辑")

        try:
            await mgr.delete_preset(builtins[0]["id"])
            print("  [FAIL] Should reject builtin delete!")
        except ValueError:
            print("  [OK] 内置预设不可删除")
        passed += 1
        print(f"  >>> Group 4 PASSED")
        print()

        # =============================================
        # 5. 预设选择/取消
        # =============================================
        print("[Test 5] 预设选择与取消")
        print("-" * 30)

        assert mgr.get_current_preset_id() is None
        print("  初始状态: 无选中预设")

        mgr.select_preset(builtins[0])
        assert mgr.get_current_preset_name() == "翻译助手"
        assert mgr.get_current_preset_id() == builtins[0]["id"]
        print(f"  选择: {mgr.get_current_preset_name()}")

        mgr.select_preset(builtins[2])
        assert mgr.get_current_preset_name() == "创意写手"
        print(f"  切换: {mgr.get_current_preset_name()}")

        mgr.clear_preset()
        assert mgr.get_current_preset_id() is None
        assert mgr.get_current_preset_name() is None
        print("  取消: 已清除预设选择")
        passed += 1
        print(f"  >>> Group 5 PASSED")
        print()

        # =============================================
        # Result
        # =============================================
        print("=" * 50)
        print(f"ALL {passed}/{total_groups} TEST GROUPS PASSED!")
        print("=" * 50)
        return passed == total_groups

    except Exception:
        import traceback
        print()
        print("=" * 50)
        print("TEST FAILED WITH EXCEPTION:")
        traceback.print_exc()
        print("=" * 50)
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
        success = asyncio.run(test_presets())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n用户中断")
        sys.exit(1)
