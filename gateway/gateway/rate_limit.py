"""In-memory rate limiting for auth-sensitive HTTP endpoints."""

from __future__ import annotations

import math
import time
from collections import deque
from threading import Lock

from starlette.requests import Request
from starlette.responses import JSONResponse

from gateway.config import settings


class InMemoryRateLimiter:
    """Process-local fixed-window limiter keyed by route group and client IP."""

    def __init__(self) -> None:
        self._buckets: dict[str, deque[float]] = {}
        self._lock = Lock()

    def check(self, key: str, limit: int, window_seconds: int) -> int | None:
        """Return Retry-After seconds when the key is rate limited, else None."""
        now = time.monotonic()
        cutoff = now - window_seconds

        with self._lock:
            bucket = self._buckets.setdefault(key, deque())
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= limit:
                retry_after = max(1, math.ceil(window_seconds - (now - bucket[0])))
                return retry_after

            bucket.append(now)
            return None

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


limiter = InMemoryRateLimiter()


def _bool_setting(settings_obj, name: str, default: bool) -> bool:
    value = getattr(settings_obj, name, default)
    return value if isinstance(value, bool) else default


def _int_setting(settings_obj, name: str, default: int) -> int:
    value = getattr(settings_obj, name, default)
    if isinstance(value, int) and value > 0:
        return value
    return default


def _limit_for_group(group: str, settings_obj) -> int:
    defaults = {
        "mcp": 60,
        "api": 60,
        "oauth": 10,
    }
    field_names = {
        "mcp": "rate_limit_mcp_requests",
        "api": "rate_limit_api_requests",
        "oauth": "rate_limit_oauth_requests",
    }
    return _int_setting(settings_obj, field_names[group], defaults[group])


def _request_key(request: Request, group: str) -> str:
    client_host = request.client.host if request.client and request.client.host else "unknown"
    return f"{group}:{client_host}"


def check_rate_limit(request: Request, group: str, settings_obj=None) -> JSONResponse | None:
    """Return 429 response when the current request exceeds the configured limit."""
    settings_obj = settings if settings_obj is None else settings_obj

    if not _bool_setting(settings_obj, "rate_limit_enabled", True):
        return None

    window_seconds = _int_setting(settings_obj, "rate_limit_window_seconds", 60)
    retry_after = limiter.check(
        _request_key(request, group),
        _limit_for_group(group, settings_obj),
        window_seconds,
    )
    if retry_after is None:
        return None

    return JSONResponse(
        {"error": "rate_limited", "error_description": "too many requests"},
        status_code=429,
        headers={"Retry-After": str(retry_after)},
    )
