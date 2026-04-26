# MCP-Eval Safe Default Suite

This directory contains the default `mcp-eval` suite for `postgres-mcp-universal`.

It is intentionally safe:

- Uses Streamable HTTP at `http://localhost:8090/mcp`.
- Does not require LLM API keys.
- Does not use real PostgreSQL credentials.
- Does not require SAP, NiFi, SSH, or 1C infrastructure.
- Does not run destructive SQL or dashboard mutation operations.

The tests validate the MCP surface, tool discovery, safe discovery flow, and
explicit error behavior for an unavailable backend.

Run:

```bash
/home/as/Документы/AI_PROJECTS/casey-just/target/release/just mcp-eval
```

