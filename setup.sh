#!/usr/bin/env bash
set -euo pipefail

# ── postgres-mcp-universal setup ──────────────────────────────────
# One-command setup: creates .env (without API token auth by default),
# builds Docker image, starts the container, and registers the
# MCP server in Codex.
# Works on Linux, macOS, and Windows (Git Bash / WSL).

cd "$(dirname "$0")"

DEFAULT_PORT=8090
NAME="postgres-universal"
ENV_PORT_KEY="PG_MCP_PORT"
CONTAINER="pg-mcp-gateway"
SETUP_CI="${MCP_SETUP_CI:-0}"

# ── Helpers ──────────────────────────────────────────────────────
env_val() { grep "^$1=" "$2" 2>/dev/null | head -1 | cut -d= -f2-; }

# Portable sed -i (macOS needs '' arg)
sed_inplace() {
  if [ "$OS" = "macos" ]; then
    sed -i '' "$@"
  else
    sed -i "$@"
  fi
}

# set_env KEY VALUE FILE — write exact KEY=VALUE (create key if absent)
set_env() {
  local key="$1" val="$2" file="$3"
  if grep -q "^${key}=" "$file" 2>/dev/null; then
    sed_inplace "s|^${key}=.*|${key}=${val}|" "$file"
  else
    printf '\n%s=%s\n' "$key" "$val" >> "$file"
  fi
}

# ── 1. Prerequisites ─────────────────────────────────────────────
echo "── Checking prerequisites ──────────────────────────────────"

# Docker CLI
if command -v docker >/dev/null 2>&1; then
  echo "  ✓ docker $(docker --version | awk '{print $3}' | tr -d ',')"
else
  echo "  ✗ docker not found"
  echo "    Install Docker Engine: https://docs.docker.com/engine/install/"
  echo "    Install Docker Desktop: https://docs.docker.com/get-docker/"
  exit 1
fi

# Docker Compose V2 (plugin, not legacy docker-compose)
if docker compose version >/dev/null 2>&1; then
  echo "  ✓ docker compose $(docker compose version --short 2>/dev/null || docker compose version | awk '{print $NF}')"
else
  echo "  ✗ Docker Compose V2 not found"
  echo "    Docker Compose V2 is included in Docker Desktop and Docker Engine 23+."
  echo "    Install: https://docs.docker.com/compose/install/"
  exit 1
fi

# Docker daemon running
if ! docker info >/dev/null 2>&1; then
  echo ""
  echo "ERROR: Docker daemon is not running."
  echo "  On Linux:  sudo systemctl start docker"
  echo "  On macOS:  open Docker Desktop app"
  echo "  On Windows: start Docker Desktop"
  exit 1
fi
echo "  ✓ Docker daemon is running"

# Codex CLI (optional but recommended)
if command -v codex >/dev/null 2>&1; then
  echo "  ✓ codex CLI found"
  CODEX_FOUND=1
else
  echo "  ✗ codex CLI not found — MCP will not be registered automatically"
  echo "    Install Codex CLI and re-run setup, or register MCP manually later."
  CODEX_FOUND=0
fi

echo ""

# ── 2. Detect OS ────────────────────────────────────────────────
OS="linux"
case "$(uname -s)" in
  Darwin*)                OS="macos"   ;;
  MINGW*|MSYS*|CYGWIN*)  OS="windows" ;;
esac

# Remove legacy auto-generated override from older installs.
if [ -f docker-compose.override.yml ] && grep -q "Auto-generated for .*host mode unsupported" docker-compose.override.yml 2>/dev/null; then
  rm -f docker-compose.override.yml
  echo "[i] Removed legacy docker-compose.override.yml from older install flow"
fi

# ── 3. Create / update .env ─────────────────────────────────────
if [ ! -f .env ]; then
  cp .env.example .env
  echo "[+] Created .env from .env.example"
else
  echo "[i] .env already exists, keeping it"
fi
# Force no-auth mode so dashboard/API never prompt for Bearer token.
set_env "PG_MCP_API_KEY" "" .env
echo "[+] Disabled dashboard/API bearer auth (PG_MCP_API_KEY is empty)"

PORT=$(env_val "$ENV_PORT_KEY" .env 2>/dev/null || true)
PORT=${PORT:-$DEFAULT_PORT}

# ── 4. Check port availability ──────────────────────────────────
if command -v ss >/dev/null 2>&1; then
  PORT_IN_USE=$(ss -tlnp "sport = :${PORT}" 2>/dev/null | grep -c ":${PORT}" || true)
elif command -v lsof >/dev/null 2>&1; then
  PORT_IN_USE=$(lsof -ti ":${PORT}" 2>/dev/null | wc -l | tr -d ' ' || true)
else
  PORT_IN_USE=0
fi

if [ "${PORT_IN_USE:-0}" -gt 0 ]; then
  # It might be our own container — that's fine
  RUNNING_CONTAINER=$(docker ps --filter "name=${CONTAINER}" --filter "status=running" -q 2>/dev/null || true)
  if [ -z "$RUNNING_CONTAINER" ]; then
    echo ""
    echo "[!] WARNING: Port ${PORT} is already in use by another process."
    echo "    If you continue, the container may fail to start."
    if [ "$SETUP_CI" = "1" ]; then
      echo "    MCP_SETUP_CI=1: continuing without interactive prompt"
    else
      printf "    Continue anyway? [y/N] "
      read -r ANSWER </dev/tty
      if [ "${ANSWER:-N}" != "y" ] && [ "${ANSWER:-N}" != "Y" ]; then
        echo "Aborted. Change PG_MCP_PORT in .env and re-run setup.sh"
        exit 1
      fi
    fi
  fi
fi

# ── 5. Build & start ───────────────────────────────────────────
echo "[*] Building and starting container (restart: always — survives reboots)..."
EXACT_CONTAINER_ID=$(docker ps -aq --filter "name=^/${CONTAINER}$" 2>/dev/null || true)
if [ -n "${EXACT_CONTAINER_ID}" ]; then
  echo "[i] Removing stale container with exact name ${CONTAINER} before compose up"
  docker rm -f "${CONTAINER}" >/dev/null 2>&1 || true
fi
docker compose up -d --build --remove-orphans

# ── 6. Health check ─────────────────────────────────────────────
echo "[*] Waiting for gateway to be healthy..."
HEALTHY=0
for i in $(seq 1 30); do
  if curl --max-time 2 -sf "http://localhost:${PORT}/health" >/dev/null 2>&1; then
    HEALTHY=1; break
  fi
  sleep 1
done

if [ "$HEALTHY" -eq 0 ]; then
  STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$CONTAINER" 2>/dev/null || echo "unknown")
  [ "$STATUS" = "healthy" ] && HEALTHY=1
fi

if [ "$HEALTHY" -eq 1 ]; then
  echo "[+] Gateway is healthy on port ${PORT}"
else
  echo "[!] Gateway not healthy after 30s. Check: docker logs ${CONTAINER}"
  exit 1
fi

# ── 6b. Install systemd service (Linux) ─────────────────────────
if [ "$OS" = "linux" ] && [ "$SETUP_CI" != "1" ] && command -v systemctl >/dev/null 2>&1; then
  SERVICE_NAME="postgres-mcp-universal"
  SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
  WORK_DIR="$(pwd)"
  SERVICE_CONTENT="[Unit]
Description=${SERVICE_NAME} (Docker Compose)
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/docker compose -f ${WORK_DIR}/docker-compose.yml up -d --remove-orphans
ExecStop=/usr/bin/docker compose -f ${WORK_DIR}/docker-compose.yml down
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target"
  SERVICE_UPDATED=0
  if [ ! -f "$SERVICE_FILE" ] || ! diff -q "$SERVICE_FILE" <(printf '%s\n' "$SERVICE_CONTENT") >/dev/null 2>&1; then
    if printf '%s\n' "$SERVICE_CONTENT" | sudo tee "$SERVICE_FILE" > /dev/null 2>&1; then
      sudo systemctl daemon-reload
      SERVICE_UPDATED=1
    else
      echo "[!] Could not install systemd service (no sudo). To install manually:"
      echo "    sudo tee ${SERVICE_FILE} > /dev/null << 'SVCEOF'"
      printf '%s\n' "$SERVICE_CONTENT"
      echo "SVCEOF"
      echo "    sudo systemctl daemon-reload && sudo systemctl enable --now ${SERVICE_NAME}.service"
    fi
  fi
  if [ "$SERVICE_UPDATED" -eq 1 ]; then
    echo "[i] systemd service file written: ${SERVICE_NAME}"
  else
    echo "[i] systemd service already up to date: ${SERVICE_NAME}"
  fi
  if sudo systemctl enable --now "${SERVICE_NAME}.service" >/dev/null 2>&1; then
    echo "[+] systemd service enabled and started: ${SERVICE_NAME} (auto-start on boot without forced rebuild)"
  else
    echo "[!] Could not enable/start systemd service automatically (no sudo)."
    echo "    Run manually: sudo systemctl enable --now ${SERVICE_NAME}.service"
  fi
fi

# ── 7. Register in Codex ─────────────────────────────────────────
if [ "$SETUP_CI" = "1" ]; then
  echo "[i] MCP_SETUP_CI=1: skipping Codex MCP registration"
elif [ "$CODEX_FOUND" -eq 1 ]; then
  # Remove previous registration if exists (idempotent)
  codex mcp remove "$NAME" >/dev/null 2>&1 || true

  codex mcp add "$NAME" --url "http://localhost:${PORT}/mcp"
  echo "[+] Registered '${NAME}' in Codex"
else
  echo ""
  echo "[i] Codex CLI not found. Register manually after installing Codex:"
  echo "    codex mcp add ${NAME} --url http://localhost:${PORT}/mcp"
fi

# ── 8. Final verification ────────────────────────────────────────
echo ""
echo "── Final verification ──────────────────────────────────────"

# Health endpoint
HEALTH_RESPONSE=$(curl --max-time 2 -sf "http://localhost:${PORT}/health" 2>/dev/null || echo "UNREACHABLE")
echo "  /health → ${HEALTH_RESPONSE}"

# MCP registration
if [ "$CODEX_FOUND" -eq 1 ] && [ "$SETUP_CI" != "1" ]; then
  if codex mcp get "$NAME" >/dev/null 2>&1; then
    echo "  ✓ '${NAME}' is registered in Codex"
  else
    echo "  ✗ '${NAME}' NOT found in Codex MCP config — something went wrong"
  fi
fi

# ── Done ─────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════════"
echo "  Setup complete!"
echo ""
echo "  Next steps:"
if [ "$SETUP_CI" = "1" ]; then
  echo "  1. Open Dashboard: http://localhost:${PORT}/dashboard"
  echo "  2. MCP registration was skipped because MCP_SETUP_CI=1"
  echo "  3. Add a PostgreSQL connection via Dashboard or via MCP tool:"
else
  echo "  1. Verify MCP registration: codex mcp get ${NAME}"
  echo "  2. Open Dashboard: http://localhost:${PORT}/dashboard"
  echo "  3. Connect any MCP client to http://localhost:${PORT}/mcp"
  echo "  4. Start Codex in your working project and use MCP server '${NAME}'"
  echo "  5. Add a PostgreSQL connection via Dashboard or via MCP tool:"
fi
echo "     connect_database(name=\"mydb\","
echo "       connection_string=\"postgresql://user:pass@host:5432/dbname\")"
echo ""
echo "  After reboot: container auto-starts (restart: always)."
echo "  Codex registration remains in the local Codex MCP configuration."
echo "════════════════════════════════════════════════════════════"
