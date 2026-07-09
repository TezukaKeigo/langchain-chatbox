"""
配置管理器 — 统一加载和管理所有项目配置。

职责：
1. 加载 .env 文件（敏感信息：API Key、数据库密码）
2. 加载 config.yaml（全局配置：LLM 设置、存储类型、会话选项）
3. 加载 config/logging.yaml（日志配置：格式、级别、输出路径）
4. 加载 config/presets.yaml（系统内置预设）

配置优先级（从高到低）：
  环境变量 > config.yaml 值 > 代码中的硬编码默认值

设计模式：
- 单例模式：全局唯一配置实例，避免重复加载
- 属性委托：通过 property 暴露常用配置项，无需记忆 yaml 路径

使用方式：
  config = ConfigManager()       # 自动加载所有配置
  api_key = config.api_key       # 直接属性访问
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field


# ============================================================
# 路径常量 — 所有配置文件路径集中在模块顶部
# ============================================================

# 项目根目录：向上两级（core → src → 项目根）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _resolve_path(relative_path: str) -> Path:
    """将相对路径转换为项目根目录下的绝对路径。

    无论从哪个目录运行程序，都能正确定位配置文件。

    Args:
        relative_path: 相对于项目根目录的路径

    Returns:
        绝对路径
    """
    return _PROJECT_ROOT / relative_path


# 配置文件路径（按需修改即可）
ENV_FILE = _resolve_path(".env")
CONFIG_YAML = _resolve_path("config.yaml")
LOGGING_CONFIG_YAML = _resolve_path("config") / "logging.yaml"
PRESETS_YAML = _resolve_path("config") / "presets.yaml"


# ============================================================
# Pydantic 配置模型 — 类型安全的配置结构
# ============================================================

class LLMConfig(BaseModel):
    """LLM 相关配置模型。"""
    default_model: str = "deepseek-v4-flash"
    timeout: int = 60
    max_retries: int = 3
    streaming: bool = True
    available_models: List[Dict[str, str]] = Field(default_factory=list)


class SQLiteConfig(BaseModel):
    """SQLite 后端配置。"""
    path: str = "data/sqlite/app.db"


class MySQLConfig(BaseModel):
    """MySQL 后端配置。"""
    pool_size: int = 5
    pool_recycle: int = 3600


class FileStorageConfig(BaseModel):
    """文件系统后端配置。"""
    path: str = "data/file_storage"
    format: str = "json"


class StorageConfig(BaseModel):
    """存储总配置。"""
    type: str = "sqlite"
    sqlite: SQLiteConfig = Field(default_factory=SQLiteConfig)
    mysql: MySQLConfig = Field(default_factory=MySQLConfig)
    file: FileStorageConfig = Field(default_factory=FileStorageConfig)


class SessionConfig(BaseModel):
    """会话配置。"""
    title_max_length: int = 30
    list_page_size: int = 20


class ExportConfig(BaseModel):
    """导出配置。"""
    path_template: str = "data/users/{username}/exports/{session_title}_{date}.md"


class DevConfig(BaseModel):
    """开发环境配置。"""
    debug: bool = False


# ============================================================
# ConfigManager
# ============================================================

class ConfigManager:
    """配置管理器 — 加载、合并、暴露所有项目配置。

    使用方式：
        config = ConfigManager()

        # 访问 LLM 配置
        print(config.get("llm", "default_model"))  # → "deepseek-v4-flash"

        # 使用属性快捷方式
        print(config.api_key)          # → 从 .env 加载的 API_KEY
        print(config.storage_type)     # → "sqlite"

        # 获取完整子配置
        presets = config.presets       # → 内置预设列表
        logging_cfg = config.logging_config  # → 日志完整配置
    """

    def __init__(self, env: Optional[str] = None) -> None:
        """初始化配置管理器，自动加载所有配置文件。

        Args:
            env: 运行环境标识（dev/test/prod），
                 默认从 APP_ENV 环境变量读取，未设置则为 "dev"
        """
        # 1. 确定运行环境
        self._env = env or os.getenv("APP_ENV", "dev")

        # 2. 加载 .env 环境变量
        self._env_vars: Dict[str, str] = {}
        self._load_env()

        # 3. 加载 config.yaml 全局配置
        self._config: Dict[str, Any] = {}
        self._load_config_yaml()

        # 4. 加载 config/logging.yaml 日志配置
        self._logging_config: Dict[str, Any] = {}
        self._load_logging_config()

        # 5. 加载 config/presets.yaml 内置预设
        self._presets: List[Dict[str, Any]] = []
        self._load_presets()

    # ----------------------------------------------------------
    # 内部加载方法
    # ----------------------------------------------------------

    def _load_env(self) -> None:
        """加载 .env 文件中的环境变量。

        使用 python-dotenv 将 .env 内容注入 os.environ，
        同时缓存到 self._env_vars 字典中方便直接访问。

        加载顺序：
        1. 基础 .env 文件（必须存在）
        2. 环境特定 .env 文件，如 .env.dev（可选，覆盖基础值）
        """
        # 加载基础 .env
        if ENV_FILE.exists():
            # load_dotenv 会将变量注入 os.environ
            load_dotenv(ENV_FILE, override=True)
            # 重新读取以便缓存到 _env_vars
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        self._env_vars[key] = value

        # 加载环境特定的 .env（如 .env.dev / .env.test / .env.prod）
        env_specific_file = _PROJECT_ROOT / f".env.{self._env}"
        if env_specific_file.exists():
            load_dotenv(env_specific_file, override=True)
            with open(env_specific_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        self._env_vars[key] = value

    def _load_config_yaml(self) -> None:
        """加载 config.yaml 全局配置文件。

        使用 PyYAML 的安全加载器（SafeLoader），
        防止 YAML 反序列化漏洞。

        加载失败时使用空字典，程序不中断，
        各配置项的默认值保证基本运行。
        """
        if not CONFIG_YAML.exists():
            print(f"⚠ 配置文件 {CONFIG_YAML} 不存在，使用默认配置")
            return

        try:
            with open(CONFIG_YAML, "r", encoding="utf-8") as f:
                self._config = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            print(f"⚠ 配置文件 {CONFIG_YAML} 解析失败: {e}，使用默认配置")

    def _load_logging_config(self) -> None:
        """加载 config/logging.yaml 日志配置文件。

        日志配置独立于全局配置，方便：
        - 不同环境使用不同的日志策略
        - 热更新日志级别
        """
        if not LOGGING_CONFIG_YAML.exists():
            print(f"⚠ 日志配置 {LOGGING_CONFIG_YAML} 不存在，使用默认配置")
            return

        try:
            with open(LOGGING_CONFIG_YAML, "r", encoding="utf-8") as f:
                self._logging_config = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            print(f"⚠ 日志配置 {LOGGING_CONFIG_YAML} 解析失败: {e}")

    def _load_presets(self) -> None:
        """加载 config/presets.yaml 系统内置预设。

        系统内置预设是所有用户共享的角色模板。
        """
        if not PRESETS_YAML.exists():
            print(f"⚠ 预设配置 {PRESETS_YAML} 不存在")
            return

        try:
            with open(PRESETS_YAML, "r", encoding="utf-8") as f:
                preset_data = yaml.safe_load(f) or {}
                self._presets = preset_data.get("presets", [])
        except yaml.YAMLError as e:
            print(f"⚠ 预设配置 {PRESETS_YAML} 解析失败: {e}")

    # ----------------------------------------------------------
    # 通用访问方法
    # ----------------------------------------------------------

    def get(self, *keys: str, default: Any = None) -> Any:
        """按路径访问配置值。

        支持多级 key，如 config.get("llm", "default_model") 等价于 config["llm"]["default_model"]。

        Args:
            *keys: 配置路径的 key 序列
            default: 不存在时返回的默认值

        Returns:
            配置值，不存在时返回 default

        Examples:
            >>> config.get("llm", "default_model")
            'gpt-4o-mini'
            >>> config.get("llm", "nonexistent", default="fallback")
            'fallback'
        """
        node: Any = self._config
        for key in keys:
            if isinstance(node, dict):
                node = node.get(key)
                if node is None:
                    return default
            else:
                return default
        return node

    def get_env(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """获取环境变量值。

        优先级：os.environ（运行时） > 缓存（.env 文件） > default

        Args:
            key: 环境变量名
            default: 不存在时的默认值

        Returns:
            环境变量值
        """
        return os.getenv(key, self._env_vars.get(key, default))

    # ----------------------------------------------------------
    # 属性快捷访问 — LLM 相关
    # ----------------------------------------------------------

    @property
    def api_base_url(self) -> str:
        """LLM API Base URL。

        来源于 .env 中的 API_BASE_URL 环境变量。
        兼容所有 OpenAI API 格式的服务商（OpenAI / DeepSeek / Ollama等）。
        """
        return self.get_env("API_BASE_URL", "https://api.openai.com/v1") or ""

    @property
    def api_key(self) -> str:
        """LLM API Key。

        来源于 .env 中的 API_KEY 环境变量。
        """
        return self.get_env("API_KEY", "") or ""

    @property
    def model_name(self) -> str:
        """当前默认模型名称。

        优先级：.env MODEL_NAME > config.yaml llm.default_model > 硬编码默认值
        """
        env_model = self.get_env("MODEL_NAME")
        if env_model:
            return env_model
        return str(self.get("llm", "default_model", default="deepseek-v4-flash"))

    @property
    def llm_timeout(self) -> int:
        """LLM API 调用超时时间（秒）。"""
        return int(self.get("llm", "timeout", default=60))

    @property
    def llm_max_retries(self) -> int:
        """LLM API 调用最大重试次数。"""
        return int(self.get("llm", "max_retries", default=3))

    @property
    def llm_streaming(self) -> bool:
        """是否启用流式输出。"""
        return bool(self.get("llm", "streaming", default=True))

    @property
    def available_models(self) -> List[Dict[str, str]]:
        """可用模型列表（用于模型切换）。"""
        return list(self.get("llm", "available_models", default=[]))

    # ----------------------------------------------------------
    # 属性快捷访问 — 存储相关
    # ----------------------------------------------------------

    @property
    def storage_type(self) -> str:
        """当前存储后端类型：sqlite / mysql / file。"""
        return str(self.get("storage", "type", default="sqlite"))

    @property
    def sqlite_path(self) -> str:
        """SQLite 数据库文件路径。"""
        return str(self.get("storage", "sqlite", "path", default="data/sqlite/app.db"))

    @property
    def mysql_config(self) -> Dict[str, Any]:
        """MySQL 连接配置。"""
        pool_config = self.get("storage", "mysql", default={})
        return {
            "host": self.get_env("MYSQL_HOST", "localhost"),
            "port": int(self.get_env("MYSQL_PORT", "3306") or "3306"),
            "user": self.get_env("MYSQL_USER", "root"),
            "password": self.get_env("MYSQL_PASSWORD", ""),
            "database": self.get_env("MYSQL_DATABASE", "langchain_chat"),
            "pool_size": pool_config.get("pool_size", 5),
            "pool_recycle": pool_config.get("pool_recycle", 3600),
        }

    # ----------------------------------------------------------
    # 属性快捷访问 — 会话与导出
    # ----------------------------------------------------------

    @property
    def session_title_max_length(self) -> int:
        """会话标题自动生成时截取的最大长度。"""
        return int(self.get("session", "title_max_length", default=30))

    @property
    def session_list_page_size(self) -> int:
        """会话列表分页大小。"""
        return int(self.get("session", "list_page_size", default=20))

    @property
    def export_path_template(self) -> str:
        """导出文件路径模板。"""
        return str(self.get(
            "export", "path_template",
            default="data/users/{username}/exports/{session_title}_{date}.md"
        ))

    # ----------------------------------------------------------
    # 属性快捷访问 — 开发环境
    # ----------------------------------------------------------

    @property
    def env(self) -> str:
        """当前运行环境：dev / test / prod。"""
        return self._env

    @property
    def debug(self) -> bool:
        """是否处于调试模式。"""
        return bool(self.get("dev", "debug", default=False))

    # ----------------------------------------------------------
    # 完整配置暴露
    # ----------------------------------------------------------

    @property
    def config(self) -> Dict[str, Any]:
        """完整全局配置字典（config.yaml 的全部内容）。

        Returns:
            配置字典的浅拷贝，防止外部意外修改。
        """
        return dict(self._config)

    @property
    def presets(self) -> List[Dict[str, Any]]:
        """系统内置预设列表。

        Returns:
            预设字典列表的浅拷贝。
        """
        return list(self._presets)

    @property
    def logging_config(self) -> Dict[str, Any]:
        """日志配置字典（logging.yaml 的全部内容）。

        Returns:
            日志配置的浅拷贝。
        """
        return dict(self._logging_config)
