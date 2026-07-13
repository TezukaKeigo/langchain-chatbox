# LangChain Chat — 架构文档

> 版本：v1.2 | 日期：2026-07-10 | 基于 Step 14

---

## 目录

1. [系统概述](#1-系统概述)
2. [分层架构](#2-分层架构)
3. [数据流](#3-数据流)
4. [模块详解](#4-模块详解)
5. [设计模式](#5-设计模式)
6. [存储后端设计](#6-存储后端设计)
7. [配置管理设计](#7-配置管理设计)
8. [异常处理策略](#8-异常处理策略)
9. [扩展点设计](#9-扩展点设计)
10. [决策记录](#10-决策记录)

---

## 1. 系统概述

LangChain Chat 是一个基于 LangChain 的多轮对话系统，采用 **分层架构 + 全链路异步 + 可插拔存储** 设计。核心流程为：

```
用户输入 → TUI 界面 → ChatEngine (LLM调用) → 流式输出 → SessionManager (持久化)
```

### 技术栈

| 层次 | 技术 | 用途 |
|------|------|------|
| LLM 框架 | LangChain + langchain-openai | 统一的模型调用接口 |
| 异步 | Python asyncio | 全链路异步（LLM、DB、文件 IO） |
| TUI | Rich + prompt_toolkit | 现代化终端界面 |
| 数据校验 | Pydantic v2 | 数据模型定义与序列化 |
| SQLite | aiosqlite | 异步 SQLite 驱动 |
| MySQL | aiomysql | 异步 MySQL 驱动（连接池） |
| 配置 | PyYAML + python-dotenv | YAML 配置 + 环境变量 |
| 测试 | pytest + pytest-asyncio | 异步测试框架 |

---

## 2. 分层架构

```
┌──────────────────────────────────────────────────────────┐
│                      入口层 (main.py)                     │
│          初始化 → 配置 → 存储 → 日志 → 启动 TUI            │
├──────────────────────────────────────────────────────────┤
│                    UI 接口层 (interface/)                  │
│        AbstractUI — 定义 UI 与业务层的通信协议             │
│        实现：TUIApp (ui/tui/app.py)                       │
│        预留：WebUIApp (ui/web/)                            │
├───────────────────┬──────────────────────────────────────┤
│    视图层          │          核心业务层 (core/)            │
│  ┌──────────────┐ │  ┌────────────┬────────────────────┐ │
│  │  MenuView    │ │  │ ChatEngine │  对话引擎           │ │
│  │  ChatView    │ │  │            │  • LLM 调用         │ │
│  │  Widgets     │ │  │            │  • 流式输出         │ │
│  └──────────────┘ │  │            │  • Token 统计       │ │
│                   │  │            │  • 模型切换         │ │
│                   │  ├────────────┼────────────────────┤ │
│                   │  │UserManager │  用户管理           │ │
│                   │  │            │  • 创建/切换/删除    │ │
│                   │  │            │  • 状态同步         │ │
│                   │  ├────────────┼────────────────────┤ │
│                   │  │SessionMgr  │  会话管理           │ │
│                   │  │            │  • 消息保存/加载     │ │
│                   │  │            │  • 标题生成/Token   │ │
│                   │  │            │  • 导出/Search      │ │
│                   │  ├────────────┼────────────────────┤ │
│                   │  │PresetMgr   │  预设管理           │ │
│                   │  │            │  • 内置预设同步      │ │
│                   │  │            │  • 自定义 CRUD      │ │
│                   │  ├────────────┼────────────────────┤ │
│                   │  │ConfigMgr   │  配置管理           │ │
│                   │  │            │  • .env + config    │ │
│                   │  │            │  • 多环境覆盖       │ │
│                   │  └────────────┴────────────────────┘ │
├───────────────────┴──────────────────────────────────────┤
│                   数据模型层 (models/)                     │
│      User / Session / Message / Preset / UserConfig      │
│              Pydantic BaseModel + 数据校验                 │
├──────────────────────────────────────────────────────────┤
│                 存储抽象层 (storage/)                      │
│               StorageBackend (ABC)                        │
│         22 个抽象方法，定义完整 CRUD 接口                   │
│     ┌────────────┬────────────┬──────────────────┐       │
│     │ SQLite     │  MySQL     │  File (JSON)     │       │
│     │ aiosqlite  │  aiomysql  │  asyncio + json  │       │
│     └────────────┴────────────┴──────────────────┘       │
│                  StorageFactory — 工厂模式                 │
└──────────────────────────────────────────────────────────┘
```

### 层间通信规则

| 规则 | 说明 |
|------|------|
| **单向依赖** | 上层依赖下层接口，下层不知道上层存在 |
| **接口隔离** | 业务层通过 `StorageBackend` 访问存储，不直接 import 具体实现 |
| **状态字典** | TUI 视图通过共享 `state` 字典通信，不直接互相调用 |
| **日志贯穿** | 所有层使用 `logging.getLogger("langchain_chat")` 统一日志通道 |

---

## 3. 数据流

### 3.1 对话请求完整链路

```
用户输入 "Python是什么?"
    │
    ▼
ChatView._chat_loop()
    │  prompt_toolkit.prompt()
    ▼
ChatEngine.chat_stream("Python是什么?")
    │
    ├─► _get_llm() → 懒初始化 ChatOpenAI (base_url/api_key/model)
    │
    ├─► _history.append(HumanMessage("Python是什么?"))
    │
    ├─► async for chunk in llm.astream(_history):
    │       yield {"content": delta, "done": False, ...}
    │       │
    │       ▼
    │   ChatView 实时渲染 token (Rich Live)
    │
    ├─► _update_token_stats(ai_message)
    │       usage_metadata → prompt/completion tokens
    │
    └─► yield {"content": "", "done": True, "total_tokens": 230}
            │
            ▼
        SessionManager.auto_save_turn()
            │
            ├─► save_user_message(session_id, "Python是什么?")
            ├─► save_ai_message(session_id, "Python是...")
            ├─► _accumulate_tokens(session_id, prompt, completion)
            └─► auto_title() (首次对话时)
```

### 3.2 模型切换流程

```
用户在对话中输入 /model
    │
    ▼
ChatView._switch_model_in_chat()
    │
    ├─► config.get_model_config("qwen-plus")
    │     → {"api_key": "sk-...", "api_base": "https://dashscope..."}
    │
    ├─► engine._create_llm("qwen-plus")  # 验证配置是否可用
    │     → ChatOpenAI(base_url=..., api_key=..., model="qwen-plus")
    │
    └─► engine.switch_model("qwen-plus")
          ├─► self._current_model = "qwen-plus"
          └─► self._llm = None  # 使旧实例失效
```

### 3.3 配置加载顺序

```
1. 读取 .env 文件 (python-dotenv → os.environ)
2. 读取环境特定 .env.{env} 文件 (覆盖)
3. 读取 config.yaml → Pydantic 模型校验
4. 读取 config/logging.yaml
5. 读取 config/presets.yaml
6. 运行时：环境变量 > config.yaml > 代码默认值
```

---

## 4. 模块详解

### 4.1 ChatEngine — 对话引擎

**职责**：封装 LLM 调用的全部逻辑，是系统的核心模块。

```
ChatEngine
├── _create_llm(model)    → ChatOpenAI 实例（每次新建，确保配置最新）
├── _get_llm()            → 懒初始化 + 配置验证
├── set_system_prompt()   → 设置角色预设（替换旧 SystemMessage）
├── load_history()        → 从 DB 加载历史（恢复会话上下文）
├── clear_history()       → 清空对话（保留系统提示词 + 重置 Token）
├── chat()                → 非流式调用，返回完整回复
├── chat_stream()         → 流式调用，异步生成器逐 token yield
├── switch_model()        → 运行时切换模型（失效 LLM 缓存）
├── _update_token_stats() → 从 AIMessage 提取 Token（兼容 4 种格式）
└── reset()               → 完全重置（清空历史 + Token + 提示词）
```

**Token 统计兼容路径**（按优先级）：

1. `message.usage_metadata` → `{input_tokens, output_tokens}` — DeepSeek/OpenAI 新格式
2. `message.response_metadata["token_usage"]` → `{prompt_tokens, completion_tokens}` — OpenAI 旧格式
3. `message.response_metadata["usage"]` → `{prompt_tokens/input_tokens, completion_tokens/output_tokens}` — Kimi/Qwen
4. 流式聚合扫描 — 遍历所有 chunk 的 response_metadata 兜底提取

### 4.2 SessionManager — 会话管理

**职责**：会话生命周期管理，是存储层与 ChatEngine 的桥梁。

- `get_or_create_session()` — 自动创建或复用当前会话
- `auto_save_turn()` — 一站式保存（用户消息 + AI回复 + Token 累计）
- `auto_title()` — 从首条消息生成标题（截断 + 去换行）
- `load_messages()` — 加载历史消息供 ChatEngine 恢复上下文
- `export_session()` — 导出为 Markdown（模板路径 + 文件名净化）
- `search_messages()` — 跨会话全文搜索（委托给存储层 SQL LIKE）

### 4.3 UserManager — 用户管理

**职责**：用户生命周期管理 + 状态同步。

- 创建校验：空白剥离 / 空字符串检查 / 50 字符上限 / 唯一性检查
- 删除用户时级联清除所有关联数据
- 切换用户时自动清除旧会话上下文（`current_session_id` → None）

### 4.4 ConfigManager — 配置管理

**职责**：统一管理 `.env`、`config.yaml`、`presets.yaml`、`logging.yaml`。

- **多模型配置**：`get_model_config(name)` 返回 `{api_key, api_base}`，优先模型专属密钥
- **Pydantic 校验**：`LLMConfig / StorageConfig / SessionConfig` 等类提供类型安全
- **环境覆盖**：基础 `config.yaml` + `config.{env}.yaml` 深度合并

---

## 5. 设计模式

| 模式 | 位置 | 说明 |
|------|------|------|
| **抽象基类** | `StorageBackend`、`AbstractUI` | 强制接口一致性，多实现可互换 |
| **工厂模式** | `StorageFactory` | 根据配置创建存储后端，开闭原则 |
| **单例模式** | `ConfigManager` | 全局唯一配置实例（未强制，约定使用） |
| **状态容器** | `state: Dict` | 视图间共享状态，替代回调/事件 |
| **策略模式** | `_update_token_stats()` | 多种 Token 提取策略，按优先级尝试 |
| **模板方法** | `auto_save_turn()` | 固定流程（保存用户→保存AI→累加Token），细节可重写 |
| **懒初始化** | `ChatEngine._get_llm()` | 延迟创建 LLM 实例，模型切换时失效重建 |
| **异步生成器** | `chat_stream()` | `AsyncIterator` 模式，逐 token yield |

---

## 6. 存储后端设计

### 6.1 接口定义

`StorageBackend` 抽象基类定义 22 个方法：

| 实体 | 方法 | 数量 |
|------|------|------|
| User | `create_user` / `get_user` / `get_user_by_username` / `list_users` / `update_user` / `delete_user` | 6 |
| Session | `create_session` / `get_session` / `list_sessions_by_user` / `update_session` / `delete_session` | 5 |
| Message | `add_message` / `list_messages_by_session` / `search_messages` | 3 |
| Preset | `create_preset` / `get_preset` / `list_presets` / `update_preset` / `delete_preset` | 5 |
| UserConfig | `set_user_config` / `get_user_config` / `get_all_user_configs` / `delete_user_config` | 4 |
| 生命周期 | `initialize` / `close` | 2 |

### 6.2 后端对比

| 特性 | SQLite | MySQL | File |
|------|--------|-------|------|
| 连接方式 | `aiosqlite.connect()` | `aiomysql.create_pool()` | 文件系统（`asyncio.to_thread`） |
| 并发控制 | 写锁（`_write_lock`） | 连接池 + 事务 | `asyncio.Lock` |
| 约束 | FOREIGN KEY + UNIQUE | FOREIGN KEY + UNIQUE | 代码手动校验 |
| 级联删除 | `ON DELETE CASCADE` | `ON DELETE CASCADE` | 代码手动实现 |
| 索引 | 自动（PRIMARY KEY） | 自动 + 手动 | 无（全量扫描） |
| 事务 | SQLite 事务 | MySQL 事务 | 无（非原子） |
| 适用规模 | 小（单文件） | 大（GB+ 级） | 小（数据量可控） |
| 可读性 | 需 SQL 客户端 | 需 SQL 客户端 | 直接用文本编辑器 |

### 6.3 File 后端数据布局

```
data/file_storage/
├── users.json              # {"user_id": {...}, ...}
├── sessions.json           # {"session_id": {...}, ...}
├── presets.json            # {"preset_id": {...}, ...}
├── user_configs.json       # {"user_id": {"key": "value", ...}, ...}
└── messages/
    └── {session_id}.json   # [{...}, {...}, ...]
```

---

## 7. 配置管理设计

### 配置优先级

```
环境变量 (os.environ)           ← 最高优先级
    ↑ 覆盖
config.{env}.yaml (环境特定)    ← 中间层
    ↑ 覆盖
config.yaml (基础配置)          ← 基础层
    ↑ 回退
代码默认值                       ← 最低优先级
```

### 敏感信息分离

| 存储位置 | 内容 | 是否入 Git |
|----------|------|------------|
| `.env` / `.env.{env}` | API Key、数据库密码 | ❌ `.gitignore` |
| `config.yaml` | 模型列表、存储类型、超时 | ✅ |
| `config/logging.yaml` | 日志级别、轮转策略 | ✅ |
| `config/presets.yaml` | 系统内置角色定义 | ✅ |
| `.env.example` | 环境变量模板（无实际值） | ✅ |

---

## 8. 异常处理策略

### 异常层次

```
ChatEngineError (base)
├── ConfigError       — API Key 缺失、配置不合法 → 阻止调用
└── LLMCallError      — 网络错误、超时 → 已自动重试后仍失败
```

### 各层策略

| 层 | 策略 |
|------|------|
| **存储层** | 抛出 `ValueError`（不合法操作）、`RuntimeError`（连接失败） |
| **业务层** | 捕获存储层异常，转换为业务语义异常（如 `ConfigError`） |
| **TUI 层** | 捕获所有异常，显示用户友好提示，不崩溃 |
| **入口层** | 记录全部未捕获异常到日志，优雅退出 |

### 重试机制

LLM 调用通过 `ChatOpenAI(max_retries=3, timeout=60)` 内置重试：
- 超时：60 秒后抛出 `LLMCallError`
- 重试：网络瞬时故障自动重试最多 3 次
- 回滚：调用失败时自动回滚用户消息，保持历史清洁

---

## 9. 扩展点设计

### 9.1 UI 层扩展

`AbstractUI` 定义了 UI 与业务层的完整协议。新增 UI 类型只需：

1. 创建新类继承 `AbstractUI`
2. 实现全部抽象方法
3. 在 `main.py` 中切换实例化

```
当前: TUIApp (ui/tui/app.py) → Rich + prompt_toolkit
未来: WebUIApp (ui/web/) → FastAPI + WebSocket
未来: APIApp → FastAPI REST API
```

### 9.2 存储后端扩展

新增存储后端只需：

1. 创建新类继承 `StorageBackend`，实现 22 个方法
2. 在 `StorageFactory._SUPPORTED_BACKENDS` 中注册
3. 在 `StorageFactory.create()` 中添加分支

```python
# 示例：添加 PostgreSQL 后端
class PostgresBackend(StorageBackend):
    ...

# factory.py
_SUPPORTED_BACKENDS = {"sqlite", "mysql", "file", "postgres"}
```

### 9.3 功能扩展预留

在 `ui_protocol.py` 中预留了以下接口：

| 接口 | 功能 | 状态 |
|------|------|------|
| `compare_models()` | 多模型并行对比 | 🔮 预留 |
| `upload_image()` | 图文理解（视觉模型） | 🔮 预留 |
| `start_voice_input()` / `stop_voice_input()` | 语音转文字输入 | 🔮 预留 |
| `register_tool()` / `list_tools()` | Tool Calling 工具注册 | 🔮 预留 |
| `enable_debug_panel()` | 调试面板（Token/延迟/上下文可视化） | 🔮 预留 |

### 9.4 配置扩展

- **多环境**：`APP_ENV=dev/test/prod` → 自动加载对应 `.env.{env}` + `config.{env}.yaml`（Step 15）
- **多租户**：当前用户隔离已支持，多组织可通过扩展 `User` 模型 + `org_id` 实现
- **插件系统**：预设管理已支持动态加载，可扩展为热加载 YAML/JSON 预设文件

---

## 10. 决策记录

### ADR-001: 全链路异步

**决定**：所有 IO 操作使用 `async/await`。

**理由**：
- LLM 流式调用天然异步
- 避免同步文件/数据库 IO 阻塞事件循环
- `aiosqlite`/`aiomysql`/`asyncio.to_thread` 提供异步支持

**代价**：所有调用链必须异步，同步业务逻辑需额外适配。

### ADR-002: 共享 state 字典而非事件总线

**决定**：TUI 视图通过 `state: Dict[str, Any]` 通信。

**理由**：
- 视图数量有限（MenuView + ChatView），事件总线过度设计
- 字典读写直观，类型提示友好
- 无回调地狱

**代价**：写入无强制校验，依赖约定而非类型系统。

### ADR-003: File 后端使用代码校验而非引入 SQLite 依赖

**决定**：File 后端在代码中手动实现唯一性检查和级联删除。

**理由**：
- 保持 File 后端的零依赖特性
- 数据量可控（单用户 < 1000 会话），性能不构成瓶颈
- 代码可读性好，适合教学

**代价**：非原子操作，极端场景下可能出现不一致。

### ADR-004: 使用 ChatOpenAI 而非直接 HTTP 调用

**决定**：通过 `langchain-openai` 的 `ChatOpenAI` 调用 LLM。

**理由**：
- 兼容所有 OpenAI API 格式的提供商
- 内置 `max_retries`/`timeout` 处理
- LangChain 生态无缝对接（Memory、Chain 等）

**代价**：引入了 LangChain 依赖链，版本升级可能带来 break change。

### ADR-005: pytest 共享 fixtures 用 SQLite + File 双后端测试

**决定**：核心测试同时验证 SQLite 和 File 后端。

**理由**：
- 两种后端实现独立，需分别验证
- MySQL 需要外部服务，不适合 CI 环境
- File 后端可作为 SQLite 的轻量替代

**代价**：File 后端测试增加 ~20s 执行时间。
