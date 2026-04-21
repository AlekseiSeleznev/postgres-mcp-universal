"""Direct tests for gateway.monitoring coverage-critical branches."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _acquire_cm(conn):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm


@pytest.mark.asyncio
async def test_get_overview_falls_back_to_bgwriter_and_handles_missing_wal():
    from gateway import monitoring

    conn = MagicMock()
    conn.fetchval = AsyncMock(side_effect=["PostgreSQL 16", "0:12:00"])

    async def fetchrow_side_effect(query):
        if "FROM pg_stat_activity" in query:
            return {"total": 4, "active": 1, "idle": 3, "idle_in_tx": 0, "idle_in_tx_abort": 0, "max_conn": 100}
        if "FROM pg_stat_database WHERE datname = current_database()" in query and "hit_ratio" in query:
            return {"hits": 10, "reads": 2, "hit_ratio": 83.33}
        if "FROM pg_stat_database WHERE datname = current_database()" in query and "xact_commit" in query:
            return {"commits": 5, "rollbacks": 0, "size_pretty": "1 MB", "size_bytes": 1024, "numbackends": 2}
        if "FROM pg_stat_checkpointer" in query:
            raise RuntimeError("not available")
        if "buffers_checkpoint::bigint" in query:
            return {"checkpoints_timed": 1, "checkpoints_req": 2, "buffers_checkpoint": 3}
        if "buffers_clean::bigint" in query:
            return {"buffers_clean": 4, "buffers_alloc": 5, "maxwritten_clean": 6}
        if "FROM pg_stat_wal" in query:
            raise RuntimeError("no wal stats")
        raise AssertionError(query)

    conn.fetchrow = AsyncMock(side_effect=fetchrow_side_effect)
    pool = MagicMock()
    pool.acquire.return_value = _acquire_cm(conn)

    with patch.object(monitoring.pool_manager, "get_pool", return_value=pool):
        payload = await monitoring.get_overview(session_id="s1")

    assert payload["version"] == "PostgreSQL 16"
    assert payload["bgwriter"]["buffers_clean"] == 4
    assert payload["bgwriter"]["checkpoints_req"] == 2
    assert payload["wal"] is None


@pytest.mark.asyncio
async def test_get_replication_and_get_schemas_return_serialized_lists():
    from gateway import monitoring

    conn = MagicMock()
    conn.fetch = AsyncMock(side_effect=[
        [{"application_name": "replica-1", "state": "streaming"}],
        [{"slot_name": "slot1", "active": True}],
    ])
    pool_for_replication = MagicMock()
    pool_for_replication.acquire.return_value = _acquire_cm(conn)

    pool_for_schemas = MagicMock()
    pool_for_schemas.fetch = AsyncMock(return_value=[{"name": "public", "tables": 7}])

    with patch.object(monitoring.pool_manager, "get_pool", side_effect=[pool_for_replication, pool_for_schemas]):
        replication = await monitoring.get_replication(session_id="s1")
        schemas = await monitoring.get_schemas(session_id="s1")

    assert replication["replicas"][0]["application_name"] == "replica-1"
    assert replication["slots"][0]["slot_name"] == "slot1"
    assert schemas == [{"name": "public", "tables": 7}]


@pytest.mark.asyncio
async def test_get_overview_handles_missing_bgwriter_sources_completely():
    from gateway import monitoring

    conn = MagicMock()
    conn.fetchval = AsyncMock(side_effect=["PostgreSQL 16", "0:15:00"])

    async def fetchrow_side_effect(query):
        if "FROM pg_stat_activity" in query:
            return {"total": 1, "active": 1, "idle": 0, "idle_in_tx": 0, "idle_in_tx_abort": 0, "max_conn": 100}
        if "FROM pg_stat_database WHERE datname = current_database()" in query and "hit_ratio" in query:
            return {"hits": 5, "reads": 5, "hit_ratio": 50.0}
        if "FROM pg_stat_database WHERE datname = current_database()" in query and "xact_commit" in query:
            return {"commits": 1, "rollbacks": 0, "size_pretty": "1 MB", "size_bytes": 1024, "numbackends": 1}
        if "FROM pg_stat_checkpointer" in query:
            raise RuntimeError("no checkpointer")
        if "FROM pg_stat_bgwriter" in query:
            raise RuntimeError("no bgwriter")
        raise AssertionError(query)

    conn.fetchrow = AsyncMock(side_effect=fetchrow_side_effect)
    pool = MagicMock()
    pool.acquire.return_value = _acquire_cm(conn)

    with patch.object(monitoring.pool_manager, "get_pool", return_value=pool):
        payload = await monitoring.get_overview(session_id="s1")

    assert payload["bgwriter"] == {}
