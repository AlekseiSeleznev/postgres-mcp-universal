set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

conformance := "/home/as/Документы/AI_PROJECTS/modelcontextprotocol-conformance/dist/index.js"
inspector := "/home/as/Документы/AI_PROJECTS/modelcontextprotocol-inspector/cli/build/index.js"
mcpeval_dir := "/home/as/Документы/AI_PROJECTS/lastmile-ai-mcp-eval"
pwsh := "/home/as/Документы/AI_PROJECTS/PowerShell-PowerShell/runtime-7.6.1-linux-x64/pwsh"
default_mcp_url := "http://localhost:8090/mcp"
default_health_url := "http://localhost:8090/health"

default:
    @echo "Available: test, health, mcp-init, mcp-tools-list, mcp-conformance, mcp-inspector-tools, mcp-eval, mcp-eval-integration, pwsh-version, pwsh-smoke, smoke"

test:
    cd gateway && { command -v python >/dev/null 2>&1 && python -m pytest tests -q || python3 -m pytest tests -q; }

health:
    curl -fsS "${HEALTH_URL:-{{default_health_url}}}"

mcp-init:
    node "{{conformance}}" server --url "${MCP_URL:-{{default_mcp_url}}}" --scenario server-initialize --output-dir "${MCP_CONFORMANCE_RESULTS:-/tmp/postgres-mcp-conformance}"

mcp-tools-list:
    node "{{conformance}}" server --url "${MCP_URL:-{{default_mcp_url}}}" --scenario tools-list --output-dir "${MCP_CONFORMANCE_RESULTS:-/tmp/postgres-mcp-conformance}"

mcp-conformance: mcp-init mcp-tools-list

mcp-inspector-tools:
    #!/usr/bin/env bash
    set -euo pipefail
    url="${MCP_URL:-{{default_mcp_url}}}"
    if [ -n "${PG_MCP_API_KEY:-}" ]; then
      node "{{inspector}}" --transport http --header "Authorization: Bearer ${PG_MCP_API_KEY}" --method tools/list "$url"
    else
      node "{{inspector}}" --transport http --method tools/list "$url"
    fi

mcp-eval path="tests/mcp-eval":
    #!/usr/bin/env bash
    set -euo pipefail
    project_dir="$PWD"
    eval_port="${MCP_EVAL_PORT:-18090}"
    eval_state="${MCP_EVAL_STATE_FILE:-/tmp/postgres-mcp-universal-mcpeval-state.json}"
    rm -f "$eval_state"
    cd "$project_dir/gateway"
    PG_MCP_PORT="$eval_port" \
    PG_MCP_STATE_FILE="$eval_state" \
    PG_MCP_DATABASE_URI="" \
    PG_MCP_API_KEY="" \
    PG_MCP_RATE_LIMIT_ENABLED=false \
    python3 -m gateway > /tmp/postgres-mcp-universal-mcpeval-server.log 2>&1 &
    server_pid="$!"
    cleanup() {
      kill "$server_pid" >/dev/null 2>&1 || true
      wait "$server_pid" >/dev/null 2>&1 || true
      rm -f "$eval_state"
    }
    trap cleanup EXIT
    for _ in $(seq 1 30); do
      if curl --max-time 2 -fsS "http://127.0.0.1:${eval_port}/health" >/dev/null 2>&1; then
        break
      fi
      sleep 0.2
    done
    curl --max-time 2 -fsS "http://127.0.0.1:${eval_port}/health" >/dev/null
    cd "{{mcpeval_dir}}"
    uv run mcp-eval run "$project_dir/{{path}}"

mcp-eval-integration path="tests/mcp-eval-integration":
    #!/usr/bin/env bash
    set -euo pipefail
    if [ "${PG_MCP_EVAL_INTEGRATION:-0}" != "1" ]; then
      echo "Skipping integration mcp-eval: set PG_MCP_EVAL_INTEGRATION=1 and PG_MCP_EVAL_DATABASE=<registered connected db name> to run."
      exit 0
    fi
    if [ -z "${PG_MCP_EVAL_DATABASE:-}" ]; then
      echo "Skipping integration mcp-eval: PG_MCP_EVAL_DATABASE is required."
      exit 0
    fi
    project_dir="$PWD"
    cd "{{mcpeval_dir}}"
    uv run mcp-eval run "$project_dir/{{path}}"

pwsh-version:
    @"{{pwsh}}" -NoLogo -NoProfile -Command '$PSVersionTable.PSVersion.ToString()'

pwsh-smoke:
    @"{{pwsh}}" -NoLogo -NoProfile -File tests/smoke/mcp-smoke.ps1

smoke: health mcp-conformance
