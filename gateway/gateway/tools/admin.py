"""Admin tools — database connection management."""

from __future__ import annotations

from mcp.types import TextContent, Tool

from gateway.db_registry import DatabaseInfo, registry
from gateway.pg_pool import pool_manager
from gateway.tools._compat_schema import compat_empty_schema

TOOLS = [
    Tool(
        name="connect_database",
        description=(
            "Connect to a PostgreSQL database. Adds it to the registry and creates a connection pool. "
            "Use 'uri' or 'connection_string' (both accepted)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Short name for this database (e.g. 'prod', 'analytics')"},
                "uri": {"type": "string", "description": "PostgreSQL connection URI: postgresql://user:pass@host:port/dbname"},
                "connection_string": {"type": "string", "description": "Alias for uri — PostgreSQL connection URI"},
                "access_mode": {
                    "type": "string",
                    "enum": ["unrestricted", "restricted"],
                    "description": "Access mode: 'unrestricted' (read/write) or 'restricted' (read-only). Default: unrestricted",
                },
            },
            "required": ["name"],
        },
    ),
    Tool(
        name="disconnect_database",
        description="Disconnect from a database and remove it from the registry.",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Database name to disconnect"},
            },
            "required": ["name"],
        },
    ),
    Tool(
        name="switch_database",
        description="Switch active database for this session. All subsequent queries will go to the selected database.",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Database name to switch to"},
            },
            "required": ["name"],
        },
    ),
    Tool(
        name="list_databases",
        description="List all registered databases with connection status and pool info.",
        inputSchema=compat_empty_schema(),
    ),
    Tool(
        name="get_server_status",
        description="Get MCP server status: pools, sessions, active database.",
        inputSchema=compat_empty_schema(),
    ),
]


async def handle(name: str, arguments: dict, session_id: str | None = None) -> list[TextContent]:
    if name == "connect_database":
        db_name = arguments["name"]
        # Accept both "uri" and "connection_string" as aliases
        uri = arguments.get("uri") or arguments.get("connection_string", "")
        if not uri:
            return [TextContent(
                type="text",
                text="Error: 'uri' or 'connection_string' is required (e.g. postgresql://user:pass@host:5432/dbname)",
            )]
        access_mode = arguments.get("access_mode", "unrestricted")

        # If already connected with same name, disconnect first (re-connect semantics)
        existing = registry.get(db_name)
        if existing:
            await pool_manager.disconnect(db_name)

        db = DatabaseInfo(name=db_name, uri=uri, access_mode=access_mode)
        registry.add(db)
        try:
            await pool_manager.connect(db)
        except Exception as e:
            registry.remove(db_name)
            return [TextContent(type="text", text=f"Failed to connect to '{db_name}': {e}")]

        return [TextContent(type="text", text=f"Connected to '{db_name}' ({access_mode} mode)")]

    if name == "disconnect_database":
        db_name = arguments["name"]
        removed = registry.remove(db_name)
        if not removed:
            return [TextContent(type="text", text=f"Database '{db_name}' not found")]
        await pool_manager.disconnect(db_name)
        registry.save()
        return [TextContent(type="text", text=f"Disconnected from '{db_name}'")]

    if name == "switch_database":
        db_name = arguments["name"]
        pool_manager.switch_db(db_name, session_id=session_id)
        return [TextContent(type="text", text=f"Switched to '{db_name}'")]

    if name == "list_databases":
        dbs = registry.list_all()
        if not dbs:
            return [TextContent(type="text", text="No databases registered. Use connect_database to add one.")]
        lines = []
        active = pool_manager.get_active_db(session_id)
        for db in dbs:
            marker = " *" if db.name == active else ""
            status = "connected" if db.connected else "disconnected"
            lines.append(f"  {db.name}{marker} — {status} ({db.access_mode})")
        return [TextContent(type="text", text="Databases (* = active):\n" + "\n".join(lines))]

    if name == "get_server_status":
        import json
        status = pool_manager.get_status()
        return [TextContent(type="text", text=json.dumps(status, indent=2))]

    return [TextContent(type="text", text=f"Unknown admin tool: {name}")]
