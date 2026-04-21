"""Tests for gateway.web_ui_services service-layer branches."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from gateway.web_ui_services import connect_from_request, edit_from_request


class _Request:
    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_connect_from_request_success_and_validation_errors():
    registry = MagicMock()
    pool_manager = MagicMock()
    pool_manager.connect = AsyncMock()
    database_info_cls = lambda **kwargs: SimpleNamespace(**kwargs)

    result = await connect_from_request(
        _Request({"name": "db1", "uri": "postgresql://localhost/db1", "access_mode": "restricted"}),
        registry=registry,
        pool_manager=pool_manager,
        database_info_cls=database_info_cls,
    )
    assert result == {"ok": True, "name": "db1"}
    registry.add.assert_called_once()
    pool_manager.connect.assert_awaited_once()

    invalid = await connect_from_request(
        _Request({"name": "bad name", "uri": "postgresql://localhost/db"}),
        registry=MagicMock(),
        pool_manager=MagicMock(),
        database_info_cls=database_info_cls,
    )
    assert invalid.status_code == 400


@pytest.mark.asyncio
async def test_edit_from_request_restores_old_db_on_reconnect_failure():
    old_db = SimpleNamespace(name="old", uri="postgresql://user:secret@localhost/db", access_mode="unrestricted")
    registry = MagicMock()
    registry.active = "old"
    registry.get.return_value = old_db
    registry.remove.return_value = old_db
    pool_manager = MagicMock()
    pool_manager.disconnect = AsyncMock()
    pool_manager.connect = AsyncMock(side_effect=[RuntimeError("connect failed"), None])
    database_info_cls = lambda **kwargs: SimpleNamespace(**kwargs)

    result = await edit_from_request(
        _Request({"old_name": "old", "name": "new", "uri": "postgresql://user@localhost/db"}),
        registry=registry,
        pool_manager=pool_manager,
        database_info_cls=database_info_cls,
    )

    assert result.status_code == 500
    registry.remove.assert_any_call("old")
    registry.remove.assert_any_call("new")
    assert registry.add.call_count == 2
    pool_manager.disconnect.assert_awaited_once_with("old")
    assert pool_manager.connect.await_count == 2


@pytest.mark.asyncio
async def test_edit_from_request_preserves_saved_default_when_other_db_is_active():
    registry = MagicMock()
    registry.active = "analytics"
    registry.get.return_value = None
    registry.remove.return_value = None
    pool_manager = MagicMock()
    pool_manager.disconnect = AsyncMock()
    pool_manager.connect = AsyncMock()
    database_info_cls = lambda **kwargs: SimpleNamespace(**kwargs)

    result = await edit_from_request(
        _Request({"old_name": "archive", "name": "archive-v2", "uri": "postgresql://localhost/archive"}),
        registry=registry,
        pool_manager=pool_manager,
        database_info_cls=database_info_cls,
    )

    assert result == {"ok": True, "name": "archive-v2"}
    assert registry.active == "analytics"
    registry.save.assert_called_once()


@pytest.mark.asyncio
async def test_edit_from_request_returns_400_for_missing_fields_and_handles_restore_failure():
    missing = await edit_from_request(
        _Request({"old_name": "", "name": "new", "uri": "postgresql://localhost/db"}),
        registry=MagicMock(),
        pool_manager=MagicMock(),
        database_info_cls=lambda **kwargs: SimpleNamespace(**kwargs),
    )
    assert missing.status_code == 400

    old_db = SimpleNamespace(name="old", uri="postgresql://user:secret@localhost/db", access_mode="unrestricted")
    registry = MagicMock()
    registry.active = "old"
    registry.get.return_value = old_db
    registry.remove.return_value = old_db
    pool_manager = MagicMock()
    pool_manager.disconnect = AsyncMock()
    pool_manager.connect = AsyncMock(side_effect=[RuntimeError("connect failed"), RuntimeError("restore failed")])

    result = await edit_from_request(
        _Request({"old_name": "old", "name": "new", "uri": "postgresql://user@localhost/db"}),
        registry=registry,
        pool_manager=pool_manager,
        database_info_cls=lambda **kwargs: SimpleNamespace(**kwargs),
    )

    assert result.status_code == 500
    assert pool_manager.connect.await_count == 2


@pytest.mark.asyncio
async def test_edit_from_request_connect_failure_without_old_db_and_without_saved_default_branch():
    registry = MagicMock()
    registry.active = "old"
    registry.get.return_value = None
    registry.remove.return_value = None
    pool_manager = MagicMock()
    pool_manager.disconnect = AsyncMock()
    pool_manager.connect = AsyncMock(side_effect=RuntimeError("connect failed"))

    failure = await edit_from_request(
        _Request({"old_name": "old", "name": "new", "uri": "postgresql://localhost/db"}),
        registry=registry,
        pool_manager=pool_manager,
        database_info_cls=lambda **kwargs: SimpleNamespace(**kwargs),
    )
    assert failure.status_code == 500

    registry = MagicMock()
    registry.active = "old"
    registry.get.return_value = None
    registry.remove.return_value = None
    pool_manager = MagicMock()
    pool_manager.disconnect = AsyncMock()
    pool_manager.connect = AsyncMock()

    ok = await edit_from_request(
        _Request({"old_name": "old", "name": "old-v2", "uri": "postgresql://localhost/db"}),
        registry=registry,
        pool_manager=pool_manager,
        database_info_cls=lambda **kwargs: SimpleNamespace(**kwargs),
    )
    assert ok == {"ok": True, "name": "old-v2"}

    registry = MagicMock()
    registry.active = ""
    registry.get.return_value = None
    registry.remove.return_value = None
    pool_manager = MagicMock()
    pool_manager.disconnect = AsyncMock()
    pool_manager.connect = AsyncMock()

    ok = await edit_from_request(
        _Request({"old_name": "archive", "name": "archive-v2", "uri": "postgresql://localhost/archive"}),
        registry=registry,
        pool_manager=pool_manager,
        database_info_cls=lambda **kwargs: SimpleNamespace(**kwargs),
    )
    assert ok == {"ok": True, "name": "archive-v2"}
    assert registry.active == ""
