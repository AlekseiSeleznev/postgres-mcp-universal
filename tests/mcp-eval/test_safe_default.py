from pathlib import Path

import mcp_eval
from mcp_eval import task


SERVER_NAME = "postgres_universal"
MISSING_DB = "__mcpeval_missing_backend_do_not_create__"
REQUIRED_TOOLS = {
    "connect_database",
    "disconnect_database",
    "switch_database",
    "list_databases",
    "get_server_status",
    "execute_sql",
    "explain_query",
    "list_schemas",
    "list_tables",
    "get_table_info",
    "list_indexes",
    "list_functions",
    "db_health",
    "active_queries",
    "table_bloat",
    "vacuum_stats",
    "lock_info",
    "pg_overview",
    "pg_activity",
    "pg_table_stats",
    "pg_index_stats",
    "pg_replication",
    "pg_schemas",
}


@mcp_eval.setup
def configure_safe_default_profile():
    mcp_eval.use_config(str(Path(__file__).with_name("mcpeval.yaml")))


def _text(result) -> str:
    text = "\n".join(
        part.text for part in getattr(result, "content", []) if hasattr(part, "text")
    )
    return text or str(result)


@task("MCP server is reachable and exposes the expected safe tool catalog")
async def server_lists_expected_tools(agent, session):
    tools_result = await agent.agent.list_tools(server_name=SERVER_NAME)
    prefix = f"{SERVER_NAME}_"
    names = {
        tool.name[len(prefix) :] if tool.name.startswith(prefix) else tool.name
        for tool in tools_result.tools
    }

    missing = REQUIRED_TOOLS - names
    assert not missing, f"Missing expected MCP tools: {sorted(missing)}"
    assert len(names) == 23, f"Expected 23 tools, got {len(names)}: {sorted(names)}"


@task("Discovery flow uses list_databases before server status")
async def discovery_flow_is_available_and_non_secret(agent, session):
    databases = await agent.agent.call_tool(
        "list_databases", {"_compat": True}, server_name=SERVER_NAME
    )
    status = await agent.agent.call_tool(
        "get_server_status", {"_compat": True}, server_name=SERVER_NAME
    )

    database_text = _text(databases)
    status_text = _text(status)

    assert "postgresql://" not in database_text.lower()
    assert "password" not in database_text.lower()
    assert "uri" not in database_text.lower()
    assert "pools" in status_text
    assert "active_default" in status_text


@task("Unavailable backend is reported explicitly instead of fabricated")
async def unavailable_backend_is_reported_not_invented(agent, session):
    result = await agent.agent.call_tool(
        "switch_database", {"name": MISSING_DB}, server_name=SERVER_NAME
    )
    text = _text(result)

    assert getattr(result, "isError", False) is True
    assert MISSING_DB in text, text
    assert (
        "not connected" in text.lower()
        or "error in switch_database" in text.lower()
    ), text


@task("Read tools do not fabricate schema when no active connected backend exists")
async def schema_discovery_failure_is_explicit(agent, session):
    await agent.agent.call_tool(
        "switch_database", {"name": MISSING_DB}, server_name=SERVER_NAME
    )
    result = await agent.agent.call_tool(
        "list_schemas", {"_compat": True}, server_name=SERVER_NAME
    )
    text = _text(result)

    assert getattr(result, "isError", False) is True
    assert (
        "not connected" in text.lower()
        or "no active database" in text.lower()
    ), text
    assert "public.orders" not in text.lower()
    assert "nifi endpoint" not in text.lower()
    assert "postgresql://" not in text.lower()
    assert "password" not in text.lower()
