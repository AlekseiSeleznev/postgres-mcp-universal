#!/usr/bin/env bash
set -euo pipefail

search_quiet() {
  local pattern="$1"
  shift

  if command -v rg >/dev/null 2>&1; then
    rg -q -- "$pattern" "$@"
  else
    grep -E -q -- "$pattern" "$@"
  fi
}

search_forbidden() {
  local pattern="$1"
  shift

  if command -v rg >/dev/null 2>&1; then
    ! rg -n -i -- "$pattern" "$@"
  else
    ! grep -E -n -i -- "$pattern" "$@"
  fi
}

if command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
else
  echo "python/python3 is unavailable; cannot run compileall smoke check"
  exit 1
fi

"${PYTHON_BIN}" -m compileall -q gateway
bash -n setup.sh

test -f CODEX.md
test -f AGENTS.md
test -f gateway/requirements-dev.txt
test -f install.cmd
test -f install.ps1
test -f uninstall.cmd
test -f uninstall.ps1
search_quiet "codex mcp add" setup.sh
search_quiet "ExecutionPolicy Bypass" install.cmd
search_quiet "ExecutionPolicy Bypass" uninstall.cmd
search_quiet "pytest-asyncio" gateway/requirements-dev.txt
search_forbidden "network_mode:\\s*host|network:\\s*host" docker-compose.yml
search_quiet "ports:" docker-compose.yml
search_quiet "platforms: linux/amd64,linux/arm64" .github/workflows/docker-publish.yml

if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    cp .env.example .env
  else
    : > .env
  fi
fi

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  docker compose -f docker-compose.yml config -q
  docker compose -f docker-compose.yml -f docker-compose.windows.yml config -q
else
  echo "docker compose is unavailable on this runner; skipping compose config smoke checks"
fi
