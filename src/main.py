"""
程序总入口模块。

职责：
- 初始化配置管理器（加载 .env + config.yaml + logging.yaml + presets.yaml）
- 初始化存储后端（通过 StorageFactory 创建）
- 启动 TUI 主应用（菜单路由 + 用户管理 + 交互界面）

启动方式：
    uv run python src/main.py         # 默认 dev 环境
    APP_ENV=prod uv run python src/main.py  # 生产环境

当前实现状态（Step 4）：
- 配置管理：已实现
- 存储后端：SQLite（已实现）
- 用户管理：已实现（创建/切换/删除/列表）
- 会话管理：Step 7-8
- 对话引擎：Step 6-7
"""

import asyncio
import sys
from pathlib import Path

# 将项目根目录加入 Python 搜索路径
# 这使得 from src.xxx 和 from xxx（相对于 src/）两种导入方式都能正常工作
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# 在 Windows 环境下强制使用 UTF-8 编码输出
# 避免 emoji 等 Unicode 字符触发 GBK 编码错误
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")


async def _main_async() -> None:
    """异步主流程：初始化配置 → 创建存储 → 启动 TUI 主循环。"""
    from core.config_manager import ConfigManager
    from storage.factory import StorageFactory
    from ui.tui.app import TUIApp

    print("\n  ⏳ 正在加载配置...", end="", flush=True)

    try:
        # Step 2: 初始化配置管理器
        config = ConfigManager()

        # 验证必要的配置
        if not config.api_key:
            print("\r  ⚠  未检测到 API Key                          ")
            print(f"     请在 .env 文件中设置 API_KEY")
            print(f"     参考 .env.example 文件进行配置")
            print(f"     API Key 将在 Step 6 对话引擎中用到")
            print()

        print("\r  ✓ 配置加载完成                              ")
        print(f"     环境: {config.env}")
        print(f"     模型: {config.model_name}")
        print(f"     存储: {config.storage_type}")
        print(f"     API : {config.api_base_url}")
        print()

        # Step 4: 初始化存储后端
        print("  ⏳ 正在初始化存储后端...", end="", flush=True)
        try:
            storage = await StorageFactory.create(config)
            print(f"\r  ✓ 存储后端就绪 ({config.storage_type})                    ")
        except Exception as e:
            print(f"\r  ✗ 存储后端初始化失败: {e}                        ")
            print("    请运行: uv run python scripts/init_db.py")
            raise

        # 创建并启动 TUI 应用
        app = TUIApp(config_manager=config, storage=storage)
        await app.run()

    except FileNotFoundError as e:
        print(f"\n  ✗ 配置文件缺失: {e}")
        print("    请确保项目根目录下存在 .env 和 config.yaml 文件")
    except Exception as e:
        print(f"\n  ✗ 启动失败: {e}")
        raise


def main() -> None:
    """程序主入口函数。

    使用 asyncio.run() 启动异步主流程。
    asyncio.run() 会创建事件循环、运行协程、清理资源。
    """
    try:
        asyncio.run(_main_async())
    except KeyboardInterrupt:
        print("\n  用户中断")
    except Exception as e:
        print(f"\n  程序异常退出: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
