# MCP Tool Catalog

Total tools: **23**.

Generated from `gateway/gateway/mcp_server.py` tool modules.
Regenerate with: `python3 tools/generate_tool_catalog.py`.

## `admin` (5)

| Tool | Description |
|------|-------------|
| `connect_database` | Connect to a PostgreSQL database. Adds it to the registry and creates a connection pool. Use 'uri' or 'connection_string' (both accepted). |
| `disconnect_database` | Disconnect from a database and remove it from the registry. |
| `get_server_status` | Get MCP server status: pools, sessions, active database. |
| `list_databases` | List all registered databases with connection status and pool info. |
| `switch_database` | Switch active database for this session. All subsequent queries will go to the selected database. |

## `query` (2)

| Tool | Description |
|------|-------------|
| `execute_sql` | Execute a SQL query against the active PostgreSQL database. In restricted mode only SELECT/EXPLAIN/SHOW/WITH are allowed. Returns results as a formatted table (up to 500 rows). |
| `explain_query` | Run EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) on a query. Returns the query plan with timing and buffer information. WARNING: EXPLAIN ANALYZE actually executes the query! |

## `schema` (5)

| Tool | Description |
|------|-------------|
| `get_table_info` | Get detailed table information: columns, types, constraints, indexes, foreign keys. |
| `list_functions` | List user-defined functions and procedures in a schema. |
| `list_indexes` | List indexes for a table or entire schema. |
| `list_schemas` | List all schemas in the active database. |
| `list_tables` | List tables and views in a schema with row counts and sizes. |

## `health` (5)

| Tool | Description |
|------|-------------|
| `active_queries` | Show currently running queries with duration, state, and wait events. |
| `db_health` | Comprehensive database health check: version, uptime, connections, cache hit ratio, dead tuples, long-running queries, replication lag. |
| `lock_info` | Show current locks and any blocked/blocking queries. |
| `table_bloat` | Estimate table and index bloat for tables in a schema. |
| `vacuum_stats` | Show vacuum and autovacuum statistics for tables. |

## `monitoring` (6)

| Tool | Description |
|------|-------------|
| `pg_activity` | Current backend activity: all client queries with PID, user, client address, duration, state (active/idle/idle-in-transaction), wait events. Also returns blocked/blocking lock pairs with queries. Use when investigating slow or stuck sessions. |
| `pg_index_stats` | Index usage statistics for a schema: scan count, tuples read/fetched, index size, and the index definition. Ordered by scan count ascending so unused indexes appear first. Use to identify unused or redundant indexes that waste write overhead. |
| `pg_overview` | Top-level PostgreSQL server metrics: version, uptime, connection counts, buffer cache hit ratio, database statistics (commits, rollbacks, tuple ops, deadlocks, conflicts), checkpoint stats, and WAL stats (PG14+). Use as a quick health snapshot before diving deeper. |
| `pg_replication` | Replication status: connected standbys with LSN positions, write/flush/replay lag (time and bytes), and all replication slots with retained WAL size. Returns empty lists on a standalone server. Use to monitor replication lag and detect stuck slots. |
| `pg_schemas` | List all user-defined schemas in the active database with their table counts. Excludes system schemas (pg_catalog, information_schema). Use to discover available schemas before exploring tables. |
| `pg_table_stats` | Per-table statistics for a schema: size (table + indexes), live/dead tuple counts, dead tuple percentage, sequential vs index scan counts, insert/update/delete counts, vacuum and analyze timestamps. Use to find tables needing vacuuming or lacking indexes. |
