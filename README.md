# LangChain Chat

> 基于 LangChain 的多轮会话系统，支持多用户、多模型、流式输出

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![uv](https://img.shields.io/badge/uv-package%20manager-orange)](https://docs.astral.sh/uv/)

## 📖 项目简介

LangChain Chat 是一个功能完备的大语言模型（LLM）对话系统，提供：

- 🚀 **多轮流式对话** — 基于 LangChain 的上下文连贯对话，逐 token 实时输出
- 👥 **多用户管理** — 独立的用户系统，数据完全隔离
- 🤖 **多模型支持** — 兼容所有 OpenAI API 格式的 LLM 服务（OpenAI / DeepSeek / Ollama / ...）
- 🎭 **角色预设** — 内置翻译助手、代码专家等多种角色，支持自定义
- 💾 **可插拔存储** — SQLite（默认）/ MySQL / File 三种后端，一键切换
- 🖥️ **TUI 界面** — Rich + prompt_toolkit 驱动的现代化命令行界面

本项目同时作为 **Python 企业级开发教学项目**，展示分层架构、依赖注入、抽象基类、设计模式等工程实践。

## 🏗️ 架构概览

```
┌─────────────────────────────────────┐
│   UI 层（TUI/WebUI）                │
├─────────────────────────────────────┤
│   接口定义层（UI Protocol）          │
├─────────────────────────────────────┤
│   核心业务层（Chat Engine / Session） │
├─────────────────────────────────────┤
│   数据模型层（Pydantic Schemas）     │
├─────────────────────────────────────┤
│   存储层（SQLite / MySQL / File）    │
└─────────────────────────────────────┘
```

- **分层架构**：清晰的职责分离，每层只与相邻层通信
- **全链路异步**：基于 `asyncio`，LLM 调用、数据库读写、文件 IO 全部异步
- **可插拔后端**：通过工厂模式实现存储后端的无缝切换

## 🚀 快速开始

### 前置要求

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) 包管理器

### 安装

```bash
# 1. 克隆项目
git clone <repo-url>
cd langchain-chat

# 2. 安装依赖（uv 自动创建虚拟环境）
uv sync

# 3. 配置 API Key
cp .env.example .env
# 编辑 .env，填入你的 API_BASE_URL 和 API_KEY

# 4. 启动
uv run python src/main.py
```

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `API_BASE_URL` | LLM 服务地址 | `https://api.openai.com/v1` |
| `API_KEY` | API 密钥 | —（必填） |
| `MODEL_NAME` | 默认模型 | `gpt-4o-mini` |
| `APP_ENV` | 运行环境（dev/test/prod） | `dev` |

## 📁 项目结构

```
langchain-chat/
├── src/
│   ├── core/          # 核心业务层
│   ├── models/        # 数据模型层（Pydantic）
│   ├── storage/       # 存储层（可插拔后端）
│   ├── interface/     # UI 接口定义
│   └── ui/            # UI 实现（TUI + WebUI 预留）
├── config/            # 配置文件（预设、日志）
├── tests/             # 测试目录
├── scripts/           # 工具脚本
├── docs/              # 文档
├── config.yaml        # 全局配置
├── pyproject.toml     # 项目元数据与依赖
└── .env.example       # 环境变量模板
```

## 🧪 开发

```bash
# 安装开发依赖（pytest、ruff）
uv sync --group dev

# 运行测试
uv run pytest

# 代码格式化与 Lint
uv run ruff check src/
uv run ruff format src/
```

## 📄 License

MIT License
