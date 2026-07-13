# LangChain Chat

> 基于 LangChain 的多轮会话系统，支持多用户、多模型、流式输出

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![uv](https://img.shields.io/badge/uv-package%20manager-orange)](https://docs.astral.sh/uv/)

---

## 📖 项目简介

LangChain Chat 是一个功能完备的大语言模型（LLM）对话系统，提供：

- 🚀 **多轮流式对话** — 基于 LangChain 的上下文连贯对话，逐 token 实时输出
- 👥 **多用户管理** — 独立的用户系统，数据完全隔离
- 🤖 **多模型支持** — 兼容所有 OpenAI API 格式的 LLM 服务（DeepSeek / Kimi / Qwen / OpenAI / Ollama）
- 🎭 **角色预设** — 内置翻译助手、代码专家等多种角色，支持自定义
- 💾 **可插拔存储** — SQLite / MySQL / File 三种后端，配置一键切换
- 📝 **对话导出** — 一键导出会话为 Markdown 文件
- 🔍 **对话搜索** — 跨会话全文搜索历史消息
- 🖥️ **TUI 界面** — Rich + prompt_toolkit 驱动的现代化命令行界面
- 📊 **Token 统计** — 实时显示每轮和累计 Token 消耗
- ⚙️ **模型切换** — 运行时无缝切换模型，对话上下文不丢失

本项目同时作为 **Python 企业级开发教学项目**，展示分层架构、依赖注入、抽象基类、设计模式等工程实践。

---

## 🏗️ 架构概览

```
┌─────────────────────────────────────────────────┐
│               UI 层 (TUI / WebUI 预留)           │
│         Rich + prompt_toolkit 驱动              │
├─────────────────────────────────────────────────┤
│              接口定义层 (UI Protocol)             │
│         AbstractUI — 解耦业务与 UI 实现           │
├─────────────────────────────────────────────────┤
│              核心业务层                           │
│   ┌──────────┬──────────┬──────────┬─────────┐  │
│   │ChatEngine│UserMgr   │SessionMgr│PresetMgr│  │
│   └──────────┴──────────┴──────────┴─────────┘  │
├─────────────────────────────────────────────────┤
│           数据模型层 (Pydantic Schemas)           │
│         User / Session / Message / Preset        │
├─────────────────────────────────────────────────┤
│           存储抽象层 (StorageBackend ABC)         │
│   ┌──────────┬──────────┬──────────────────┐    │
│   │ SQLite   │  MySQL   │  File (JSON)     │    │
│   └──────────┴──────────┴──────────────────┘    │
└─────────────────────────────────────────────────┘
```

### 设计原则

| 原则 | 实践 |
|------|------|
| **分层架构** | UI → Core → Storage，每层只与相邻层通信 |
| **依赖倒置** | 业务层依赖 `StorageBackend` 接口，不依赖具体实现 |
| **全链路异步** | 基于 `asyncio`，LLM 调用、数据库读写、文件 IO 全部异步 |
| **工厂模式** | `StorageFactory.create(config)` 根据配置创建存储后端 |
| **单例模式** | `ConfigManager` 全局唯一实例 |
| **状态容器** | 通过共享 `state` 字典在视图间通信 |

---

## 🚀 快速开始

### 前置要求

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) 包管理器

### 安装

```bash
# 1. 克隆项目
git clone <repo-url>
cd langchain-chat

# 2. 安装依赖
uv sync

# 3. 配置 API Key
cp .env.example .env
# 编辑 .env，填入你的 API Key

# 4. 启动
uv run python src/main.py
```

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `API_BASE_URL` | LLM 服务地址（全局回退） | `https://api.openai.com/v1` |
| `API_KEY` | API 密钥（全局回退） | — |
| `MODEL_NAME` | 默认模型 | `deepseek-v4-flash` |
| `DEEPSEEK_API_KEY` | DeepSeek 专属密钥 | 回退到 `API_KEY` |
| `KIMI_API_KEY` | Kimi/Moonshot 专属密钥 | 回退到 `API_KEY` |
| `QWEN_API_KEY` | Qwen/DashScope 专属密钥 | 回退到 `API_KEY` |
| `MYSQL_HOST` | MySQL 主机地址 | `localhost` |
| `MYSQL_PORT` | MySQL 端口 | `3306` |
| `MYSQL_USER` | MySQL 用户名 | `root` |
| `MYSQL_PASSWORD` | MySQL 密码 | — |
| `MYSQL_DATABASE` | MySQL 数据库名 | `langchain_chat` |
| `APP_ENV` | 运行环境（dev/test/prod） | `dev` |

### 多模型配置

每个模型可独立配置 API Key 和 Base URL。在 `config.yaml` 的 `llm.available_models` 中添加条目：

```yaml
llm:
  available_models:
    - name: "my-custom-model"
      provider: "custom"
      env_key: "MY_MODEL_API_KEY"        # 环境变量名
      api_base_url: "https://api.example.com/v1"
      description: "自定义模型"
```

程序会自动从对应环境变量读取密钥；未配置时回退到全局 `API_KEY`。

---

## 📁 项目结构

```
langchain-chat/
├── src/
│   ├── core/                    # 核心业务层
│   │   ├── chat_engine.py       #   对话引擎（LLM 调用 + 流式 + Token）
│   │   ├── config_manager.py    #   配置管理（.env + config.yaml）
│   │   ├── user_manager.py      #   用户管理（创建/切换/删除）
│   │   ├── session_manager.py   #   会话管理（CRUD + 导出 + 搜索）
│   │   └── preset_manager.py    #   预设管理（内置 + 自定义）
│   ├── models/
│   │   └── schemas.py           #   Pydantic 数据模型
│   ├── storage/
│   │   ├── base.py              #   存储抽象基类（22 个抽象方法）
│   │   ├── factory.py           #   工厂方法（根据配置创建后端）
│   │   ├── sqlite_backend.py    #   SQLite 后端实现
│   │   ├── mysql_backend.py     #   MySQL 后端实现
│   │   └── file_backend.py      #   File (JSON) 后端实现
│   ├── interface/
│   │   └── ui_protocol.py       #   UI 协议接口 + 扩展预留
│   ├── ui/
│   │   ├── tui/                 #   TUI 实现
│   │   │   ├── app.py           #     主应用（路由 + 状态管理）
│   │   │   ├── menu_view.py     #     菜单视图
│   │   │   ├── chat_view.py     #     对话视图
│   │   │   └── widgets.py       #     通用组件
│   │   └── web/                 #   WebUI 预留
│   └── main.py                  #   程序入口
├── config/
│   ├── logging.yaml             #   日志配置（JSON + 旋转文件）
│   └── presets.yaml             #   内置预设定义
├── tests/
│   ├── conftest.py              #   pytest 共享 fixtures
│   ├── test_storage.py          #   存储后端测试（70 用例）
│   ├── test_user_manager.py     #   用户管理测试（22 用例）
│   ├── test_session_manager.py  #   会话管理测试（29 用例）
│   ├── test_chat_engine.py      #   对话引擎测试（60 用例）
│   └── test_step*.py            #   旧版独立测试脚本
├── scripts/
│   └── init_db.py               #   数据库初始化脚本
├── docs/
│   └── architecture.md          #   架构文档
├── config.yaml                  #   全局配置文件
├── pyproject.toml               #   项目元数据与依赖
├── .env.example                 #   环境变量模板
└── README.md                    #   本文件
```

---

## ⚙️ 配置

### 存储后端切换

编辑 `config.yaml` 中的 `storage.type`：

```yaml
storage:
  type: sqlite    # sqlite | mysql | file
```

| 后端 | 适用场景 | 特点 |
|------|----------|------|
| **SQLite** | 单机开发 / 个人使用 | 零配置，嵌入式，默认选项 |
| **MySQL** | 生产环境 / 多实例 | 连接池，高并发，数据可靠性高 |
| **File** | 轻量 / 无数据库依赖 | 纯 JSON 文件，可读性好，易于备份 |

### 日志配置

`config/logging.yaml` 控制日志行为：

- **console** — 可读格式，仅 WARNING+ 级别
- **app.log** — JSON 格式，记录所有 INFO+ 日志，10MB × 10 个备份
- **error.log** — JSON 格式，仅 ERROR+ 级别，5MB × 5 个备份

日志文件位于 `logs/` 目录，启动时自动创建。

---

## 🧪 测试

```bash
# 安装开发依赖
uv sync --group dev

# 运行 pytest 测试套件（181 用例）
uv run pytest tests/

# 运行旧版独立测试
uv run python tests/test_step3_crud.py
uv run python tests/test_step8_session_mgmt.py
```

### 测试覆盖

| 模块 | 测试文件 | 用例数 | 覆盖内容 |
|------|----------|--------|----------|
| 存储后端 | `test_storage.py` | 70 | SQLite + File 全部 CRUD、工厂、级联删除 |
| 用户管理 | `test_user_manager.py` | 22 | 创建校验、查询、删除、状态管理 |
| 会话管理 | `test_session_manager.py` | 29 | 会话 CRUD、消息、Token、标题、导出、搜索 |
| 对话引擎 | `test_chat_engine.py` | 60 | 提示词、历史、Token、模型切换、错误处理 |

---

## 📋 使用流程

### 首次使用

1. **启动程序** → `uv run python src/main.py`
2. **创建用户** → 用户管理 → 新建用户 → 输入用户名
3. **选择预设**（可选）→ 预设管理 → 浏览并选择角色
4. **开始对话** → 开始对话 → 输入消息 → 实时流式回复
5. **切换模型** → 对话中输入 `/model` → 选择目标模型
6. **查看历史** → 会话管理 → 加载历史会话

### 常用操作

| 操作 | 路径 |
|------|------|
| 新建会话 | 会话管理 → 新建会话 |
| 搜索消息 | 会话管理 → 搜索消息 → 输入关键词 |
| 导出对话 | 会话管理 → 导出会话 → 生成 Markdown 文件 |
| 重命名会话 | 会话管理 → 重命名会话 |
| 删除会话 | 会话管理 → 删除会话 |
| 全局设置 | 设置 → 修改默认模型/存储后端 |

---

## 🗺️ 开发路线

项目按 15 个步骤迭代构建，每步可独立运行与回退：

| Step | Tag | 内容 |
|------|-----|------|
| 1 | `step-1-init` | 项目初始化与工程化配置 |
| 2 | `step-2-skeleton` | 数据模型 + 存储接口 + TUI 骨架 |
| 3 | `step-3-sqlite` | SQLite 存储后端 |
| 4 | `step-4-user-mgmt` | 用户管理 + TUI 用户菜单 |
| 5 | `step-5-presets` | 预设管理 + TUI 预设菜单 |
| 6 | `step-6-chat-engine` | 对话引擎核心 |
| 7 | `step-7-first-chat` | **核心里程碑：首轮多轮对话** |
| 8 | `step-8-session-mgmt` | 会话管理完善 |
| 9 | `step-9-search` | 对话搜索 |
| 10 | `step-10-export-switch` | 导出 + 模型切换 |
| 11 | `step-11-mysql` | MySQL 后端 |
| 12 | `step-12-logging-file` | File 后端 + 日志系统 |
| 13 | `step-13-tests` | 单元测试（pytest 181 用例） |
| 14 | `step-14-docs-extend` | 文档 + 扩展预留 |
| 15 | `step-15-envs` | 多环境配置区分 |

```bash
# 回退到任意步骤
git checkout step-7-first-chat

# 回到最新
git checkout main

# 查看所有 tag
git tag
```

---

## 🔧 扩展预留

以下接口已在 `src/interface/ui_protocol.py` 中预留：

| 扩展方向 | 预留内容 | 说明 |
|----------|----------|------|
| **WebUI** | `AbstractUI` 抽象基类 | 实现全部抽象方法即可接入 FastAPI/Flask |
| **多模型对比** | `compare_models()` | 同时向多个模型发送同一问题，并排对比输出 |
| **图文理解** | `upload_image()` | 上传图片附件，传入 LLM 视觉模型 |
| **语音输入** | `start_voice_input()` / `stop_voice_input()` | 语音转文字输入 |
| **Tool Calling** | `register_tool()` / `list_tools()` | LLM 工具调用注册与管理 |

---

## 📄 License

MIT License
