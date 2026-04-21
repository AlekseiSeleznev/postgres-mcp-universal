"""Shared fixtures for gateway tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    from gateway.rate_limit import limiter

    limiter.reset()
    yield
    limiter.reset()
