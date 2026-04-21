"""Shared helpers for row-like objects (asyncpg Records, dicts, mocks)."""

from __future__ import annotations


def row_as_dict(row) -> dict:
    if isinstance(row, dict):
        return row
    if hasattr(row, "keys"):
        try:
            return {k: row[k] for k in row.keys()}
        except Exception:
            pass
    if hasattr(row, "items"):
        try:
            return dict(row.items())
        except Exception:
            pass
    try:
        return dict(row)
    except Exception:
        pass
    return {}


def row_get(row, key: str, default=None):
    if hasattr(row, "get"):
        return row.get(key, default)
    try:
        return row[key]
    except Exception:
        return default


def row_has_key(row, key: str) -> bool:
    if hasattr(row, "keys"):
        try:
            return key in row.keys()
        except Exception:
            pass
    try:
        return key in row
    except Exception:
        return False
