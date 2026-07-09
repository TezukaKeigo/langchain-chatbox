"""
TUI 复用组件 — 样式定义、格式化工具、通用渲染函数。

本模块提供 TUI 界面的基础构建块：
- 全局 Console 实例（统一输出入口）
- 预定义主题色板和样式常量
- 面板、表格、状态消息的快速渲染函数
- 文本格式化工具

设计原则：
- 所有 Rich 渲染输出通过本模块的 console 实例，保证样式一致
- 通用 UI 模式提取为函数，避免在各视图中重复代码
- 样式常量集中管理，方便整体换肤
"""

from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

# ============================================================
# 全局 Console 实例 — 整个 TUI 共享一个输出入口
# ============================================================

console = Console(
    force_terminal=True,   # 强制终端模式（即使输出被重定向也能正常渲染）
    highlight=True,        # 启用语法高亮（如 Python 代码片段）
    emoji=True,            # 启用 emoji 支持
    width=None,            # 自动检测终端宽度
)


# ============================================================
# 主题色板 — 集中管理所有颜色，方便统一换肤
# ============================================================

class Theme:
    """TUI 主题色板。

    使用 Rich 支持的颜色名称。
    修改此类的常量即可统一更换整个 TUI 的配色方案。

    命名规范：
    - PRIMARY: 主色调（标题、强调）
    - SUCCESS: 成功/确认操作
    - WARNING: 警告/需注意
    - ERROR: 错误/失败
    - ACCENT: 装饰/辅助色
    - MUTED: 次要信息/弱化文本
    """
    PRIMARY = "bright_cyan"
    SUCCESS = "green"
    WARNING = "yellow"
    ERROR = "red"
    ACCENT = "bright_magenta"
    MUTED = "dim white"
    HIGHLIGHT = "bright_yellow"
    USER_ROLE = "bright_green"     # 用户消息角色标识
    AI_ROLE = "bright_cyan"        # AI 消息角色标识
    SYSTEM_ROLE = "bright_yellow"  # 系统消息角色标识


# ============================================================
# 样式常量 — prompt_toolkit 输入框样式
# ============================================================

# prompt_toolkit 输入框的样式定义（用于 prompt() 函数）
INPUT_STYLE = {
    "": Theme.PRIMARY,           # 默认文字颜色
    "prompt": Theme.ACCENT,      # 提示符颜色（如 "你 >"）
}

# prompt_toolkit 底部工具栏样式
TOOLBAR_STYLE = {
    "bottom-toolbar": f"bg:#333333 {Theme.MUTED}",
}


# ============================================================
# 面板渲染函数
# ============================================================

def print_header(title: str, subtitle: Optional[str] = None) -> None:
    """渲染应用标题面板。

    用于主菜单顶部、各子菜单头部等需要醒目标题的场景。

    Args:
        title: 主标题文字
        subtitle: 副标题文字（可选）
    """
    content = Text()
    content.append(title, style=f"bold {Theme.PRIMARY}")
    if subtitle:
        content.append(f"\n{subtitle}", style=Theme.MUTED)

    panel = Panel(
        content,
        border_style=Theme.PRIMARY,
        box=box.ROUNDED,
        padding=(1, 2),
    )
    console.print(panel)


def print_section(text: str) -> None:
    """渲染章节标题。

    用于菜单中分隔不同功能区。

    Args:
        text: 章节标题文字
    """
    console.print(f"\n[{Theme.ACCENT}]{text}[/{Theme.ACCENT}]")
    console.print("─" * len(text))


# ============================================================
# 状态消息渲染
# ============================================================

def print_success(message: str) -> None:
    """渲染成功消息。

    使用 Rich Text 对象避免消息内容中的特殊字符
    （如方括号）被误解析为 Rich markup 标签。

    Args:
        message: 消息内容
    """
    output = Text()
    output.append("  ✓ ", style=Theme.SUCCESS)
    output.append(message, style=Theme.SUCCESS)
    console.print(output)


def print_error(message: str) -> None:
    """渲染错误消息。

    使用 Rich Text 对象避免消息内容中的特殊字符被误解析。

    Args:
        message: 错误描述
    """
    output = Text()
    output.append("  ✗ ", style=Theme.ERROR)
    output.append("错误: ", style=f"bold {Theme.ERROR}")
    output.append(message, style=Theme.ERROR)
    console.print(output)


def print_warning(message: str) -> None:
    """渲染警告消息。

    Args:
        message: 警告内容
    """
    output = Text()
    output.append("  ! ", style=Theme.WARNING)
    output.append(message, style=Theme.WARNING)
    console.print(output)


def print_info(message: str) -> None:
    """渲染信息提示。

    Args:
        message: 信息内容
    """
    output = Text()
    output.append("  i ", style=Theme.MUTED)
    output.append(message, style=Theme.MUTED)
    console.print(output)


# ============================================================
# 表格渲染
# ============================================================

def print_table(
    title: str,
    columns: List[Dict[str, str]],
    rows: List[List[Any]],
    show_index: bool = True,
) -> None:
    """渲染格式化表格。

    用于会话列表、用户列表、预设列表等数据展示场景。

    Args:
        title: 表格标题
        columns: 列定义，如 [{"key": "序号", "style": "cyan"}, ...]
        rows: 数据行列表，每行是一个值的列表
        show_index: 是否显示序号列

    Examples:
        >>> print_table(
        ...     "会话列表",
        ...     [{"key": "标题", "style": "cyan"}, {"key": "时间", "style": "dim"}],
        ...     [["测试会话", "2024-01-01 12:00"], ["代码问答", "2024-01-02 15:30"]]
        ... )
    """
    if not rows:
        console.print(f"\n  [{Theme.MUTED}]（暂无数据）[/{Theme.MUTED}]")
        return

    table = Table(
        title=f"\n[{Theme.PRIMARY}]{title}[/{Theme.PRIMARY}]",
        box=box.SIMPLE_HEAD,
        header_style=f"bold {Theme.PRIMARY}",
        border_style=Theme.MUTED,
        show_header=True,
        title_justify="left",
    )

    if show_index:
        table.add_column("#", style=Theme.MUTED, width=4, justify="right")

    for col in columns:
        table.add_column(
            col["key"],
            style=col.get("style", ""),
            width=col.get("width"),
            justify=col.get("justify", "left"),
            no_wrap=col.get("no_wrap", False),
        )

    for i, row in enumerate(rows, 1):
        if show_index:
            table.add_row(str(i), *[str(cell) for cell in row])
        else:
            table.add_row(*[str(cell) for cell in row])

    console.print(table)


# ============================================================
# 菜单列表渲染
# ============================================================

def print_menu_options(options: List[Dict[str, Any]], start_index: int = 1) -> None:
    """渲染菜单选项列表。

    统一的菜单样式，在各个子菜单中复用。

    Args:
        options: 菜单选项列表，每项含 {'key': str, 'label': str, 'desc': str}
        start_index: 起始序号（通常为 1）

    Examples:
        >>> print_menu_options([
        ...     {"key": "1", "label": "新建会话", "desc": "开始一轮新的对话"},
        ...     {"key": "2", "label": "历史会话", "desc": "加载之前的对话"},
        ... ])
    """
    max_label_len = max((len(opt.get("label", "")) for opt in options), default=0)

    for i, opt in enumerate(options, start_index):
        label = opt.get("label", "")
        desc = opt.get("desc", "")
        padding = " " * (max_label_len - len(label) + 2)
        console.print(
            f"  [{Theme.HIGHLIGHT}]{opt.get('key', str(i))}.[/{Theme.HIGHLIGHT}] "
            f"[bold]{label}[/bold]{padding}"
            f"[{Theme.MUTED}]{desc}[/{Theme.MUTED}]"
        )


# ============================================================
# 文本格式化
# ============================================================

def truncate(text: str, max_length: int, suffix: str = "...") -> str:
    """截断文本到指定长度。

    Args:
        text: 原始文本
        max_length: 最大长度
        suffix: 截断后的后缀

    Returns:
        截断后的文本

    Examples:
        >>> truncate("这是一段很长的对话内容", 10)
        '这是一段很长的对...'
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def format_datetime(dt: Any) -> str:
    """格式化日期时间对象为统一的显示字符串。

    由于各存储后端可能返回字符串或 datetime 对象，
    此函数统一处理并输出 'YYYY-MM-DD HH:MM' 格式。

    Args:
        dt: datetime 对象或 ISO 格式字符串

    Returns:
        格式化后的日期时间字符串
    """
    if dt is None:
        return "未知"

    # 如果已经是字符串，尝试截取
    if isinstance(dt, str):
        # ISO 格式: "2024-01-15T14:30:00" → "2024-01-15 14:30"
        return dt.replace("T", " ")[:16]

    # datetime 对象
    return dt.strftime("%Y-%m-%d %H:%M")


def strip_markdown(text: str, max_length: int = 80) -> str:
    """去除 Markdown 标记，用于在纯文本终端中显示。

    当前只做基础处理（去 `#`、`*` 等），
    后续可升级为完整的 Markdown 到纯文本转换。

    Args:
        text: Markdown 格式文本
        max_length: 最大长度（截断用）

    Returns:
        纯文本版本
    """
    # 去除常见的 Markdown 标记
    result = text
    # 去除代码块
    while "```" in result:
        start = result.find("```")
        end = result.find("```", start + 3)
        if end != -1:
            result = result[:start] + "[代码块]" + result[end + 3:]
        else:
            break
    # 去除行内代码
    result = result.replace("`", "")
    # 去除加粗和斜体标记
    result = result.replace("**", "").replace("__", "")
    result = result.replace("*", "").replace("_", "")

    return truncate(result.strip(), max_length)
