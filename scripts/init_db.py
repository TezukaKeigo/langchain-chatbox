"""
数据库初始化脚本。

用于首次创建数据库和所有数据表，可在任何时候重复执行（幂等）。

支持 SQLite 和 MySQL 两种后端，根据 config.yaml 中的 storage.type 自动选择。

使用方式：
    uv run python scripts/init_db.py

执行效果：
    SQLite:
        1. 自动创建 data/sqlite/ 目录（如不存在）
        2. 创建 app.db 数据库文件（如不存在）
        3. 按外键依赖顺序创建 5 张数据表（如不存在）
        4. 打印每张表的创建状态
        5. 输出数据库文件位置

    MySQL:
        1. 创建数据库（如不存在）
        2. 按外键依赖顺序创建 5 张数据表（如不存在）
        3. 打印每张表的创建状态

注意：
    - 此脚本是幂等的 — 重复执行不会损坏已有数据
    - 使用了 CREATE TABLE IF NOT EXISTS 语法
"""

import asyncio
import sys
from pathlib import Path

# Windows 环境下强制 UTF-8 输出，避免 GBK 编码错误
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# 将项目根目录加入 Python 搜索路径
# 脚本位于 scripts/ 子目录中，需要能导入 src/ 下的模块
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# 期望的 5 张数据表
_EXPECTED_TABLES = ["users", "sessions", "messages", "presets", "user_configs"]


async def _init_database() -> None:
    """异步初始化数据库的主流程。"""
    from src.core.config_manager import ConfigManager
    from src.storage.factory import StorageFactory

    print()
    print("  LangChain Chat — 数据库初始化")
    print("  " + "─" * 32)
    print()

    # 1. 加载配置
    print("  [1/3] 加载配置...")
    config = ConfigManager()
    storage_type = config.storage_type

    print(f"        存储类型: {storage_type}")
    if storage_type == "sqlite":
        db_path = Path(config.sqlite_path)
        if not db_path.is_absolute():
            db_path = _PROJECT_ROOT / db_path
        print(f"        数据库路径: {db_path}")
    elif storage_type == "mysql":
        mysql_cfg = config.mysql_config
        print(f"        MySQL 主机: {mysql_cfg['host']}:{mysql_cfg['port']}")
        print(f"        MySQL 数据库: {mysql_cfg['database']}")
        print(f"        MySQL 用户: {mysql_cfg['user']}")
    print()

    # 2. 创建并初始化存储后端
    print("  [2/3] 创建数据库表...")
    try:
        storage = await StorageFactory.create(config)
    except NotImplementedError as e:
        print(f"    ✗ 错误: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"    ✗ 初始化失败: {e}")
        sys.exit(1)

    if storage_type == "sqlite":
        print(f"    ✓ SQLite 数据库已就绪: {db_path}")
    elif storage_type == "mysql":
        print(f"    ✓ MySQL 数据库已就绪: {mysql_cfg['host']}:{mysql_cfg['port']}/{mysql_cfg['database']}")
    print()

    # 3. 验证表结构
    print("  [3/3] 验证表结构...")
    table_names = await _verify_tables(storage, storage_type)

    print()
    print("  " + "─" * 32)
    print(f"  ✓ 数据库初始化完成！")
    if storage_type == "sqlite":
        print(f"    文件: {db_path.absolute()}")
    elif storage_type == "mysql":
        print(f"    数据库: {mysql_cfg['database']}@{mysql_cfg['host']}")
    print(f"    表数: {len(table_names)}")
    print()

    await storage.close()


async def _verify_tables(storage, storage_type: str) -> list:
    """验证所有必需的表是否存在，并打印列信息。

    Args:
        storage: 已初始化的存储后端实例
        storage_type: 存储类型（sqlite / mysql）

    Returns:
        已存在的表名列表
    """
    table_names = []

    for table in _EXPECTED_TABLES:
        columns = None

        if storage_type == "sqlite":
            # SQLite: 使用 PRAGMA table_info
            import aiosqlite
            db_path = storage._db_path
            async with aiosqlite.connect(str(db_path)) as db:
                # 先检查表是否存在
                cursor = await db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
                    (table,),
                )
                row = await cursor.fetchone()
                if row is None:
                    print(f"    ✗ {table} — 未找到!")
                    continue
                table_names.append(table)
                # 获取列信息
                cursor = await db.execute(f"PRAGMA table_info({table})")
                columns = await cursor.fetchall()
                col_names = [col[1] for col in columns]

        elif storage_type == "mysql":
            # MySQL: 使用 SHOW COLUMNS
            pool = storage._pool
            if pool is None:
                continue
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    try:
                        await cur.execute(f"SHOW COLUMNS FROM `{table}`")
                        columns = await cur.fetchall()
                        table_names.append(table)
                        col_names = [col[0] for col in columns]
                    except Exception:
                        print(f"    ✗ {table} — 未找到!")
                        continue

        if columns:
            col_display = ', '.join(col_names[:5])
            if len(col_names) > 5:
                col_display += '...'
            print(f"    ✓ {table} ({len(columns)} 列: {col_display})")

    return table_names


def main() -> None:
    """脚本入口。"""
    try:
        asyncio.run(_init_database())
    except KeyboardInterrupt:
        print("\n  用户中断")
        sys.exit(0)
    except Exception as e:
        print(f"\n  初始化失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
