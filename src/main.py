"""
程序总入口模块。

职责：
- 解析启动参数
- 初始化配置
- 启动 TUI 主应用

后续步骤中会逐步对接：
- ConfigManager：加载配置
- StorageFactory：创建存储后端
- UserManager、SessionManager、ChatEngine：核心业务
- TUI App：交互界面

当前 Step 1 只输出启动信息，验证项目骨架正确搭建。
"""

import sys

# 在 Windows 环境下强制使用 UTF-8 编码输出
# 避免 emoji 等 Unicode 字符触发 GBK 编码错误
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")


def main() -> None:
    """程序主入口函数。

    后续步骤中会在此处完成配置加载、后端初始化、
    业务管理器注入和 TUI 启动等完整流程。
    """
    print("\U0001f389 LangChain Chat 项目已启动")
    print(f"   Python 版本: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    print(f"   项目版本: 0.1.0")
    print()
    print("   后续步骤将逐步实现：")
    print("   Step 2 → 数据模型 + 存储接口 + TUI 骨架")
    print("   Step 3 → SQLite 后端 + 数据库初始化")
    print("   ...")
    print("   Step 7 → 第一次真正的多轮流式对话！（核心里程碑）")


if __name__ == "__main__":
    main()
