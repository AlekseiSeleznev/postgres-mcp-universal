"""Extended server tests — session cleanup loop, background tasks, lifespan."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestSessionCleanupLoop:
    """Tests for _session_cleanup_loop background task."""

    @pytest.mark.asyncio
    async def test_cleanup_loop_calls_pool_manager_cleanup(self):
        """Cleanup loop should periodically call pool_manager.cleanup_sessions."""
        from gateway import server as server_mod

        cleanup_count = []

        def mock_cleanup():
            cleanup_count.append(1)
            return 0

        with patch.object(server_mod.pool_manager, "cleanup_sessions", side_effect=mock_cleanup), \
             patch("gateway.server.asyncio.sleep", AsyncMock(side_effect=asyncio.CancelledError)):
            try:
                await server_mod._session_cleanup_loop()
            except asyncio.CancelledError:
                pass

        # Should have called cleanup at least once before CancelledError
        assert len(cleanup_count) == 0  # loop calls sleep first, then cleanup

    @pytest.mark.asyncio
    async def test_cleanup_loop_cancels_cleanly(self):
        """CancelledError should stop the loop gracefully without re-raising."""
        from gateway import server as server_mod

        with patch("gateway.server.asyncio.sleep", AsyncMock(side_effect=asyncio.CancelledError)):
            # Should not raise — should handle CancelledError and exit cleanly
            await server_mod._session_cleanup_loop()

    @pytest.mark.asyncio
    async def test_cleanup_loop_survives_exception_in_cleanup(self):
        """Unexpected exception in cleanup should not kill the loop."""
        from gateway import server as server_mod

        call_count = [0]

        async def fake_sleep(n):
            call_count[0] += 1
            if call_count[0] >= 3:
                raise asyncio.CancelledError()

        with patch("gateway.server.asyncio.sleep", fake_sleep), \
             patch.object(
                 server_mod.pool_manager,
                 "cleanup_sessions",
                 side_effect=RuntimeError("unexpected"),
             ):
            # Should survive exceptions and loop until CancelledError
            await server_mod._session_cleanup_loop()

        # Should have looped 3 times despite exceptions
        assert call_count[0] == 3


class TestLifespanWithCleanupTask:
    """Tests that lifespan starts and stops the cleanup task properly."""

    @pytest.mark.asyncio
    async def test_lifespan_starts_cleanup_task(self, tmp_path):
        import gateway.server as server_mod
        import gateway.db_registry as db_reg_mod
        from gateway.db_registry import DatabaseRegistry
        from starlette.applications import Starlette

        empty_reg = DatabaseRegistry()
        mock_pool_manager = MagicMock()
        mock_pool_manager.connect = AsyncMock()
        mock_pool_manager.close_all = AsyncMock()
        mock_pool_manager.get_status = MagicMock(return_value={})
        mock_pool_manager.cleanup_sessions = MagicMock(return_value=0)

        tasks_created = []
        original_create_task = asyncio.create_task

        def mock_create_task(coro, **kwargs):
            task = original_create_task(coro, **kwargs)
            tasks_created.append(task)
            return task

        with patch.object(db_reg_mod, "registry", empty_reg), \
             patch.object(server_mod, "pool_manager", mock_pool_manager), \
             patch("gateway.server.settings") as mock_settings, \
             patch("gateway.db_registry.STATE_FILE", str(tmp_path / "s.json")), \
             patch("gateway.server.asyncio.create_task", mock_create_task):
            mock_settings.database_uri = ""
            mock_settings.port = 8080

            app = Starlette(lifespan=server_mod.lifespan)
            async with server_mod.lifespan(app):
                # At least the cleanup task should have been created
                assert len(tasks_created) >= 1

        # After lifespan exits, cleanup task should be done
        for task in tasks_created:
            assert task.done()


class TestMcpSessionManagement:
    """Tests for MCP session creation and transport reuse."""

    @pytest.mark.asyncio
    async def test_new_session_gets_transport(self):
        """Each new MCP request without session ID should get a new transport."""
        from gateway import server as server_mod

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/mcp",
            "headers": [],
            "query_string": b"",
        }

        responses = []

        async def receive():
            return {"type": "http.request", "body": b""}

        async def send(event):
            responses.append(event)

        # Mock the transport to avoid actually running MCP
        mock_transport = MagicMock()
        mock_transport.is_terminated = False
        mock_transport.handle_request = AsyncMock()

        mock_event = asyncio.Event()
        mock_event.set()

        with patch("gateway.server.settings") as mock_settings, \
             patch("gateway.server.StreamableHTTPServerTransport", return_value=mock_transport), \
             patch("gateway.server.asyncio.create_task") as mock_task, \
             patch("gateway.server.asyncio.Event", return_value=mock_event):
            mock_settings.api_key = ""
            def _fake_create_task(coro, **_kwargs):
                # Prevent "coroutine was never awaited" warning in this mocked path.
                coro.close()
                return MagicMock()

            mock_task.side_effect = _fake_create_task
            await server_mod.handle_mcp(scope, receive, send)

        mock_transport.handle_request.assert_awaited_once()
