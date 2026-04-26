import os
from pathlib import Path

import mcp_eval
from mcp_eval import task


SERVER_NAME = "postgres_universal"


@mcp_eval.setup
def configure_integration_profile():
    mcp_eval.use_config(str(Path(__file__).with_name("mcpeval.yaml")))


def _text(result) -> str:
    return "\n".join(
        part.text for part in getattr(result, "content", []) if hasattr(part, "text")
    )


@task("Connected integration database exposes schemas through read-only metadata tools")
async def connected_database_lists_schemas(agent, session):
    db_name = os.environ["PG_MCP_EVAL_DATABASE"]

    databases = await agent.agent.call_tool(
        "list_databases", {"_compat": True}, server_name=SERVER_NAME
    )
    database_text = _text(databases)
    assert db_name in database_text
    assert "connected" in database_text.lower()

    switch = await agent.agent.call_tool(
        "switch_database", {"name": db_name}, server_name=SERVER_NAME
    )
    assert getattr(switch, "isError", False) is not True, _text(switch)

    schemas = await agent.agent.call_tool(
        "list_schemas", {"_compat": True}, server_name=SERVER_NAME
    )
    schema_text = _text(schemas)
    assert getattr(schemas, "isError", False) is not True, schema_text
    assert "Schemas:" in schema_text or "No user schemas found" in schema_text

