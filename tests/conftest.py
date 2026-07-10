"""
pytest 共享 fixtures — 为所有测试模块提供可复用的测试环境。

提供的 fixtures：
- temp_dir: 临时目录（测试结束后自动清理）
- config_manager: ConfigManager 实例
- state: 应用全局状态字典
- sqlite_backend: 已初始化的 SQLite 后端（独立临时数据库）
- file_backend: 已初始化的 File 后端（独立临时目录）
- test_user: 在 SQLite 后端中预创建的测试用户
"""

import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest

# 确保项目根目录在 sys.path 中
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ============================================================
# 基础 fixtures
# ============================================================

@pytest.fixture
def temp_dir():
    """创建临时目录，测试结束后自动清理。"""
    with tempfile.TemporaryDirectory(prefix="lc_test_") as tmp:
        yield tmp


@pytest.fixture
def config_manager():
    """创建 ConfigManager 实例（使用项目真实配置）。"""
    from src.core.config_manager import ConfigManager
    return ConfigManager()


@pytest.fixture
def state(config_manager) -> Dict[str, Any]:
    """创建应用全局状态字典。"""
    return {
        "current_user_id": None,
        "current_username": None,
        "current_session_id": None,
        "current_session_title": None,
        "current_model": config_manager.model_name,
        "current_preset_id": None,
        "current_preset_name": None,
        "config": config_manager,
    }


# ============================================================
# SQLite backend fixtures
# ============================================================

@pytest.fixture
async def sqlite_backend(temp_dir):
    """创建已初始化的 SQLite 后端（使用独立临时数据库）。

    测试结束后自动关闭连接。
    """
    from src.storage.sqlite_backend import SQLiteBackend

    db_path = os.path.join(temp_dir, "test.db")
    backend = SQLiteBackend(db_path)
    await backend.initialize()
    yield backend
    try:
        await backend.close()
    except Exception:
        pass


@pytest.fixture
async def test_user(sqlite_backend):
    """在 SQLite 后端中预创建一个测试用户。"""
    return await sqlite_backend.create_user("_pytest_user", default_model="deepseek-v4-flash")


# ============================================================
# File backend fixtures
# ============================================================

@pytest.fixture
async def file_backend(temp_dir):
    """创建已初始化的 File 后端（使用独立临时目录）。

    测试结束后自动关闭。
    """
    from src.storage.file_backend import FileBackend

    root = os.path.join(temp_dir, "file_storage")
    backend = FileBackend(root_path=root, fmt="json")
    await backend.initialize()
    yield backend
    try:
        await backend.close()
    except Exception:
        pass
