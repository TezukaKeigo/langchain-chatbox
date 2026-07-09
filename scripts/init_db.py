"""
数据库初始化脚本。

用于首次创建数据库和所有数据表，可在任何时候重复执行（幂等）。

使用方式：
    uv run python scripts/init_db.py

执行效果：
    1. 自动创建 data/sqlite/ 目录（如不存在）
    2. 创建 app.db 数据库文件（如不存在）
    3. 按外键依赖顺序创建 5 张数据表（如不存在）
    4. 打印每张表的创建状态
    5. 输出数据库文件位置

注意：
    - 此脚本是幂等的 — 重复执行不会损坏已有数据
    - 使用了 CREATE TABLE IF NOT EXISTS 语法
    - 数据库文件路径从 config.yaml 中读取
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
    print(f"        存储类型: {config.storage_type}")
    print(f"        数据库路径: {config.sqlite_path}")
    print()

    # 2. 确定数据库文件位置
    db_path = Path(config.sqlite_path)
    if not db_path.is_absolute():
        db_path = _PROJECT_ROOT / db_path

    # 3. 创建并初始化存储后端
    print("  [2/3] 创建数据库表...")
    try:
        storage = await StorageFactory.create(config)
    except NotImplementedError as e:
        print(f"    ✗ 错误: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"    ✗ 初始化失败: {e}")
        sys.exit(1)

    print(f"    ✓ 数据库已连接: {db_path}")
    print()

    # 4. 验证表结构
    print("  [3/3] 验证表结构...")

    import aiosqlite
    async with aiosqlite.connect(str(db_path)) as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = await cursor.fetchall()
        table_names = [row[0] for row in tables]

    expected_tables = ["users", "sessions", "messages", "presets", "user_configs"]
    for table in expected_tables:
        if table in table_names:
            # 查询每个表的列信息
            async with aiosqlite.connect(str(db_path)) as db:
                cursor = await db.execute(f"PRAGMA table_info({table})")
                columns = await cursor.fetchall()
                col_names = [col[1] for col in columns]
            print(f"    ✓ {table} ({len(columns)} 列: {', '.join(col_names[:5])}{'...' if len(columns) > 5 else ''})")
        else:
            print(f"    ✗ {table} — 未找到!")

    print()
    print("  " + "─" * 32)
    print(f"  ✓ 数据库初始化完成！")
    print(f"    文件: {db_path.absolute()}")
    print(f"    表数: {len(table_names)}")
    print()

    await storage.close()


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
