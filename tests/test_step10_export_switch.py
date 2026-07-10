# -*- coding: utf-8 -*-
"""Step 10: Export + Model Switch - Test Suite."""

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


# ============ Part A: Markdown Export ============

async def test_export_basic():
    section("A1. Basic session export to Markdown")

    from src.storage.sqlite_backend import SQLiteBackend
    from src.core.session_manager import SessionManager
    from src.core.config_manager import ConfigManager

    db_path = tempfile.mktemp(suffix='.db')
    export_dir = tempfile.mkdtemp()
    try:
        backend = SQLiteBackend(db_path)
        await backend.initialize()
        config = ConfigManager()
        # Override export path template to use temp dir
        config._config['export'] = {
            'path_template': f'{export_dir}/{{username}}/{{session_title}}_{{date}}.md'
        }
        state = {'current_user_id': None, 'config': config}
        sm = SessionManager(backend, state, config)

        # Create user and session with messages
        user = await backend.create_user('export_user', default_model='deepseek-v4-flash')
        uid = user['id']
        s1 = await backend.create_session(uid, '测试会话', 'deepseek-v4-flash')
        await backend.add_message(s1['id'], 'human', '你好，请介绍一下Python', 0, 0)
        await backend.add_message(s1['id'], 'ai', 'Python是一种高级编程语言...', 10, 5)

        # Export
        file_path = await sm.export_session(s1['id'], 'export_user')
        check(os.path.exists(file_path), f'export file exists: {file_path}')
        check(file_path.startswith(export_dir), f'file in export dir')

        # Check content
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        check('# 测试会话' in content, 'export contains session title')
        check('deepseek-v4-flash' in content, 'export contains model name')
        check('你好，请介绍一下Python' in content, 'export contains user message')
        check('Python是一种高级编程语言' in content, 'export contains AI message')
        check('👤 用户' in content, 'export contains user role label')
        check('🤖 AI' in content, 'export contains AI role label')
        check('导出日期' in content, 'export contains export date')
        check('消息数' in content, 'export contains message count')

    finally:
        await backend.close()
        # Cleanup
        import shutil
        if os.path.exists(db_path):
            os.unlink(db_path)
        if os.path.exists(export_dir):
            shutil.rmtree(export_dir, ignore_errors=True)


async def test_export_empty_session():
    section("A2. Export empty session (no messages)")

    from src.storage.sqlite_backend import SQLiteBackend
    from src.core.session_manager import SessionManager
    from src.core.config_manager import ConfigManager

    db_path = tempfile.mktemp(suffix='.db')
    export_dir = tempfile.mkdtemp()
    try:
        backend = SQLiteBackend(db_path)
        await backend.initialize()
        config = ConfigManager()
        config._config['export'] = {
            'path_template': f'{export_dir}/{{username}}/{{session_title}}_{{date}}.md'
        }
        state = {'config': config}
        sm = SessionManager(backend, state, config)

        user = await backend.create_user('empty_user', default_model='qwen-plus')
        s1 = await backend.create_session(user['id'], '空会话', 'qwen-plus')

        file_path = await sm.export_session(s1['id'], 'empty_user')
        check(os.path.exists(file_path), f'empty session export exists')

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        check('# 空会话' in content, 'empty export contains title')
        check('消息数' in content, 'empty export contains 消息数 field')

    finally:
        await backend.close()
        import shutil
        if os.path.exists(db_path):
            os.unlink(db_path)
        if os.path.exists(export_dir):
            shutil.rmtree(export_dir, ignore_errors=True)


async def test_export_nonexistent_session():
    section("A3. Export non-existent session raises error")

    from src.storage.sqlite_backend import SQLiteBackend
    from src.core.session_manager import SessionManager
    from src.core.config_manager import ConfigManager

    db_path = tempfile.mktemp(suffix='.db')
    try:
        backend = SQLiteBackend(db_path)
        await backend.initialize()
        config = ConfigManager()
        state = {'config': config}
        sm = SessionManager(backend, state, config)

        try:
            await sm.export_session('nonexistent-id-12345', 'user')
            check(False, 'should have raised ValueError')
        except ValueError as e:
            check('不存在' in str(e), f'ValueError mentions 不存在: {e}')

    finally:
        await backend.close()
        if os.path.exists(db_path):
            os.unlink(db_path)


async def test_export_title_sanitization():
    section("A4. Export sanitizes special chars in filename")

    from src.storage.sqlite_backend import SQLiteBackend
    from src.core.session_manager import SessionManager
    from src.core.config_manager import ConfigManager

    db_path = tempfile.mktemp(suffix='.db')
    export_dir = tempfile.mkdtemp()
    try:
        backend = SQLiteBackend(db_path)
        await backend.initialize()
        config = ConfigManager()
        config._config['export'] = {
            'path_template': f'{export_dir}/{{username}}/{{session_title}}_{{date}}.md'
        }
        state = {'config': config}
        sm = SessionManager(backend, state, config)

        user = await backend.create_user('safe_user', default_model='deepseek-v4-flash')
        # Create session with special chars in title
        s1 = await backend.create_session(user['id'], '测试/模型:对比?', 'deepseek-v4-flash')

        file_path = await sm.export_session(s1['id'], 'safe_user')
        check(os.path.exists(file_path), f'sanitized filename exists: {os.path.basename(file_path)}')
        # The path should not contain special chars like / or :
        dir_part = os.path.dirname(file_path)
        file_part = os.path.basename(file_path)
        check('/' not in file_part, 'filename contains no slash')
        check(':' not in file_part, 'filename contains no colon')
        check('?' not in file_part, 'filename contains no question mark')

    finally:
        await backend.close()
        import shutil
        if os.path.exists(db_path):
            os.unlink(db_path)
        if os.path.exists(export_dir):
            shutil.rmtree(export_dir, ignore_errors=True)


async def test_export_multiline_messages():
    section("A5. Export handles multi-line messages")

    from src.storage.sqlite_backend import SQLiteBackend
    from src.core.session_manager import SessionManager
    from src.core.config_manager import ConfigManager

    db_path = tempfile.mktemp(suffix='.db')
    export_dir = tempfile.mkdtemp()
    try:
        backend = SQLiteBackend(db_path)
        await backend.initialize()
        config = ConfigManager()
        config._config['export'] = {
            'path_template': f'{export_dir}/{{username}}/{{session_title}}_{{date}}.md'
        }
        state = {'config': config}
        sm = SessionManager(backend, state, config)

        user = await backend.create_user('multi_user', default_model='kimi 2.6')
        s1 = await backend.create_session(user['id'], '多行消息', 'kimi 2.6')
        # Multi-line user message
        await backend.add_message(s1['id'], 'human',
            '第一行\n第二行\n第三行', 0, 0)
        await backend.add_message(s1['id'], 'ai',
            '回复第一段\n\n回复第二段\n```python\nprint("hello")\n```', 10, 8)

        file_path = await sm.export_session(s1['id'], 'multi_user')
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        check('第一行' in content and '第二行' in content and '第三行' in content,
              'multi-line user message preserved')
        check('print("hello")' in content, 'code block content preserved')

    finally:
        await backend.close()
        import shutil
        if os.path.exists(db_path):
            os.unlink(db_path)
        if os.path.exists(export_dir):
            shutil.rmtree(export_dir, ignore_errors=True)


# ============ Part B: Model Configuration ============

async def test_model_config_per_provider():
    section("B1. get_model_config returns per-model API credentials")

    from src.core.config_manager import ConfigManager
    import os

    # We test the logic directly — the config has per-model env_key + api_base_url
    config = ConfigManager()

    # DeepSeek model
    ds_cfg = config.get_model_config('deepseek-v4-flash')
    check('api_key' in ds_cfg, 'DeepSeek config has api_key')
    check('api_base' in ds_cfg, 'DeepSeek config has api_base')
    check(ds_cfg['api_base'] == 'https://api.deepseek.com/v1',
          f'DeepSeek base URL correct: {ds_cfg["api_base"]}')

    # Kimi model
    kimi_cfg = config.get_model_config('kimi 2.6')
    check('api_key' in kimi_cfg, 'Kimi config has api_key')
    check(kimi_cfg['api_base'] == 'https://api.moonshot.cn/v1',
          f'Kimi base URL correct: {kimi_cfg["api_base"]}')

    # Qwen model
    qwen_cfg = config.get_model_config('qwen-plus')
    check(qwen_cfg['api_base'] == 'https://dashscope.aliyuncs.com/compatible-mode/v1',
          f'Qwen base URL correct: {qwen_cfg["api_base"]}')


async def test_model_config_unknown_fallback():
    section("B2. Unknown model falls back to global defaults")

    from src.core.config_manager import ConfigManager

    config = ConfigManager()

    # Unknown model should use global fallbacks
    cfg = config.get_model_config('nonexistent-model-xyz')
    check('api_key' in cfg, 'unknown model config has api_key (fallback)')
    check('api_base' in cfg, 'unknown model config has api_base (fallback)')
    # Should match global defaults
    check(cfg['api_key'] == config.api_key,
          'unknown model api_key matches global api_key')
    check(cfg['api_base'] == config.api_base_url,
          'unknown model api_base matches global api_base_url')


async def test_available_models_list():
    section("B3. available_models list is populated")

    from src.core.config_manager import ConfigManager

    config = ConfigManager()
    models = config.available_models
    check(len(models) >= 3, f'at least 3 models configured (got {len(models)})')
    check(any(m['name'] == 'deepseek-v4-flash' for m in models),
          'deepseek-v4-flash in available_models')
    check(any(m['name'] == 'kimi 2.6' for m in models),
          'kimi 2.6 in available_models')
    check(any(m['name'] == 'qwen-plus' for m in models),
          'qwen-plus in available_models')

    # Each model should have required fields
    for m in models:
        check('name' in m, f'model {m.get("name", "?")} has name')
        check('provider' in m, f'model {m.get("name", "?")} has provider')
        check('env_key' in m, f'model {m.get("name", "?")} has env_key')
        check('api_base_url' in m, f'model {m.get("name", "?")} has api_base_url')


# ============ Part C: Model Switching State ============

async def test_state_model_switch():
    section("C1. State current_model updates on switch")

    from src.storage.sqlite_backend import SQLiteBackend
    from src.core.user_manager import UserManager

    db_path = tempfile.mktemp(suffix='.db')
    try:
        backend = SQLiteBackend(db_path)
        await backend.initialize()
        state = {
            'current_user_id': None,
            'current_username': None,
            'current_model': None,
        }
        um = UserManager(backend, state)

        # Create user with kimi as default model
        user = await um.create_user('model_user', default_model='kimi 2.6')
        um.set_current_user(user)

        check(state['current_model'] == 'kimi 2.6',
              f'state current_model set to kimi (got: {state["current_model"]})')

        # Simulate model switch via settings
        state['current_model'] = 'qwen-plus'
        check(state['current_model'] == 'qwen-plus',
              f'state current_model switched to qwen (got: {state["current_model"]})')

        state['current_model'] = 'deepseek-v4-flash'
        check(state['current_model'] == 'deepseek-v4-flash',
              f'state current_model switched to deepseek (got: {state["current_model"]})')

    finally:
        await backend.close()
        if os.path.exists(db_path):
            os.unlink(db_path)


async def test_clear_user_resets_model():
    section("C2. clear_current_user resets model state")

    from src.storage.sqlite_backend import SQLiteBackend
    from src.core.user_manager import UserManager

    db_path = tempfile.mktemp(suffix='.db')
    try:
        backend = SQLiteBackend(db_path)
        await backend.initialize()
        state = {
            'current_user_id': None,
            'current_username': None,
            'current_model': 'deepseek-v4-flash',
        }
        um = UserManager(backend, state)

        user = await um.create_user('temp_user', default_model='qwen-plus')
        um.set_current_user(user)
        check(state['current_model'] == 'qwen-plus', 'model set to qwen')

        um.clear_current_user()
        check(state['current_model'] is None,
              f'current_model cleared (got: {state["current_model"]})')
        check(state['current_user_id'] is None, 'user_id cleared')

    finally:
        await backend.close()
        if os.path.exists(db_path):
            os.unlink(db_path)


async def test_export_path_template_substitution():
    section("C3. Export path template substitution")

    from src.core.config_manager import ConfigManager

    config = ConfigManager()
    template = config.export_path_template
    check('{username}' in template, 'template has username placeholder')
    check('{session_title}' in template, 'template has session_title placeholder')
    check('{date}' in template, 'template has date placeholder')
    check(template.endswith('.md'), 'template produces .md file')


# ============================================================================
# Main runner
# ============================================================================

async def main():
    global _test_passed, _test_failed, _test_errors

    print("=" * 60)
    print("  Step 10: Export + Model Switch — Test Suite")
    print("=" * 60)

    # Part A: Export
    await test_export_basic()
    await test_export_empty_session()
    await test_export_nonexistent_session()
    await test_export_title_sanitization()
    await test_export_multiline_messages()

    # Part B: Model config
    await test_model_config_per_provider()
    await test_model_config_unknown_fallback()
    await test_available_models_list()

    # Part C: State management
    await test_state_model_switch()
    await test_clear_user_resets_model()
    await test_export_path_template_substitution()

    # Summary
    total = _test_passed + _test_failed
    print(f"\n{'='*60}")
    print(f"  Results: {_test_passed}/{total} passed, {_test_failed} failed")
    print(f"{'='*60}")

    if _test_failed > 0:
        print("\n  Failed tests:")
        for err in _test_errors:
            print(f"    - {err}")

    return _test_failed == 0


if __name__ == '__main__':
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
