"""Tests for gateway.config — Settings, env vars, defaults."""

from __future__ import annotations

import os
import pytest
from unittest.mock import patch


class TestSettingsDefaults:
    """Verify default values are correct."""

    @staticmethod
    def _settings():
        # Tests for defaults must be isolated from developer-local .env values.
        from gateway.config import Settings
        with patch.dict(os.environ, {}, clear=True):
            return Settings(_env_file=None)

    def test_default_port(self):
        s = self._settings()
        assert s.port == 8090

    def test_default_log_level(self):
        s = self._settings()
        assert s.log_level == "INFO"

    def test_default_database_uri_empty(self):
        s = self._settings()
        assert s.database_uri == ""

    def test_default_access_mode(self):
        s = self._settings()
        assert s.access_mode == "unrestricted"

    def test_default_query_timeout(self):
        s = self._settings()
        assert s.query_timeout == 30

    def test_default_pool_min_size(self):
        s = self._settings()
        assert s.pool_min_size == 2

    def test_default_pool_max_size(self):
        s = self._settings()
        assert s.pool_max_size == 10

    def test_default_metadata_cache_ttl(self):
        s = self._settings()
        assert s.metadata_cache_ttl == 600

    def test_default_session_timeout(self):
        s = self._settings()
        # 8 hours in seconds
        assert s.session_timeout == 28800

    def test_default_api_key_empty(self):
        s = self._settings()
        assert s.api_key == ""

    def test_default_rate_limit_settings(self):
        s = self._settings()
        assert s.rate_limit_enabled is True
        assert s.rate_limit_window_seconds == 60
        assert s.rate_limit_mcp_requests == 60
        assert s.rate_limit_api_requests == 60
        assert s.rate_limit_oauth_requests == 10


class TestSettingsFromEnv:
    """Verify that settings can be overridden via environment variables."""

    def test_port_from_env(self):
        from gateway.config import Settings
        with patch.dict(os.environ, {"PG_MCP_PORT": "9090"}):
            s = Settings()
            assert s.port == 9090

    def test_log_level_from_env(self):
        from gateway.config import Settings
        with patch.dict(os.environ, {"PG_MCP_LOG_LEVEL": "DEBUG"}):
            s = Settings()
            assert s.log_level == "DEBUG"

    def test_database_uri_from_env(self):
        from gateway.config import Settings
        uri = "postgresql://user:pass@localhost:5432/mydb"
        with patch.dict(os.environ, {"PG_MCP_DATABASE_URI": uri}):
            s = Settings()
            assert s.database_uri == uri

    def test_access_mode_from_env(self):
        from gateway.config import Settings
        with patch.dict(os.environ, {"PG_MCP_ACCESS_MODE": "restricted"}):
            s = Settings()
            assert s.access_mode == "restricted"

    def test_query_timeout_from_env(self):
        from gateway.config import Settings
        with patch.dict(os.environ, {"PG_MCP_QUERY_TIMEOUT": "60"}):
            s = Settings()
            assert s.query_timeout == 60

    def test_pool_min_size_from_env(self):
        from gateway.config import Settings
        with patch.dict(os.environ, {"PG_MCP_POOL_MIN_SIZE": "5"}):
            s = Settings()
            assert s.pool_min_size == 5

    def test_pool_max_size_from_env(self):
        from gateway.config import Settings
        with patch.dict(os.environ, {"PG_MCP_POOL_MAX_SIZE": "20"}):
            s = Settings()
            assert s.pool_max_size == 20

    def test_api_key_from_env(self):
        from gateway.config import Settings
        with patch.dict(os.environ, {"PG_MCP_API_KEY": "secret-token-123"}):
            s = Settings()
            assert s.api_key == "secret-token-123"

    def test_session_timeout_from_env(self):
        from gateway.config import Settings
        with patch.dict(os.environ, {"PG_MCP_SESSION_TIMEOUT": "3600"}):
            s = Settings()
            assert s.session_timeout == 3600

    def test_rate_limit_settings_from_env(self):
        from gateway.config import Settings
        with patch.dict(os.environ, {
            "PG_MCP_RATE_LIMIT_ENABLED": "false",
            "PG_MCP_RATE_LIMIT_WINDOW_SECONDS": "15",
            "PG_MCP_RATE_LIMIT_MCP_REQUESTS": "7",
            "PG_MCP_RATE_LIMIT_API_REQUESTS": "8",
            "PG_MCP_RATE_LIMIT_OAUTH_REQUESTS": "3",
        }):
            s = Settings()
            assert s.rate_limit_enabled is False
            assert s.rate_limit_window_seconds == 15
            assert s.rate_limit_mcp_requests == 7
            assert s.rate_limit_api_requests == 8
            assert s.rate_limit_oauth_requests == 3

    def test_extra_env_vars_are_ignored(self):
        """extra='ignore' means unknown env vars do not raise errors."""
        from gateway.config import Settings
        with patch.dict(os.environ, {"PG_MCP_UNKNOWN_SETTING": "value"}):
            s = Settings()  # Should not raise
            assert s is not None

    def test_env_prefix(self):
        """Non-prefixed vars should not affect settings."""
        from gateway.config import Settings
        with patch.dict(os.environ, {"PORT": "1234"}):
            s = Settings()
            assert s.port == 8090  # Default unchanged


class TestGlobalSettings:
    """Verify module-level singleton exists."""

    def test_settings_singleton_exists(self):
        from gateway.config import settings
        assert settings is not None

    def test_settings_is_settings_instance(self):
        from gateway.config import settings, Settings
        assert isinstance(settings, Settings)
