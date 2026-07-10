"""
会话管理器 — 会话生命周期管理（创建/加载/保存/标题生成）。

本模块负责会话级的业务逻辑：
1. 自动创建会话（首次进入对话时）
2. 每轮对话后自动保存消息到数据库
3. 首条消息自动生成会话标题
4. 加载历史会话的消息记录
5. 更新会话的 Token 累计统计
6. 新建会话（清空上下文重新开始）

职责边界：
- SessionManager：会话的 CRUD 和持久化
- ChatEngine：LLM 调用和内存中的消息历史
- ChatView：TUI 界面渲染和用户交互

设计原则：
- 与 UserManager / PresetManager 风格一致，通过 state 字典通信
- 所有数据库操作通过 StorageBackend 接口，不直接耦合 SQLite
- Token 统计由 ChatEngine 提供，SessionManager 负责持久化

使用方式：
    session_mgr = SessionManager(storage, state, config)
    session = await session_mgr.get_or_create_session(user_id, model)
    await session_mgr.auto_save_turn(session_id, user_msg, ai_msg, tokens)
"""

from typing import Any, Dict, List, Optional

from src.storage.base import StorageBackend


class SessionManager:
    """会话管理器 — 封装会话生命周期的全部业务逻辑。

    在存储层的基础上叠加：
    - 会话自动创建（懒初始化）
    - 消息自动持久化
    - 标题自动生成
    - Token 累计更新

    Attributes:
        _storage: 存储后端实例
        _state: 应用全局状态字典
        _config: ConfigManager 实例
    """

    def __init__(
        self,
        storage: StorageBackend,
        state: Dict[str, Any],
        config: Any,
    ) -> None:
        """初始化会话管理器。

        Args:
            storage: 已初始化的存储后端实例
            state: 应用全局状态字典
            config: ConfigManager 实例
        """
        self._storage = storage
        self._state = state
        self._config = config

    # ============================================================
    # 会话创建与获取
    # ============================================================

    async def get_or_create_session(
        self,
        user_id: str,
        model_name: Optional[str] = None,
        preset_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取当前会话，不存在则自动创建。

        优先级：
        1. 如果 state 中已有 current_session_id，验证其存在后返回
        2. 否则创建新会话

        Args:
            user_id: 所属用户 ID
            model_name: 使用的模型名称（默认从 config 读取）
            preset_id: 使用的预设 ID（可选）

        Returns:
            Session 数据字典
        """
        if model_name is None:
            model_name = self._config.model_name

        # 尝试使用已有会话
        existing_id = self._state.get("current_session_id")
        if existing_id:
            session = await self._storage.get_session(existing_id)
            if session is not None:
                return session

        # 创建新会话
        session = await self._storage.create_session(
            user_id=user_id,
            title="新会话",
            model_name=model_name,
            preset_id=preset_id,
        )

        # 更新全局状态
        self._state["current_session_id"] = session["id"]
        self._state["current_session_title"] = session["title"]

        return session

    async def create_new_session(
        self,
        user_id: str,
        model_name: Optional[str] = None,
        preset_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """强制创建新会话（不清空旧会话数据，只是开始新的）。

        旧会话保留在数据库中，可通过会话列表随时加载。

        Args:
            user_id: 所属用户 ID
            model_name: 使用的模型名称
            preset_id: 使用的预设 ID（可选）

        Returns:
            新创建的 Session 数据字典
        """
        if model_name is None:
            model_name = self._config.model_name

        session = await self._storage.create_session(
            user_id=user_id,
            title="新会话",
            model_name=model_name,
            preset_id=preset_id,
        )

        self._state["current_session_id"] = session["id"]
        self._state["current_session_title"] = session["title"]

        return session

    # ============================================================
    # 消息保存
    # ============================================================

    async def save_user_message(
        self,
        session_id: str,
        content: str,
    ) -> Dict[str, Any]:
        """保存用户消息到数据库。

        Args:
            session_id: 所属会话 ID
            content: 用户输入文本

        Returns:
            Message 数据字典
        """
        return await self._storage.add_message(
            session_id=session_id,
            role="human",
            content=content,
            prompt_tokens=0,
            completion_tokens=0,
        )

    async def save_ai_message(
        self,
        session_id: str,
        content: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> Dict[str, Any]:
        """保存 AI 回复消息到数据库。

        Args:
            session_id: 所属会话 ID
            content: AI 回复文本
            prompt_tokens: 本轮 prompt token 消耗
            completion_tokens: 本轮 completion token 消耗

        Returns:
            Message 数据字典
        """
        return await self._storage.add_message(
            session_id=session_id,
            role="ai",
            content=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    async def auto_save_turn(
        self,
        session_id: str,
        user_message: str,
        ai_response: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        """完整保存一轮对话（用户消息 + AI 回复），并更新会话 Token 累计。

        这是一个便捷方法，等价于依次调用：
        1. save_user_message()
        2. save_ai_message()
        3. _accumulate_tokens()

        Args:
            session_id: 所属会话 ID
            user_message: 用户输入文本
            ai_response: AI 回复文本
            prompt_tokens: 本轮 prompt token 消耗
            completion_tokens: 本轮 completion token 消耗
        """
        # 保存用户消息
        await self.save_user_message(session_id, user_message)

        # 保存 AI 回复
        await self.save_ai_message(
            session_id, ai_response,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

        # 更新会话 Token 累计
        if prompt_tokens > 0 or completion_tokens > 0:
            await self._accumulate_tokens(session_id, prompt_tokens, completion_tokens)

    async def _accumulate_tokens(
        self,
        session_id: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        """累加会话的 Token 计数。

        从数据库读取当前累计值，加上本轮消耗后写回。

        Args:
            session_id: 会话 ID
            prompt_tokens: 本轮 prompt token 增量
            completion_tokens: 本轮 completion token 增量
        """
        session = await self._storage.get_session(session_id)
        if session is None:
            return

        new_prompt = session.get("total_prompt_tokens", 0) + prompt_tokens
        new_completion = session.get("total_completion_tokens", 0) + completion_tokens

        await self._storage.update_session(
            session_id,
            total_prompt_tokens=new_prompt,
            total_completion_tokens=new_completion,
        )

    # ============================================================
    # 标题自动生成
    # ============================================================

    async def auto_title(self, session_id: str, first_message: str) -> str:
        """从首条用户消息自动生成会话标题。

        规则：
        - 截取前 N 个字符（N 由 config.session.title_max_length 决定）
        - 超出部分用 "..." 替代
        - 去除换行符

        Args:
            session_id: 会话 ID
            first_message: 首条用户消息文本

        Returns:
            生成的标题字符串
        """
        max_len = self._config.session_title_max_length

        # 清理文本：去换行、去首尾空白
        cleaned = first_message.replace("\n", " ").replace("\r", " ").strip()

        if len(cleaned) <= max_len:
            title = cleaned
        else:
            title = cleaned[:max_len] + "..."

        # 更新数据库
        await self._storage.update_session(session_id, title=title)

        # 更新全局状态
        self._state["current_session_title"] = title

        return title

    # ============================================================
    # 消息历史
    # ============================================================

    async def load_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """加载会话的所有历史消息。

        Args:
            session_id: 会话 ID

        Returns:
            消息字典列表，按时间正序排列
        """
        return await self._storage.list_messages_by_session(session_id)

    # ============================================================
    # 会话信息
    # ============================================================

    async def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话详情。

        Args:
            session_id: 会话 ID

        Returns:
            Session 数据字典；不存在时返回 None
        """
        return await self._storage.get_session(session_id)

    async def get_total_tokens(self, session_id: str) -> Dict[str, int]:
        """获取会话的累计 Token 统计。

        Args:
            session_id: 会话 ID

        Returns:
            {"prompt": int, "completion": int, "total": int}
        """
        session = await self._storage.get_session(session_id)
        if session is None:
            return {"prompt": 0, "completion": 0, "total": 0}

        prompt = session.get("total_prompt_tokens", 0)
        completion = session.get("total_completion_tokens", 0)
        return {
            "prompt": prompt,
            "completion": completion,
            "total": prompt + completion,
        }

    # ============================================================
    # 会话列表与管理（Step 8）
    # ============================================================

    async def list_user_sessions(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """列出用户的所有会话。

        按更新时间倒序排列，最近活跃的会话在前。

        Args:
            user_id: 用户 ID
            limit: 每页数量上限
            offset: 分页偏移量

        Returns:
            Session 数据字典列表
        """
        return await self._storage.list_sessions_by_user(user_id, limit, offset)

    async def rename_session(
        self,
        session_id: str,
        new_title: str,
    ) -> Dict[str, Any]:
        """重命名会话。

        更新数据库中的会话标题，如果该会话是当前活跃会话，
        同步更新全局状态中的标题。

        Args:
            session_id: 会话 ID
            new_title: 新标题

        Returns:
            更新后的 Session 数据字典

        Raises:
            ValueError: 会话不存在
        """
        session = await self._storage.update_session(session_id, title=new_title)

        # 如果是当前会话，同步更新状态
        if session_id == self._state.get("current_session_id"):
            self._state["current_session_title"] = new_title

        return session

    async def delete_session(self, session_id: str) -> bool:
        """删除会话及其所有关联消息。

        如果删除的是当前活跃会话，自动清除状态。
        CASCADE 会自动删除该会话下的所有消息。

        Args:
            session_id: 会话 ID

        Returns:
            True 表示删除成功；会话不存在返回 False
        """
        success = await self._storage.delete_session(session_id)

        if success and session_id == self._state.get("current_session_id"):
            self.clear_current_session()

        return success

    def switch_to_session(self, session: Dict[str, Any]) -> None:
        """切换到指定会话（仅更新状态，不操作数据库）。

        将目标会话设为当前活跃会话，后续 get_or_create_session()
        会验证并加载该会话。

        Args:
            session: 目标 Session 数据字典
        """
        self._state["current_session_id"] = session["id"]
        self._state["current_session_title"] = session.get("title", "新会话")

    # ============================================================
    # 会话导出（Step 10）
    # ============================================================

    async def export_session(
        self,
        session_id: str,
        username: str,
    ) -> str:
        """导出会话为 Markdown 文件。

        将指定会话的全部消息格式化为易读的 Markdown 文档，
        包含会话元信息（标题、模型、时间、消息数），
        按时间正序排列所有消息。

        Args:
            session_id: 会话 ID
            username: 用户名（用于路径模板中 {username} 占位符）

        Returns:
            导出文件的绝对路径

        Raises:
            ValueError: 会话不存在
        """
        import os
        from datetime import date

        # 1. 获取会话信息
        session = await self._storage.get_session(session_id)
        if session is None:
            raise ValueError(f"会话不存在: {session_id}")

        # 2. 获取所有消息
        messages = await self._storage.list_messages_by_session(session_id)

        # 3. 构建 Markdown 内容
        title = session.get("title", "新会话")
        model = session.get("model_name", "unknown")
        created = session.get("created_at", "")
        today = date.today().strftime("%Y-%m-%d")

        md_lines: List[str] = []
        md_lines.append(f"# {title}")
        md_lines.append("")
        md_lines.append(f"- **模型**: {model}")
        md_lines.append(f"- **导出日期**: {today}")
        md_lines.append(f"- **创建时间**: {created}")
        md_lines.append(f"- **消息数**: {len(messages)}")
        md_lines.append("")
        md_lines.append("---")
        md_lines.append("")

        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            msg_time = msg.get("created_at", "")

            if role == "human":
                md_lines.append("### 👤 用户")
            elif role == "ai":
                md_lines.append("### 🤖 AI")
            elif role == "system":
                md_lines.append("### ⚙️ 系统")
            else:
                md_lines.append(f"### {role}")

            md_lines.append("")
            md_lines.append(content)
            md_lines.append("")
            if msg_time:
                md_lines.append(f"*{msg_time}*")
            md_lines.append("")
            md_lines.append("---")
            md_lines.append("")

        md_content = "\n".join(md_lines)

        # 4. 构建文件路径（清理文件名中的非法字符）
        path_template = self._config.export_path_template
        safe_title = "".join(
            c if c.isalnum() or c in "_- " else "_" for c in title
        )[:50]
        safe_title = safe_title.strip().replace(" ", "_")
        if not safe_title:
            safe_title = "untitled"

        file_path = path_template.format(
            username=username,
            session_title=safe_title,
            date=today,
        )

        # 5. 确保目录存在并写入文件
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        return os.path.abspath(file_path)

    # ============================================================
    # 消息搜索（Step 9）
    # ============================================================

    async def search_messages(
        self,
        user_id: str,
        keyword: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """在用户的所有会话中搜索包含关键词的消息。

        使用 SQL LIKE 进行模糊匹配，搜索范围限定在当前用户的
        所有会话中。每条结果附带所属会话标题，方便定位上下文。

        Args:
            user_id: 用户 ID（限定搜索范围）
            keyword: 搜索关键词
            limit: 返回数量上限

        Returns:
            匹配的消息列表，每条消息附带 session_title 字段
        """
        return await self._storage.search_messages(user_id, keyword, limit)

    # ============================================================
    # 状态清理
    # ============================================================

    def clear_current_session(self) -> None:
        """清除当前会话状态（不删除数据库记录）。

        用于"新建会话"或"返回主菜单"时清理状态。
        """
        self._state["current_session_id"] = None
        self._state["current_session_title"] = None
