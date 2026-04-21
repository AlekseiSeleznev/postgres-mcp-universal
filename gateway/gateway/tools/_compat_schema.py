"""Shared MCP tool schemas for compatibility edge cases."""

from __future__ import annotations


def compat_empty_schema() -> dict:
    """Return a non-empty optional object schema for zero-arg tools.

    Some MCP client wrappers mishandle tools whose input schema is an object
    with no properties and end up sending invalid empty-string parameters.
    This optional placeholder keeps the schema non-empty while preserving the
    zero-argument behavior of the tool.
    """
    return {
        "type": "object",
        "properties": {
            "_compat": {
                "type": "boolean",
                "description": (
                    "Compatibility placeholder for MCP clients that mishandle empty "
                    "argument schemas. Ignored by the server."
                ),
            },
        },
    }
