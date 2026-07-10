# -*- coding: utf-8 -*-
"""Step 8: Session Management - Test Suite."""

import sys, os, asyncio, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Any, Dict, List

_test_passed = 0
_test_failed = 0
_test_errors: List[str] = []

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


# ============ Test 1: SessionManager new methods ============

async def test1_session_manager_methods():
    section("1. SessionManager: list/rename/delete/switch")

    from src.storage.sqlite_backend import SQLiteBackend
    from src.core.session_manager import SessionManager
    from src.core.config_manager import ConfigManager

    db_path = tempfile.mktemp(suffix='.db')
    try:
        backend = SQLiteBackend(db_path)
        await backend.initialize()
        config = ConfigManager()
        state = {
            'current_user_id': None, 'current_session_id': None,
            'current_session_title': None, 'current_model': config.model_name,
            'config': config,
        }
        sm = SessionManager(backend, state, config)
        state['session_manager'] = sm

        user = await backend.create_user('u1', default_model='deepseek-v4-flash')
        uid = user['id']

        s1 = await backend.create_session(uid, 'Session-A', 'deepseek-v4-flash')
        s2 = await backend.create_session(uid, 'Session-B', 'kimi 2.6')
        s3 = await backend.create_session(uid, 'Session-C', 'qwen-plus')

        # list_user_sessions
        sessions = await sm.list_user_sessions(uid)
        check(len(sessions) == 3, f'list_user_sessions returns 3 (got {len(sessions)})')
        check(sessions[0]['title'] == 'Session-C', f'newest first (got {sessions[0]["title"]})')

        # switch_to_session
        sm.switch_to_session(s1)
        check(state['current_session_id'] == s1['id'], 'switch_to_session sets id')
        check(state['current_session_title'] == s1['title'], 'switch_to_session sets title')

        # rename_session
        updated = await sm.rename_session(s2['id'], 'Renamed-B')
        check(updated['title'] == 'Renamed-B', f'rename returns new title (got {updated["title"]})')
        s2f = await backend.get_session(s2['id'])
        check(s2f['title'] == 'Renamed-B', 'DB title also updated')

        # rename current session syncs state
        sm.switch_to_session(s3)
        await sm.rename_session(s3['id'], 'Current-Renamed')
        check(state['current_session_title'] == 'Current-Renamed',
              f'rename current syncs state (got {state["current_session_title"]})')

        # delete_session
        success = await sm.delete_session(s2['id'])
        check(success is True, 'delete_session returns True')
        remaining = await backend.list_sessions_by_user(uid)
        check(len(remaining) == 2, f'2 remaining after delete (got {len(remaining)})')

        # delete current session clears state
        sm.switch_to_session(s1)
        await sm.delete_session(s1['id'])
        check(state['current_session_id'] is None, 'deleting current clears session_id')
        check(state['current_session_title'] is None, 'deleting current clears session_title')

        # delete nonexistent
        success = await sm.delete_session('nonexistent-id')
        check(success is False, 'deleting nonexistent returns False')

        # switch + get_or_create
        sm.switch_to_session(s3)
        sess = await sm.get_or_create_session(uid)
        check(sess['id'] == s3['id'], 'switch then get_or_create returns same session')

        # create_new_session preserves old
        new_s = await sm.create_new_session(uid)
        check(new_s['id'] != s3['id'], 'create_new_session creates new id')
        all_s = await backend.list_sessions_by_user(uid)
        check(len(all_s) == 2, f'old session preserved, 2 total (got {len(all_s)})')

        await backend.close()
    finally:
        try: os.remove(db_path)
        except OSError: pass


# ============ Test 2: Edge cases ============

async def test2_edge_cases():
    section("2. Edge Cases")

    from src.storage.sqlite_backend import SQLiteBackend
    from src.core.session_manager import SessionManager
    from src.core.config_manager import ConfigManager

    db_path = tempfile.mktemp(suffix='.db')
    try:
        backend = SQLiteBackend(db_path)
        await backend.initialize()
        config = ConfigManager()
        state = {
            'current_user_id': 'u2', 'current_session_id': None,
            'current_session_title': None, 'config': config,
        }
        sm = SessionManager(backend, state, config)

        user = await backend.create_user('edge_user', default_model='deepseek-v4-flash')
        sessions = await sm.list_user_sessions(user['id'])
        check(len(sessions) == 0, f'empty list for new user (got {len(sessions)})')

        try:
            await sm.rename_session('nonexistent', 'test')
            check(False, 'rename nonexistent should raise ValueError')
        except ValueError:
            check(True, 'rename nonexistent raises ValueError')

        sm.clear_current_session()
        check(state['current_session_id'] is None, 'clear clears id')
        check(state['current_session_title'] is None, 'clear clears title')

        await backend.close()
    finally:
        try: os.remove(db_path)
        except OSError: pass


# ============ Test 3: Token accumulation ============

async def test3_token_accumulation():
    section("3. Token Accumulation Regression")

    from src.storage.sqlite_backend import SQLiteBackend
    from src.core.session_manager import SessionManager
    from src.core.config_manager import ConfigManager

    db_path = tempfile.mktemp(suffix='.db')
    try:
        backend = SQLiteBackend(db_path)
        await backend.initialize()
        config = ConfigManager()
        state = {
            'current_user_id': None, 'current_session_id': None,
            'current_session_title': None, 'config': config,
        }
        sm = SessionManager(backend, state, config)

        user = await backend.create_user('tokens', default_model='deepseek-v4-flash')
        state['current_user_id'] = user['id']
        session = await sm.get_or_create_session(user['id'])

        await sm.auto_save_turn(session['id'], 'Q1', 'A1', prompt_tokens=100, completion_tokens=50)
        await sm.auto_save_turn(session['id'], 'Q2', 'A2', prompt_tokens=80, completion_tokens=40)

        tokens = await sm.get_total_tokens(session['id'])
        check(tokens['prompt'] == 180, f'prompt=180 (got {tokens["prompt"]})')
        check(tokens['completion'] == 90, f'completion=90 (got {tokens["completion"]})')
        check(tokens['total'] == 270, f'total=270 (got {tokens["total"]})')

        await sm.auto_save_turn(session['id'], 'Q3', 'A3')
        tokens = await sm.get_total_tokens(session['id'])
        check(tokens['total'] == 270, f'zero-token turn does NOT accumulate (got {tokens["total"]})')

        await backend.close()
    finally:
        try: os.remove(db_path)
        except OSError: pass


# ============ Test 4: ChatEngine integration ============

async def test4_chat_engine_integration():
    section("4. ChatEngine Message Load Integration")

    from src.storage.sqlite_backend import SQLiteBackend
    from src.core.session_manager import SessionManager
    from src.core.chat_engine import ChatEngine
    from src.core.config_manager import ConfigManager

    db_path = tempfile.mktemp(suffix='.db')
    try:
        backend = SQLiteBackend(db_path)
        await backend.initialize()
        config = ConfigManager()
        state = {'current_user_id': None, 'config': config}
        sm = SessionManager(backend, state, config)

        user = await backend.create_user('chat_user', default_model='deepseek-v4-flash')
        state['current_user_id'] = user['id']
        session = await backend.create_session(user['id'], 'History Session', 'deepseek-v4-flash')
        await backend.add_message(session['id'], 'human', '1+1=?', 0, 0)
        await backend.add_message(session['id'], 'ai', '=2', 5, 3)
        await backend.add_message(session['id'], 'human', '2+2=?', 0, 0)
        await backend.add_message(session['id'], 'ai', '=4', 5, 3)

        messages = await sm.load_messages(session['id'])
        check(len(messages) == 4, f'load 4 messages (got {len(messages)})')
        check(messages[0]['role'] == 'human' and messages[0]['content'] == '1+1=?', 'msg1: human 1+1=?')
        check(messages[1]['role'] == 'ai' and messages[1]['content'] == '=2', 'msg2: ai =2')
        check(messages[3]['content'] == '=4', 'msg4: =4')

        engine = ChatEngine(config, state)
        engine.load_history(messages)
        check(engine.message_count == 4, f'ChatEngine message_count=4 (got {engine.message_count})')

        await backend.close()
    finally:
        try: os.remove(db_path)
        except OSError: pass


# ============ Main ============

async def main():
    print("=" * 60)
    print("  Step 8: Session Management - Test Suite")
    print("=" * 60)

    await test1_session_manager_methods()
    await test2_edge_cases()
    await test3_token_accumulation()
    await test4_chat_engine_integration()

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
