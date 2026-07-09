"""
Pydantic 数据模型定义。

本模块定义了项目中所有核心数据实体的结构：
- User：用户信息与偏好
- Session：会话索引
- Message：单条对话消息
- Preset：角色预设（系统内置 + 用户自定义）
- UserConfig：用户偏好键值对

所有模型继承 pydantic.BaseModel，自动获得：
- 类型校验（运行时检查数据类型）
- 序列化/反序列化（model_dump / model_validate）
- IDE 智能补全（类型注解完整）
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


# ============================================================
# 工具函数
# ============================================================

def _new_id() -> str:
    """生成全局唯一的 ID 字符串（UUID4）。"""
    return str(uuid4())


def _now() -> datetime:
    """返回当前 UTC 时间（去除了时区信息的 naive datetime）。

    选择 naive datetime 的原因：
    - SQLite 不存储时区信息
    - 保持与数据库层的兼容性
    - 项目所有时间统一使用 UTC
    """
    return datetime.utcnow()


# ============================================================
# 数据模型
# ============================================================

class User(BaseModel):
    """用户模型。

    每个用户拥有独立的会话、预设、配置数据，
    用户之间数据完全隔离。

    Attributes:
        id: 用户唯一标识（UUID4）
        username: 用户名（全局唯一）
        default_model: 用户偏好的默认 LLM 模型
        default_preset_id: 用户偏好的默认预设角色（可为空）
        created_at: 用户创建时间
        updated_at: 用户信息最后更新时间
    """
    id: str = Field(default_factory=_new_id, description="用户唯一标识")
    username: str = Field(..., min_length=1, max_length=50, description="用户名（全局唯一）")
    default_model: str = Field(default="deepseek-v4-flash", description="默认模型")
    default_preset_id: Optional[str] = Field(default=None, description="默认预设ID")
    created_at: datetime = Field(default_factory=_now, description="创建时间")
    updated_at: datetime = Field(default_factory=_now, description="更新时间")


class Session(BaseModel):
    """会话模型。

    一个用户拥有多个会话，每个会话包含多条消息。
    会话记录使用的模型、预设角色和 Token 累计用量。

    Attributes:
        id: 会话唯一标识（UUID4）
        user_id: 所属用户 ID
        title: 会话标题（自动生成或手动设置）
        model_name: 该会话使用的 LLM 模型
        preset_id: 该会话使用的预设角色 ID（可为空）
        total_prompt_tokens: 累计 prompt token 消耗
        total_completion_tokens: 累计 completion token 消耗
        created_at: 会话创建时间
        updated_at: 会话最后活跃时间
    """
    id: str = Field(default_factory=_new_id, description="会话唯一标识")
    user_id: str = Field(..., description="所属用户ID")
    title: str = Field(default="新会话", max_length=200, description="会话标题")
    model_name: str = Field(default="deepseek-v4-flash", description="使用的模型名称")
    preset_id: Optional[str] = Field(default=None, description="使用的预设ID")
    total_prompt_tokens: int = Field(default=0, ge=0, description="累计Prompt Token")
    total_completion_tokens: int = Field(default=0, ge=0, description="累计Completion Token")
    created_at: datetime = Field(default_factory=_now, description="创建时间")
    updated_at: datetime = Field(default_factory=_now, description="更新时间")


class Message(BaseModel):
    """消息模型。

    会话中的每条消息（用户输入 或 AI 回复）。
    记录消息内容、角色和该轮的 Token 消耗。

    Attributes:
        id: 消息唯一标识（UUID4）
        session_id: 所属会话 ID
        role: 消息角色（human=用户输入, ai=AI回复, system=系统提示）
        content: 消息正文内容
        prompt_tokens: 该消息消耗的 prompt tokens
        completion_tokens: 该消息消耗的 completion tokens
        created_at: 消息创建时间
    """
    id: str = Field(default_factory=_new_id, description="消息唯一标识")
    session_id: str = Field(..., description="所属会话ID")
    role: str = Field(..., description="消息角色: human / ai / system")
    content: str = Field(default="", description="消息内容")
    prompt_tokens: int = Field(default=0, ge=0, description="Prompt Token 消耗")
    completion_tokens: int = Field(default=0, ge=0, description="Completion Token 消耗")
    created_at: datetime = Field(default_factory=_now, description="创建时间")


class Preset(BaseModel):
    """预设角色模型。

    系统内置预设（is_builtin=True, user_id=None）对所有用户可见，
    用户自定义预设（is_builtin=False, user_id=具体用户）仅对所属用户可见。

    Attributes:
        id: 预设唯一标识（UUID4）
        user_id: 所属用户 ID（None 表示系统内置）
        name: 预设名称
        description: 预设功能描述
        system_prompt: 预设的系统提示词
        is_builtin: 是否为系统内置预设
        created_at: 创建时间
        updated_at: 更新时间
    """
    id: str = Field(default_factory=_new_id, description="预设唯一标识")
    user_id: Optional[str] = Field(default=None, description="所属用户ID（NULL=系统内置）")
    name: str = Field(..., min_length=1, max_length=100, description="预设名称")
    description: str = Field(default="", description="预设描述")
    system_prompt: str = Field(..., min_length=1, description="系统提示词")
    is_builtin: bool = Field(default=False, description="是否系统内置")
    created_at: datetime = Field(default_factory=_now, description="创建时间")
    updated_at: datetime = Field(default_factory=_now, description="更新时间")


class UserConfig(BaseModel):
    """用户配置模型。

    键值对形式的用户偏好存储，灵活扩展。

    Attributes:
        id: 配置项唯一标识（UUID4）
        user_id: 所属用户 ID
        key: 配置键名
        value: 配置值
        updated_at: 最后更新时间
    """
    id: str = Field(default_factory=_new_id, description="配置唯一标识")
    user_id: str = Field(..., description="所属用户ID")
    key: str = Field(..., min_length=1, max_length=100, description="配置键名")
    value: str = Field(default="", description="配置值")
    updated_at: datetime = Field(default_factory=_now, description="更新时间")


# ============================================================
# 角色常量
# ============================================================

class MessageRole:
    """消息角色常量。

    使用字符串常量而非枚举，保持与 LangChain 消息类型的兼容性。
    """
    HUMAN = "human"      # 用户输入
    AI = "ai"            # AI 回复
    SYSTEM = "system"    # 系统提示词
