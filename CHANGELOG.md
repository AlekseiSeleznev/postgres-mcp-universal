# История изменений

## v1.0.0 (2026-04-16)

- Первый публичный релиз репозитория.
- Runtime:
  - HTTP MCP endpoint на `POST /mcp`;
  - web dashboard на `/dashboard`;
  - 23 MCP tools для запросов, схемы, health и monitoring PostgreSQL.
- Установка:
  - единая Docker-схема на bridge-сети для Linux, Windows и macOS;
  - автоматический install path через `./setup.sh` и нативный Windows path через `install.cmd` / `install.ps1`;
  - uninstall/reinstall path документирован в `README.md` и `CODEX.md`.
- Безопасность и эксплуатация:
  - опциональный Bearer auth через `PG_MCP_API_KEY`;
  - in-memory rate limiting для `/mcp`, `/api/*` и `/oauth/token`;
  - dashboard защищён `Content-Security-Policy`;
  - контейнер запускается не от `root`.
- Документация:
  - `README.md` синхронизирован с кодом и остаётся на русском языке;
  - `CODEX.md` содержит полный install/uninstall/reinstall path для Codex;
  - `AGENTS.md` остаётся нейтральной памяткой для любых MCP-клиентов.
- Публикация:
  - Docker package публикуется в GHCR;
  - multi-arch build настроен для `linux/amd64` и `linux/arm64`.
