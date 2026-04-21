"""Direct tests for in-memory rate limiting helpers."""

from __future__ import annotations

from collections import deque
from unittest.mock import patch

from starlette.requests import Request


def _request(path: str = "/api/status", *, client=None):
    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": [],
        "query_string": b"",
        "scheme": "http",
        "server": ("testserver", 8090),
    }
    if client is not None:
        scope["client"] = client
    return Request(scope)


def test_in_memory_rate_limiter_enforces_limit_and_reset():
    from gateway.rate_limit import InMemoryRateLimiter

    limiter = InMemoryRateLimiter()
    assert limiter.check("api:127.0.0.1", 1, 60) is None
    assert limiter.check("api:127.0.0.1", 1, 60) == 60

    limiter.reset()
    assert limiter.check("api:127.0.0.1", 1, 60) is None


def test_in_memory_rate_limiter_drops_expired_entries():
    from gateway.rate_limit import InMemoryRateLimiter

    limiter = InMemoryRateLimiter()
    with patch("gateway.rate_limit.time.monotonic", side_effect=[100.0, 100.0, 161.0]):
        assert limiter.check("api:127.0.0.1", 1, 60) is None
        assert limiter.check("api:127.0.0.1", 1, 60) == 60
        assert limiter.check("api:127.0.0.1", 1, 60) is None


def test_check_rate_limit_separates_route_groups_for_same_ip():
    import gateway.rate_limit as rate_mod

    request = _request(client=("127.0.0.1", 12345))
    with patch.object(rate_mod.limiter, "_buckets", {}), \
         patch("gateway.rate_limit.settings") as mock_settings:
        mock_settings.rate_limit_enabled = True
        mock_settings.rate_limit_window_seconds = 60
        mock_settings.rate_limit_api_requests = 1
        mock_settings.rate_limit_oauth_requests = 1
        mock_settings.rate_limit_mcp_requests = 1

        assert rate_mod.check_rate_limit(request, "api") is None
        assert rate_mod.check_rate_limit(request, "oauth") is None
        assert rate_mod.check_rate_limit(request, "api").status_code == 429
        assert rate_mod.check_rate_limit(request, "oauth").status_code == 429


def test_check_rate_limit_can_be_disabled_and_uses_unknown_client_fallback():
    import gateway.rate_limit as rate_mod

    request = _request(client=None)
    with patch("gateway.rate_limit.settings") as mock_settings:
        mock_settings.rate_limit_enabled = False
        assert rate_mod.check_rate_limit(request, "api") is None

    key = rate_mod._request_key(request, "api")
    assert key == "api:unknown"
