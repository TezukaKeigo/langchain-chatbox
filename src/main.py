"""
程序总入口模块。

职责：
- 初始化日志系统（加载 config/logging.yaml）
- 初始化配置管理器（加载 .env + config.yaml + presets.yaml）
- 初始化存储后端（通过 StorageFactory 创建）
- 启动 TUI 主应用（菜单路由 + 用户管理 + 交互界面）

启动方式：
    uv run python src/main.py         # 默认 dev 环境
    APP_ENV=prod uv run python src/main.py  # 生产环境

当前实现状态（Step 12）：
- 配置管理：已实现
- 存储后端：SQLite / MySQL / File（三种后端均已实现）
- 日志系统：已实现（JSON 格式文件日志 + 控制台输出）
- 用户管理 / 会话管理 / 对话引擎：已实现
"""

import asyncio
import logging
import logging.config
import os as _os
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


def _setup_logging() -> None:
    """初始化日志系统。

    从 config/logging.yaml 读取日志配置，
    通过 logging.config.dictConfig 注入 Python logging 模块。
    同时确保 logs/ 目录存在（避免 RotatingFileHandler 创建失败）。
    """
    import yaml

    logging_yaml = _PROJECT_ROOT / "config" / "logging.yaml"
    if not logging_yaml.exists():
        # 没有日志配置文件时使用默认控制台输出
        logging.basicConfig(
            level=logging.INFO,
            format="[%(asctime)s] [%(levelname)-8s] %(name)s — %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            stream=sys.stdout,
        )
        logging.getLogger("langchain_chat").warning(
            "日志配置文件 %s 不存在，使用默认控制台输出", logging_yaml
        )
        return

    # 确保 logs/ 目录存在
    logs_dir = _PROJECT_ROOT / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    with open(logging_yaml, "r", encoding="utf-8") as f:
        config_dict = yaml.safe_load(f)

    # 将日志文件路径修正为绝对路径（dictConfig 的 filename 默认相对于 CWD）
    if config_dict and "handlers" in config_dict:
        for handler_cfg in config_dict["handlers"].values():
            if "filename" in handler_cfg:
                filename = handler_cfg["filename"]
                if not Path(filename).is_absolute():
                    handler_cfg["filename"] = str(_PROJECT_ROOT / filename)

    logging.config.dictConfig(config_dict)


async def _main_async() -> None:
    """异步主流程：初始化配置 → 创建存储 → 启动 TUI 主循环。"""
    from core.config_manager import ConfigManager
    from storage.factory import StorageFactory
    from ui.tui.app import TUIApp

    logger = logging.getLogger("langchain_chat")

    print("\n  ⏳ 正在加载配置...", end="", flush=True)

    try:
        # Step 2: 初始化配置管理器
        config = ConfigManager()
        logger.info(
            "配置加载完成 — 环境=%s, 模型=%s, 存储=%s",
            config.env, config.model_name, config.storage_type,
        )

        # 验证必要的配置
        if not config.api_key:
            logger.warning("API Key 未配置")
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

        # Step 12: 初始化存储后端
        print("  ⏳ 正在初始化存储后端...", end="", flush=True)
        try:
            storage = await StorageFactory.create(config)
            logger.info("存储后端初始化成功 — 类型=%s", config.storage_type)
            print(f"\r  ✓ 存储后端就绪 ({config.storage_type})                    ")
        except Exception as e:
            logger.error("存储后端初始化失败 — %s", e, exc_info=True)
            print(f"\r  ✗ 存储后端初始化失败: {e}                        ")
            print("    请运行: uv run python scripts/init_db.py")
            raise

        # 创建并启动 TUI 应用
        app = TUIApp(config_manager=config, storage=storage)
        await app.run()

    except FileNotFoundError as e:
        logger.error("配置文件缺失 — %s", e)
        print(f"\n  ✗ 配置文件缺失: {e}")
        print("    请确保项目根目录下存在 .env 和 config.yaml 文件")
    except Exception as e:
        logger.critical("程序启动失败 — %s", e, exc_info=True)
        print(f"\n  ✗ 启动失败: {e}")
        raise


def main() -> None:
    """程序主入口函数。

    使用 asyncio.run() 启动异步主流程。
    asyncio.run() 会创建事件循环、运行协程、清理资源。
    """
    # Step 12: 启动时初始化日志系统
    _setup_logging()
    logger = logging.getLogger("langchain_chat")
    logger.info("=" * 60)
    logger.info("LangChain Chat 启动")
    logger.info("=" * 60)

    try:
        asyncio.run(_main_async())
    except KeyboardInterrupt:
        logger.info("用户中断，程序退出")
        print("\n  用户中断")
    except Exception as e:
        logger.critical("程序异常退出 — %s", e, exc_info=True)
        print(f"\n  程序异常退出: {e}")
        sys.exit(1)
    finally:
        logger.info("LangChain Chat 退出")


if __name__ == "__main__":
    main()
