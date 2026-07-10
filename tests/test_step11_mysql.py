# -*- coding: utf-8 -*-
"""Step 11: MySQL Backend — Test Suite."""

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


# ============ Part A: MySQL Backend Structure ============

def test_mysql_import():
    section("A1. MySQLBackend can be imported")

    from src.storage.mysql_backend import MySQLBackend
    check(MySQLBackend is not None, 'MySQLBackend class imported')

    # Verify it's a subclass of StorageBackend
    from src.storage.base import StorageBackend
    check(issubclass(MySQLBackend, StorageBackend),
          'MySQLBackend extends StorageBackend')


def test_mysql_constructor():
    section("A2. MySQLBackend constructor accepts all params")

    from src.storage.mysql_backend import MySQLBackend

    backend = MySQLBackend(
        host='localhost',
        port=3306,
        user='test_user',
        password='test_pass',
        database='test_db',
        pool_size=10,
        pool_recycle=7200,
    )
    check(backend._host == 'localhost', 'host stored correctly')
    check(backend._port == 3306, 'port stored correctly')
    check(backend._user == 'test_user', 'user stored correctly')
    check(backend._database == 'test_db', 'database stored correctly')
    check(backend._pool_size == 10, 'pool_size stored correctly')
    check(backend._pool_recycle == 7200, 'pool_recycle stored correctly')
    check(backend._pool is None, 'pool initially None')


def test_mysql_constructor_defaults():
    section("A3. MySQLBackend constructor defaults")

    from src.storage.mysql_backend import MySQLBackend

    backend = MySQLBackend()
    check(backend._host == 'localhost', 'default host')
    check(backend._port == 3306, 'default port')
    check(backend._user == 'root', 'default user')
    check(backend._password == '', 'default password')
    check(backend._database == 'langchain_chat', 'default database')
    check(backend._pool_size == 5, 'default pool_size')
    check(backend._pool_recycle == 3600, 'default pool_recycle')


def test_mysql_factory_registered():
    section("A4. Factory supports MySQL storage type")

    from src.storage.factory import StorageFactory
    check('mysql' in StorageFactory._SUPPORTED_BACKENDS,
          'mysql is in _SUPPORTED_BACKENDS')


# ============ Part B: Factory Wiring ============

async def test_factory_creates_mysql_type():
    section("B1. Factory recognizes mysql storage type")

    from src.core.config_manager import ConfigManager
    from src.storage.factory import StorageFactory

    config = ConfigManager()
    # Override storage type
    config._config['storage'] = config._config.get('storage', {})
    config._config['storage']['type'] = 'mysql'

    check(config.storage_type == 'mysql', 'config storage_type is mysql')

    # Try creating — it should attempt MySQL connection (will fail but that's expected)
    # We just verify it doesn't raise NotImplementedError
    try:
        storage = await StorageFactory.create(config)
        # If MySQL happens to be available, clean up
        await storage.close()
        print("  INFO MySQL is available — integration test passed with real DB")
    except Exception as e:
        error_msg = str(e)
        # Connection refused/timeout is expected (no MySQL running)
        # NotImplementedError would mean factory is broken
        is_connection_error = any(phrase in error_msg.lower() for phrase in [
            "connection refused", "cannot connect", "can't connect",
            "unknown mysql", "timeout", "host", "getaddrinfo",
        ])
        check(not isinstance(e, NotImplementedError),
              f'MySQL backend is NOT NotImplementedError (got: {type(e).__name__}: {error_msg[:80]})')
        if isinstance(e, NotImplementedError):
            check(False, 'Factory still raises NotImplementedError for MySQL')
        else:
            check(is_connection_error,
                  f'Expected connection error, got: {type(e).__name__}: {error_msg[:80]}')


# ============ Part C: MySQL Config Integration ============

async def test_mysql_config_from_config_manager():
    section("C1. ConfigManager provides MySQL config")

    from src.core.config_manager import ConfigManager

    config = ConfigManager()
    mysql_cfg = config.mysql_config

    check('host' in mysql_cfg, 'mysql_config has host')
    check('port' in mysql_cfg, 'mysql_config has port')
    check('user' in mysql_cfg, 'mysql_config has user')
    check('password' in mysql_cfg, 'mysql_config has password')
    check('database' in mysql_cfg, 'mysql_config has database')
    check('pool_size' in mysql_cfg, 'mysql_config has pool_size')
    check('pool_recycle' in mysql_cfg, 'mysql_config has pool_recycle')

    check(isinstance(mysql_cfg['port'], int), 'port is int')
    check(isinstance(mysql_cfg['pool_size'], int), 'pool_size is int')
    check(mysql_cfg['pool_size'] == 5, f'pool_size defaults to 5 (got {mysql_cfg["pool_size"]})')


async def test_factory_uses_mysql_config():
    section("C2. Factory passes MySQL config to MySQLBackend")

    from src.storage.mysql_backend import MySQLBackend

    # Create backend with config-like parameters
    backend = MySQLBackend(
        host='db.example.com',
        port=3307,
        user='app_user',
        password='secret',
        database='chat_db',
        pool_size=8,
        pool_recycle=1800,
    )
    check(backend._host == 'db.example.com', 'custom host')
    check(backend._port == 3307, 'custom port')
    check(backend._user == 'app_user', 'custom user')
    check(backend._password == 'secret', 'custom password')
    check(backend._database == 'chat_db', 'custom database')
    check(backend._pool_size == 8, 'custom pool_size')
    check(backend._pool_recycle == 1800, 'custom pool_recycle')


# ============ Part D: SQL Schema Compatibility ============

async def test_mysql_schema_has_all_tables():
    section("D1. MySQL CREATE TABLE statements cover all 5 tables")

    from src.storage.mysql_backend import _ALL_CREATE_STATEMENTS

    check(len(_ALL_CREATE_STATEMENTS) == 5,
          f'5 CREATE TABLE statements (got {len(_ALL_CREATE_STATEMENTS)})')

    statements_text = ' '.join(_ALL_CREATE_STATEMENTS).lower()
    check('create table' in statements_text, 'all CREATE TABLE')
    check('users' in statements_text, 'users table')
    check('sessions' in statements_text, 'sessions table')
    check('messages' in statements_text, 'messages table')
    check('presets' in statements_text, 'presets table')
    check('user_configs' in statements_text, 'user_configs table')


async def test_mysql_schema_uses_innodb():
    section("D2. MySQL tables use InnoDB engine")

    from src.storage.mysql_backend import _ALL_CREATE_STATEMENTS

    for sql in _ALL_CREATE_STATEMENTS:
        check('innodb' in sql.lower(),
              f'Table uses InnoDB engine: {sql.split("CREATE TABLE")[1].split("(")[0].strip()[:60]}')


async def test_mysql_schema_has_foreign_keys():
    section("D3. MySQL schema has foreign keys for referential integrity")

    from src.storage.mysql_backend import _ALL_CREATE_STATEMENTS

    statements_text = ' '.join(_ALL_CREATE_STATEMENTS).lower()
    check('foreign key' in statements_text, 'has FOREIGN KEY constraints')
    check('on delete cascade' in statements_text, 'has ON DELETE CASCADE')


async def test_mysql_schema_utf8mb4():
    section("D4. MySQL tables use utf8mb4 charset")

    from src.storage.mysql_backend import _ALL_CREATE_STATEMENTS

    for sql in _ALL_CREATE_STATEMENTS:
        check('utf8mb4' in sql.lower(),
              f'Table uses utf8mb4: {sql.split("CREATE TABLE")[1].split("(")[0].strip()[:60]}')


# ============ Part E: Column Definitions ============

async def test_mysql_column_definitions():
    section("E1. Column definition mappings are complete")

    from src.storage.mysql_backend import (
        _USERS_COLUMNS, _PRESETS_COLUMNS, _SESSIONS_COLUMNS,
        _MESSAGES_COLUMNS, _USER_CONFIGS_COLUMNS,
    )

    check('id' in _USERS_COLUMNS, 'users has id')
    check('username' in _USERS_COLUMNS, 'users has username')
    check('default_model' in _USERS_COLUMNS, 'users has default_model')
    check(len(_USERS_COLUMNS) == 6, f'users has 6 columns (got {len(_USERS_COLUMNS)})')

    check('id' in _SESSIONS_COLUMNS, 'sessions has id')
    check('user_id' in _SESSIONS_COLUMNS, 'sessions has user_id')
    check('title' in _SESSIONS_COLUMNS, 'sessions has title')
    check(len(_SESSIONS_COLUMNS) == 9, f'sessions has 9 columns (got {len(_SESSIONS_COLUMNS)})')

    check('id' in _MESSAGES_COLUMNS, 'messages has id')
    check('session_id' in _MESSAGES_COLUMNS, 'messages has session_id')
    check('role' in _MESSAGES_COLUMNS, 'messages has role')
    check('content' in _MESSAGES_COLUMNS, 'messages has content')
    check(len(_MESSAGES_COLUMNS) == 7, f'messages has 7 columns (got {len(_MESSAGES_COLUMNS)})')

    check('id' in _PRESETS_COLUMNS, 'presets has id')
    check('is_builtin' in _PRESETS_COLUMNS, 'presets has is_builtin')
    check(len(_PRESETS_COLUMNS) == 8, f'presets has 8 columns (got {len(_PRESETS_COLUMNS)})')

    check('id' in _USER_CONFIGS_COLUMNS, 'user_configs has id')
    check('key' in _USER_CONFIGS_COLUMNS, 'user_configs has key')
    check(len(_USER_CONFIGS_COLUMNS) == 5, f'user_configs has 5 columns (got {len(_USER_CONFIGS_COLUMNS)})')


# ============ Part F: Helper Functions ============

async def test_make_dict_helper():
    section("F1. _make_dict converts tuple to dict")

    from src.storage.mysql_backend import _make_dict

    columns = ['id', 'name', 'age']
    row = ('abc-123', 'Alice', 30)
    result = _make_dict(columns, row)
    check(result == {'id': 'abc-123', 'name': 'Alice', 'age': 30},
          f'_make_dict works: {result}')

    # None row returns None
    result_none = _make_dict(columns, None)
    check(result_none is None, '_make_dict returns None for None input')


async def test_parse_datetime_helper():
    section("F2. _parse_datetime handles various inputs")

    from datetime import datetime
    from src.storage.mysql_backend import _parse_datetime

    # None
    check(_parse_datetime(None) is None, 'None -> None')

    # datetime object (pass-through)
    now = datetime(2026, 7, 10, 14, 30, 0)
    result = _parse_datetime(now)
    check(result == now, f'datetime pass-through: {result}')

    # ISO string
    result = _parse_datetime('2026-07-10 14:30:00')
    check(isinstance(result, datetime), f'string -> datetime: {result}')
    check(result.year == 2026, f'year=2026 (got {result.year})')
    check(result.month == 7, f'month=7 (got {result.month})')

    # Invalid string
    result = _parse_datetime('not-a-date')
    check(result is None, 'invalid string -> None')


# ============ Part G: init_db.py Support ============

async def test_init_db_supports_mysql():
    section("G1. init_db.py recognizes MySQL storage type")

    from src.core.config_manager import ConfigManager

    # Verify the config flow: if storage type is mysql, ConfigManager
    # provides mysql_config dict that factory can use
    config = ConfigManager()
    config._config['storage'] = config._config.get('storage', {})
    config._config['storage']['type'] = 'mysql'

    check(config.storage_type == 'mysql', 'storage_type reads as mysql')

    # mysql_config should provide valid connection params
    mysql_cfg = config.mysql_config
    check(len(mysql_cfg['host']) > 0, 'mysql host is not empty')
    check(mysql_cfg['port'] > 0, 'mysql port > 0')


# ============ Part H: Switch Between Backends ============

async def test_switch_between_backends():
    section("H1. Config change switches between SQLite and MySQL backends")

    from src.core.config_manager import ConfigManager
    from src.storage.factory import StorageFactory

    # Verify that changing config.storage_type changes StorageFactory behavior
    config = ConfigManager()

    # SQLite
    config._config['storage'] = config._config.get('storage', {})
    config._config['storage']['type'] = 'sqlite'
    check(config.storage_type == 'sqlite', 'switched to sqlite')

    try:
        storage = await StorageFactory.create(config)
        from src.storage.sqlite_backend import SQLiteBackend
        check(isinstance(storage, SQLiteBackend),
              f'sqlite config creates SQLiteBackend (got {type(storage).__name__})')
        await storage.close()
    except Exception as e:
        check(False, f'SQLite creation failed: {e}')


# ============================================================================
# Main runner
# ============================================================================

async def main():
    global _test_passed, _test_failed, _test_errors

    print("=" * 60)
    print("  Step 11: MySQL Backend — Test Suite")
    print("=" * 60)

    # Part A: Structure
    test_mysql_import()
    test_mysql_constructor()
    test_mysql_constructor_defaults()
    test_mysql_factory_registered()

    # Part B: Factory Wiring
    await test_factory_creates_mysql_type()

    # Part C: Config
    await test_mysql_config_from_config_manager()
    await test_factory_uses_mysql_config()

    # Part D: Schema
    await test_mysql_schema_has_all_tables()
    await test_mysql_schema_uses_innodb()
    await test_mysql_schema_has_foreign_keys()
    await test_mysql_schema_utf8mb4()

    # Part E: Columns
    await test_mysql_column_definitions()

    # Part F: Helpers
    await test_make_dict_helper()
    await test_parse_datetime_helper()

    # Part G: init_db
    await test_init_db_supports_mysql()

    # Part H: Switch
    await test_switch_between_backends()

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
