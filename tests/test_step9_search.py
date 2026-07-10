# -*- coding: utf-8 -*-
"""Step 9: Message Search - Test Suite."""

import sys, os, asyncio, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Any

_test_passed = 0
_test_failed = 0
_test_errors = []

def check(condition: Any, message: str) -> bool:
    global _test_passed, _test_failed
    if condition:
        _test_passed += 1
        print(f"  PASS {message}")
        return True
    else:
        _test_failed += 1
        msg = f"  FAIL {message}"
        print(msg)
        _test_errors.append(msg)
        return False

def section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ============ Test 1: Basic search ============

async def test1_basic_search():
    section("1. Basic keyword search across sessions")

    from src.storage.sqlite_backend import SQLiteBackend
    from src.core.session_manager import SessionManager
    from src.core.config_manager import ConfigManager

    db_path = tempfile.mktemp(suffix='.db')
    try:
        backend = SQLiteBackend(db_path)
        await backend.initialize()
        config = ConfigManager()
        state = {'current_user_id': None, 'config': config}
        sm = SessionManager(backend, state, config)

        user = await backend.create_user('search_user', default_model='deepseek-v4-flash')
        uid = user['id']

        # Create sessions with messages
        s1 = await backend.create_session(uid, 'Python学习', 'deepseek-v4-flash')
        await backend.add_message(s1['id'], 'human', '如何用Python读取CSV文件？', 0, 0)
        await backend.add_message(s1['id'], 'ai', '可以使用pandas.read_csv()方法', 5, 3)

        s2 = await backend.create_session(uid, '算法讨论', 'kimi 2.6')
        await backend.add_message(s2['id'], 'human', 'Python实现快速排序', 0, 0)
        await backend.add_message(s2['id'], 'ai', '以下是Python代码实现...', 8, 5)

        s3 = await backend.create_session(uid, '日常聊天', 'qwen-plus')
        await backend.add_message(s3['id'], 'human', '今天天气真好', 0, 0)
        await backend.add_message(s3['id'], 'ai', '是的，适合出门走走', 3, 2)

        # Search for "Python"
        results = await sm.search_messages(uid, 'Python')
        check(len(results) == 3, f'"Python" matches 3 messages (got {len(results)})')

        # Each result should have session_title
        for r in results:
            check('session_title' in r, f'message has session_title (value: {r.get("session_title")})')

        # Search for "CSV" — SQLite LIKE is case-insensitive for ASCII,
        # so "CSV" also matches "pandas.read_csv()" in the AI reply
        results = await sm.search_messages(uid, 'CSV')
        check(len(results) == 2, f'"CSV" matches 2 messages (case-insensitive) (got {len(results)})')
        # Both should belong to the same session
        for r in results:
            check(r['session_title'] == 'Python学习',
                  f'CSV match belongs to Python学习 (got {r["session_title"]})')

        # Search for nonexistent keyword
        results = await sm.search_messages(uid, 'ZZZNOTEXIST')
        check(len(results) == 0, f'nonexistent keyword returns 0 results (got {len(results)})')

        # Search should only return messages from THIS user
        user2 = await backend.create_user('other_user', default_model='deepseek-v4-flash')
        s4 = await backend.create_session(user2['id'], 'Other Python', 'deepseek-v4-flash')
        await backend.add_message(s4['id'], 'human', 'Python入门教程', 0, 0)

        # Search for user1 should NOT include user2's messages
        results = await sm.search_messages(uid, '入门')
        check(len(results) == 0, f'user1 search for "入门" returns 0 (user2 data isolated)')

        await backend.close()
    finally:
        try: os.remove(db_path)
        except OSError: pass


# ============ Test 2: Search result order and details ============

async def test2_search_order_and_details():
    section("2. Search result ordering and field completeness")

    from src.storage.sqlite_backend import SQLiteBackend
    from src.core.session_manager import SessionManager
    from src.core.config_manager import ConfigManager

    db_path = tempfile.mktemp(suffix='.db')
    try:
        backend = SQLiteBackend(db_path)
        await backend.initialize()
        config = ConfigManager()
        state = {'current_user_id': None, 'config': config}
        sm = SessionManager(backend, state, config)

        user = await backend.create_user('order_test', default_model='deepseek-v4-flash')
        uid = user['id']

        s = await backend.create_session(uid, '测试会话', 'deepseek-v4-flash')

        # Add messages at different times
        import asyncio as aio
        await backend.add_message(s['id'], 'human', '第一轮：LangChain介绍', 0, 0)
        await aio.sleep(0.1)
        await backend.add_message(s['id'], 'ai', 'LangChain是LLM应用框架', 5, 3)
        await aio.sleep(0.1)
        await backend.add_message(s['id'], 'human', '第二轮：LangChain的Chain用法', 0, 0)
        await aio.sleep(0.1)
        await backend.add_message(s['id'], 'ai', 'Chain可以串联多个步骤', 5, 3)

        # Search for "LangChain" - should find 3 messages (not "Chain可以串联...")
        results = await sm.search_messages(uid, 'LangChain')
        check(len(results) == 3, f'"LangChain" matches 3 messages (got {len(results)})')

        # Results should be ordered by created_at DESC (newest first)
        if len(results) >= 2:
            from datetime import datetime
            t0 = results[0].get('created_at')
            t1 = results[1].get('created_at')
            if isinstance(t0, str): t0 = datetime.fromisoformat(t0)
            if isinstance(t1, str): t1 = datetime.fromisoformat(t1)
            check(t0 >= t1, 'results ordered newest-first')

        # Each result must have all required fields
        required_fields = ['id', 'session_id', 'role', 'content', 'session_title', 'created_at']
        for r in results:
            for field in required_fields:
                check(field in r, f'result has field "{field}"')
            check(r['content'] != '', 'content is non-empty')

        # Search for "Chain" (case-insensitive LIKE)
        results = await sm.search_messages(uid, 'Chain')
        check(len(results) == 4, f'"Chain" matches 4 messages (includes those with LangChain) (got {len(results)})')

        await backend.close()
    finally:
        try: os.remove(db_path)
        except OSError: pass


# ============ Test 3: Search with special characters ============

async def test3_search_special_chars():
    section("3. Search with special characters and edge cases")

    from src.storage.sqlite_backend import SQLiteBackend
    from src.core.session_manager import SessionManager
    from src.core.config_manager import ConfigManager

    db_path = tempfile.mktemp(suffix='.db')
    try:
        backend = SQLiteBackend(db_path)
        await backend.initialize()
        config = ConfigManager()
        state = {'current_user_id': None, 'config': config}
        sm = SessionManager(backend, state, config)

        user = await backend.create_user('special_user', default_model='deepseek-v4-flash')
        uid = user['id']

        s = await backend.create_session(uid, 'Special Chars', 'deepseek-v4-flash')
        await backend.add_message(s['id'], 'human', '代码: print("hello world")', 0, 0)
        await backend.add_message(s['id'], 'ai', '输出: hello world 你好世界', 5, 3)
        await backend.add_message(s['id'], 'human', '网址: https://example.com/path?q=1', 0, 0)

        # Search Chinese
        results = await sm.search_messages(uid, '你好')
        check(len(results) == 1, f'Chinese search works (got {len(results)})')

        # Search with parentheses
        results = await sm.search_messages(uid, 'hello')
        check(len(results) == 2, f'"hello" matches 2 msgs (got {len(results)})')

        # Search URL fragment
        results = await sm.search_messages(uid, 'example')
        check(len(results) == 1, f'URL fragment search works (got {len(results)})')

        # Search code fragment
        results = await sm.search_messages(uid, 'print')
        check(len(results) == 1, f'code fragment search works (got {len(results)})')

        await backend.close()
    finally:
        try: os.remove(db_path)
        except OSError: pass


# ============ Test 4: limit parameter ============

async def test4_search_limit():
    section("4. Search result limit")

    from src.storage.sqlite_backend import SQLiteBackend
    from src.core.session_manager import SessionManager
    from src.core.config_manager import ConfigManager

    db_path = tempfile.mktemp(suffix='.db')
    try:
        backend = SQLiteBackend(db_path)
        await backend.initialize()
        config = ConfigManager()
        state = {'current_user_id': None, 'config': config}
        sm = SessionManager(backend, state, config)

        user = await backend.create_user('limit_test', default_model='deepseek-v4-flash')
        uid = user['id']

        s = await backend.create_session(uid, 'Test', 'deepseek-v4-flash')
        # Add 10 messages all containing "test"
        for i in range(10):
            await backend.add_message(s['id'], 'human', f'test message {i}', 0, 0)

        # Default limit = 50
        results = await sm.search_messages(uid, 'test')
        check(len(results) == 10, f'default limit returns all 10 (got {len(results)})')

        # Custom limit = 3
        results = await sm.search_messages(uid, 'test', limit=3)
        check(len(results) == 3, f'limit=3 returns 3 (got {len(results)})')

        await backend.close()
    finally:
        try: os.remove(db_path)
        except OSError: pass


# ============ Main ============

async def main():
    print("=" * 60)
    print("  Step 9: Message Search - Test Suite")
    print("=" * 60)

    await test1_basic_search()
    await test2_search_order_and_details()
    await test3_search_special_chars()
    await test4_search_limit()

    total = _test_passed + _test_failed
    print(f"\n{'='*60}")
    print(f"  RESULTS: {_test_passed}/{total} passed ({_test_failed} failed)")
    print(f"{'='*60}")

    if _test_failed > 0:
        print("\nFailures:")
        for err in _test_errors:
            print(f"  {err}")
        sys.exit(1)
    else:
        print("\nAll tests passed!")

if __name__ == '__main__':
    asyncio.run(main())
