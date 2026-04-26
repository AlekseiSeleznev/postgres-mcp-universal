# MCP-Eval Integration Suite

This profile is gated because it uses a real registered PostgreSQL backend.

Run only when the local `postgres-mcp-universal` gateway is available and the
target database is already registered and connected:

```bash
PG_MCP_EVAL_INTEGRATION=1 \
PG_MCP_EVAL_DATABASE=claas-postgres-nifi-NIFI_CLAAS_UH_KA \
/home/as/Документы/AI_PROJECTS/casey-just/target/release/just mcp-eval-integration
```

The integration test uses read-only metadata flow:

1. `list_databases`
2. `switch_database`
3. `list_schemas`

It does not run SQL, DDL, DML, SAP, NiFi, SSH, or 1C operations.

Model API keys are not required for the current integration profile. Future
agent-quality evals that call `agent.generate_str()` should be added under a
separate model-gated profile and should read provider credentials only from
environment variables such as `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`.

