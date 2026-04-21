"""Lightweight load-smoke tests for concurrent and polling scenarios."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient


@pytest.mark.asyncio
async def test_query_execute_sql_concurrent_smoke():
    from gateway.tools import query as query_mod

    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=[{"id": 1}])
    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire.return_value = acquire_cm

    db = SimpleNamespace(access_mode="unrestricted")

    async def _one_call():
        result = await query_mod.handle("execute_sql", {"query": "SELECT 1"}, session_id="s1")
        assert "(1 row)" in result[0].text

    with patch.object(query_mod.pool_manager, "get_pool", return_value=pool), \
         patch.object(query_mod.pool_manager, "get_active_db", return_value="main"), \
         patch.object(query_mod.registry, "get", return_value=db):
        await asyncio.gather(*[_one_call() for _ in range(25)])

    assert conn.fetch.await_count == 25


@pytest.mark.asyncio
async def test_admin_connect_disconnect_churn_smoke():
    from gateway.tools import admin as admin_mod

    fake_registry = MagicMock()
    fake_registry.get.return_value = None
    fake_registry.remove.return_value = object()
    fake_registry.list_all.return_value = []

    fake_pool_manager = MagicMock()
    fake_pool_manager.connect = AsyncMock()
    fake_pool_manager.disconnect = AsyncMock()
    fake_pool_manager.get_active_db.return_value = ""

    async def _connect_disconnect(i: int):
        name = f"db{i}"
        connected = await admin_mod.handle(
            "connect_database",
            {"name": name, "uri": f"postgresql://localhost/{name}"},
            session_id=f"s{i}",
        )
        assert "Connected to" in connected[0].text
        disconnected = await admin_mod.handle(
            "disconnect_database",
            {"name": name},
            session_id=f"s{i}",
        )
        assert "Disconnected from" in disconnected[0].text

    with patch.object(admin_mod, "registry", fake_registry), \
         patch.object(admin_mod, "pool_manager", fake_pool_manager):
        await asyncio.gather(*[_connect_disconnect(i) for i in range(20)])

    assert fake_pool_manager.connect.await_count == 20
    assert fake_pool_manager.disconnect.await_count == 20


def test_dashboard_status_polling_with_auth_smoke():
    from gateway.web_ui import api_status

    app = Starlette(routes=[Route("/api/status", api_status)])

    with patch("gateway.web_ui.settings") as ms, patch("gateway.web_ui.pool_manager") as pm:
        ms.api_key = "secret-token"
        ms.rate_limit_enabled = True
        ms.rate_limit_window_seconds = 60
        ms.rate_limit_api_requests = 200
        pm.get_status.return_value = {"ok": True}
        with TestClient(app) as client:
            statuses = [
                client.get("/api/status", headers={"Authorization": "Bearer secret-token"}).status_code
                for _ in range(100)
            ]

    assert all(code == 200 for code in statuses)
