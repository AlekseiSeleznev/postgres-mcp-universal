"""MCP Server — tool registration and dispatch."""

from __future__ import annotations

import contextvars
import logging

from mcp.server import Server
from mcp.types import (
    GetPromptResult,
    Prompt,
    PromptArgument,
    PromptMessage,
    TextContent,
    Tool,
)

from gateway import __version__
from gateway.tools import admin, query, schema, health, monitoring

log = logging.getLogger(__name__)


AGENT_INSTRUCTIONS = """
You are connected to **postgres-mcp-universal** — an HTTP MCP gateway to
PostgreSQL databases at http://localhost:8090/mcp. For ANY task related to
PostgreSQL (reading data, inspecting schema, diagnosing performance,
planning migrations), **use these MCP tools first; do NOT guess table
structures or invent SQL from memory**.

Intent recognition — when the user's request is a PostgreSQL task,
route it here:
  User phrases that pin the session to this MCP:
    «Postgres / PostgreSQL / PG / постгрес», «используем Postgres <name>»,
    «работаем с PG <name>», «подключись к Postgres <name>»,
    «в базе postgres <name>», «switch to Postgres <name>».
  Postgres-specific terminology (any of these → use THIS MCP):
    postgresql:// or postgres:// DSN, pg_* tables/views, VACUUM, ANALYZE
    (SQL), EXPLAIN (ANALYZE), psql, pg_catalog, pg_stat_*, pg_index,
    WAL, hot-standby, replication slot, schema `public`/pgcrypto/uuid-ossp.
  Typical DB-name hints: main, prod, staging, dev, analytics, warehouse,
    <app>_prod / <app>_db / lowercase snake_case names.
  Action when user names a database («используем Postgres main»):
    1) list_databases → if `main` present, switch_database name=main.
    2) If not present, ask the user for `postgresql://…` URI or a
       traditional connection_string and call connect_database
       (default access_mode=restricted).
  If the user says «база X» without specifying Postgres, call
  list_databases here first; if X is present, proceed. If not, say so
  and ask — do NOT invent a connection.

Pre-flight (always):
  1. list_databases — confirm an active DB. If empty, ask the user for
     a connection URI and call connect_database (default profile is
     restricted = read-only).
  2. get_server_status — verify pool is healthy.

Reading data:
  schema: list_schemas → list_tables → get_table_info (columns, PK/FK,
  indexes). Never compose SQL against a table before get_table_info
  confirms the real column names and types.
  query: use execute_sql for SELECT/EXPLAIN/SHOW/WITH. Wrap expensive
  analyses in explain_query (analyze=false by default). Never send
  ANALYZE in restricted mode — it actually runs the query.

Diagnostics / performance:
  • Server-wide first: pg_overview / db_health (commits, rollbacks,
    deadlocks, WAL, cache hit ratio, replication status).
  • Then narrow: active_queries / pg_activity → lock_info for blocked
    backends → table_bloat + vacuum_stats → list_indexes / pg_index_stats
    (sorted by scan count ASC to find unused indexes) → pg_table_stats.

Writes (destructive operations):
  • Check DB access mode first — restricted DBs will reject DDL / DML.
  • For every INSERT/UPDATE/DELETE/ALTER/DROP/CREATE: show the SQL to
    the user and ask to confirm. Do not run it silently.
  • Prefer EXPLAIN first on anything non-trivial.

If a required tool fails (backend offline, DB not connected, access
mode denies a write), tell the user explicitly — do NOT silently
fall back to hallucinated SQL.

Tool categories:
  lifecycle: connect_database, disconnect_database, switch_database,
    list_databases, get_server_status.
  query: execute_sql, explain_query.
  schema: list_schemas, list_tables, get_table_info, list_indexes,
    list_functions.
  health (basic): db_health, active_queries, table_bloat, vacuum_stats,
    lock_info.
  monitoring (advanced): pg_overview, pg_activity, pg_table_stats,
    pg_index_stats, pg_replication, pg_schemas.

Common pitfalls — read this before calling unfamiliar tools:
  • Always inspect `tools/list` and read inputSchema before a first
    call. Do NOT invent argument names. Most tool-level errors are
    `'X' is a required property`.
  • connect_database: accepts EITHER `uri` OR `connection_string`
    (both are optional props but one is required). `access_mode`
    defaults to `restricted` (read-only). Pass `unrestricted` only
    when the user explicitly asks for writes.
  • execute_sql in restricted profile rejects INSERT / UPDATE /
    DELETE / ALTER / DROP / CREATE / TRUNCATE. Check access_mode via
    list_databases BEFORE suggesting writes; if writes are needed,
    tell the user to reconnect with `access_mode=unrestricted`.
  • explain_query with `analyze=true` actually executes the query.
    For expensive analyses default to `analyze=false`; never pass
    `analyze=true` in restricted mode.
  • list_tables / list_indexes / list_functions / get_table_info /
    table_bloat / vacuum_stats / pg_table_stats / pg_index_stats:
    `schema` defaults to `public`. If the object lives elsewhere,
    pass schema explicitly; don't assume `public`.
  • Active DB is pinned to the current Mcp-Session-Id. Call
    `switch_database` once per session. Two clients can hold
    different active DBs concurrently — sessions are independent.
  • Metadata cache TTL is 600s. After ALTER / CREATE / DROP re-fetch
    `get_table_info` before composing new SQL; warn the user about
    possible lag.
  • If a call returns HTTP 404 or the session stops responding, the
    gateway dropped the session. Re-initialize (initialize +
    notifications/initialized); do NOT retry on the same SID.
  • Before ANY destructive SQL (UPDATE / DELETE / DROP / ALTER /
    CREATE / TRUNCATE): show the final SQL to the user and wait for
    an explicit "yes" — never run silently.
""".strip()


server = Server(
    "postgres-mcp-universal", version=__version__, instructions=AGENT_INSTRUCTIONS
)

# Per-request context variable holding the Mcp-Session-Id header value.
# Set by server.py's handle_mcp() before forwarding each request to the
# transport, so tool handlers can retrieve it without touching MCP SDK internals.
_current_session_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "_current_session_id", default=None
)

# Collect all tools from modules
ALL_TOOL_MODULES = [admin, query, schema, health, monitoring]


def _all_tools() -> list[Tool]:
    tools = []
    for mod in ALL_TOOL_MODULES:
        tools.extend(mod.TOOLS)
    return tools


# Map tool name -> module for dispatch
_TOOL_DISPATCH: dict[str, object] = {}
for _mod in ALL_TOOL_MODULES:
    for _tool in _mod.TOOLS:
        _TOOL_DISPATCH[_tool.name] = _mod


def _get_session_id() -> str | None:
    """Return the Mcp-Session-Id for the current request.

    The value is injected by server.py's handle_mcp() via _current_session_id
    ContextVar before the request is forwarded to the MCP transport. When
    called outside an HTTP request (e.g. tests or stdio transport), None is
    returned and pool_manager falls back to the global active database.
    """
    return _current_session_id.get()


@server.list_tools()
async def list_tools() -> list[Tool]:
    return _all_tools()


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    session_id = _get_session_id()
    log.debug("call_tool %s session=%s args=%s", name, session_id, arguments)

    mod = _TOOL_DISPATCH.get(name)
    if not mod:
        # MCP spec: unknown tool is an error — return isError=True
        from mcp.types import CallToolResult
        return CallToolResult(
            isError=True,
            content=[TextContent(type="text", text=f"Unknown tool: {name}")],
        )

    try:
        return await mod.handle(name, arguments, session_id=session_id)
    except Exception as e:
        log.exception("Tool %s failed", name)
        # MCP spec §2.4: tool errors should set isError=True
        from mcp.types import CallToolResult
        return CallToolResult(
            isError=True,
            content=[TextContent(type="text", text=f"Error in {name}: {e}")],
        )


# ---------------------------------------------------------------------------
# MCP Prompts — ready-to-run playbooks for typical PostgreSQL tasks
# ---------------------------------------------------------------------------

_PROMPTS: list[tuple[Prompt, str]] = [
    (
        Prompt(
            name="connect_and_inspect",
            description=(
                "Connect (or confirm) a PostgreSQL database, then show a "
                "quick server overview: schemas, size, health."
            ),
            arguments=[],
        ),
        (
            "Use postgres-mcp-universal to: "
            "1) list_databases; if empty, ask the user for a connection URI "
            "and call connect_database. "
            "2) db_health — version, uptime, cache hit ratio, connections. "
            "3) list_schemas — user-defined schemas with table counts. "
            "4) pg_overview — commits/rollbacks/deadlocks snapshot. "
            "Summarise findings. Never invent schema or table names."
        ),
    ),
    (
        Prompt(
            name="describe_table",
            description=(
                "Describe a table: columns, PK/FK, indexes, row count, "
                "bloat and index usage."
            ),
            arguments=[
                PromptArgument(
                    name="table",
                    description="schema.table, e.g. 'public.orders'",
                    required=True,
                ),
            ],
        ),
        (
            "For {table}: "
            "1) get_table_info — columns, PK, FK, indexes, constraints. "
            "2) list_indexes — sizes and scan counts. "
            "3) table_bloat — dead-tuple ratio. "
            "4) vacuum_stats — last autovacuum timestamps. "
            "5) pg_index_stats filtered to the same table — flag indexes "
            "with scan_count = 0. "
            "Never compose SQL for the table before step 1 confirms its "
            "real schema."
        ),
    ),
    (
        Prompt(
            name="safe_query",
            description=(
                "Run a SELECT safely: EXPLAIN first, then execute with a "
                "sensible LIMIT. Stops if the plan looks expensive."
            ),
            arguments=[
                PromptArgument(
                    name="query",
                    description="SQL (SELECT) to analyse and run",
                    required=True,
                ),
            ],
        ),
        (
            "For the query: {query}\n"
            "1) explain_query with analyze=false (never ANALYZE in "
            "restricted mode). "
            "2) Read the plan — if cost is very high or a seq scan on a "
            "large table, suggest an index/rewrite instead of running. "
            "3) Otherwise execute_sql with a LIMIT 100 if the user did not "
            "set one. "
            "4) Summarise results."
        ),
    ),
    (
        Prompt(
            name="diagnose_performance",
            description=(
                "Triage database performance: look at running queries, "
                "locks, bloat, unused indexes, replication lag."
            ),
            arguments=[],
        ),
        (
            "Performance triage: "
            "1) pg_overview — deadlocks, checkpoint stats, WAL rate. "
            "2) active_queries + pg_activity — long-running / blocked. "
            "3) lock_info — who blocks whom. "
            "4) table_bloat + vacuum_stats — hotspots needing VACUUM. "
            "5) pg_index_stats sorted ascending by scan count — candidates "
            "for DROP INDEX. "
            "6) pg_replication — standby lag if replicas exist. "
            "Produce a prioritised list with the tool call that produced "
            "each finding."
        ),
    ),
    (
        Prompt(
            name="propose_migration",
            description=(
                "Plan a schema migration: show current state, compose SQL, "
                "wait for user approval, then execute."
            ),
            arguments=[
                PromptArgument(
                    name="intent",
                    description="What the migration should achieve",
                    required=True,
                ),
            ],
        ),
        (
            "Migration for: {intent}\n"
            "1) Identify target table(s) and call get_table_info for each. "
            "2) Compose the ALTER/CREATE/DROP SQL. "
            "3) explain_query if it is data-motion-heavy (CREATE INDEX, "
            "etc.). "
            "4) Present the SQL to the user and ask to confirm. "
            "5) On 'yes', execute via execute_sql — NOT before. "
            "6) Re-run get_table_info to show the applied change. "
            "If the DB is in restricted mode, stop at step 4 and tell the "
            "user to switch to an unrestricted connection."
        ),
    ),
]


@server.list_prompts()
async def list_prompts() -> list[Prompt]:
    return [p for p, _ in _PROMPTS]


@server.get_prompt()
async def get_prompt(name: str, arguments: dict | None = None) -> GetPromptResult:
    for prompt, body in _PROMPTS:
        if prompt.name == name:
            args = arguments or {}
            try:
                text = body.format(**args)
            except KeyError:
                text = body
            return GetPromptResult(
                description=prompt.description,
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(type="text", text=text),
                    )
                ],
            )
    raise ValueError(f"Unknown prompt: {name}")
