"""
存储工厂 — 根据配置创建并初始化存储后端实例。

设计模式：工厂模式（Factory Pattern）

职责：
1. 读取配置中的 storage.type 字段
2. 实例化对应的存储后端（SQLiteBackend / MySQLBackend / FileBackend）
3. 调用后端的 initialize() 方法完成数据库初始化
4. 返回就绪的后端实例

扩展方式（开闭原则）：
  新增后端只需：
  1. 创建新类继承 StorageBackend
  2. 在本文件的 _BACKEND_MAP 中注册
  3. 无需修改任何业务代码

使用方式：
    config = ConfigManager()
    storage = await StorageFactory.create(config)
    # storage 已初始化，可直接使用
    await storage.close()
"""

from typing import TYPE_CHECKING

from .base import StorageBackend

if TYPE_CHECKING:
    from src.core.config_manager import ConfigManager


class StorageFactory:
    """存储后端工厂。

    根据全局配置创建对应的存储后端实例。

    所有方法均为静态方法 — 工厂本身不需要维护状态。
    """

    # 当前已实现的后端类型
    _SUPPORTED_BACKENDS = {"sqlite", "mysql", "file"}

    @staticmethod
    async def create(config: "ConfigManager") -> StorageBackend:
        """创建并初始化存储后端。

        根据 config.storage_type 选择后端类型：
        - sqlite → SQLiteBackend（默认，Step 3 实现）
        - mysql  → MySQLBackend（Step 11 实现）
        - file   → FileBackend（Step 12 实现）

        Args:
            config: ConfigManager 实例，提供 storage_type 和相关配置

        Returns:
            已初始化的 StorageBackend 实例

        Raises:
            ValueError: 存储类型不支持
            RuntimeError: 初始化失败
        """
        storage_type = config.storage_type.lower()

        if storage_type not in StorageFactory._SUPPORTED_BACKENDS:
            raise ValueError(
                f"不支持的存储类型: '{storage_type}'，"
                f"可选值: {', '.join(StorageFactory._SUPPORTED_BACKENDS)}"
            )

        if storage_type == "sqlite":
            backend = await StorageFactory._create_sqlite(config)
        elif storage_type == "mysql":
            backend = await StorageFactory._create_mysql(config)
        elif storage_type == "file":
            backend = await StorageFactory._create_file(config)
        else:
            raise ValueError(f"存储类型 '{storage_type}' 暂未实现")

        return backend

    # ============================================================
    # 各后端创建方法
    # ============================================================

    @staticmethod
    async def _create_sqlite(config: "ConfigManager") -> StorageBackend:
        """创建 SQLite 后端。

        数据库文件路径从 config.sqlite_path 读取，
        默认值为 data/sqlite/app.db。
        """
        from .sqlite_backend import SQLiteBackend

        db_path = config.sqlite_path
        backend = SQLiteBackend(db_path=db_path)
        await backend.initialize()
        return backend

    @staticmethod
    async def _create_mysql(config: "ConfigManager") -> StorageBackend:
        """创建 MySQL 后端（Step 11 实现）。

        Args:
            config: 配置管理器

        Raises:
            NotImplementedError: 当前步骤尚未实现
        """
        raise NotImplementedError(
            "MySQL 后端将在 Step 11 中实现。"
            "当前请使用 SQLite 后端（config.yaml 中 storage.type = 'sqlite'）"
        )

    @staticmethod
    async def _create_file(config: "ConfigManager") -> StorageBackend:
        """创建 File 后端（Step 12 实现）。

        Args:
            config: 配置管理器

        Raises:
            NotImplementedError: 当前步骤尚未实现
        """
        raise NotImplementedError(
            "File 文件系统后端将在 Step 12 中实现。"
            "当前请使用 SQLite 后端（config.yaml 中 storage.type = 'sqlite'）"
        )
