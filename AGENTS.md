# AGENTS.md

Нейтральная памятка для любых MCP-клиентов и агентов, работающих с `postgres-mcp-universal`.

## Назначение проекта

`postgres-mcp-universal` — HTTP MCP-шлюз для PostgreSQL. Основной сценарий: установка через `setup.sh` или `install.ps1`, запуск в Docker, управление подключениями через dashboard и подключение любого MCP-клиента к `http://localhost:8090/mcp`.

## Подключение MCP-клиента

- transport: Streamable HTTP
- endpoint: `POST http://localhost:8090/mcp`
- без auth: достаточно URL
- с auth: нужен заголовок `Authorization: Bearer <PG_MCP_API_KEY>`

Клиент-специфичные шаги здесь намеренно не описываются. Для подробного Codex-path используйте `CODEX.md`.

## Источники истины

- [README.md](README.md) — пользовательская инструкция по установке, запуску, проверке и troubleshooting
- [CODEX.md](CODEX.md) — подробная инструкция именно для Codex, включая install/uninstall/reinstall cycle
- [setup.sh](setup.sh) — основной bash install-flow
- [install.cmd](install.cmd) — Windows wrapper для запуска `install.ps1` без ручной настройки execution policy
- [install.ps1](install.ps1) — нативный Windows PowerShell install-flow
- [uninstall.cmd](uninstall.cmd) — Windows wrapper для запуска `uninstall.ps1`
- [uninstall.ps1](uninstall.ps1) — Windows-friendly remove-flow
- [.github/workflows/ci.yml](.github/workflows/ci.yml) — фактические CI-проверки
- [.github/workflows/docker-publish.yml](.github/workflows/docker-publish.yml) — публикация Docker package в GHCR

## Ключевые файлы кода

- `gateway/gateway/server.py` — ASGI app, MCP transport, auth, dashboard docs route
- `gateway/gateway/mcp_server.py` — регистрация MCP tools
- `gateway/gateway/pg_pool.py` — `asyncpg` pools и session routing
- `gateway/gateway/db_registry.py` — реестр подключённых баз
- `gateway/gateway/web_ui.py` — dashboard API
- `gateway/gateway/web_ui_content.py` — HTML dashboard и встроенная документация

## Что проверять после изменений

- `cd gateway && python -m pytest tests/ -v --cov=gateway --cov-branch --cov-report=term-missing --cov-fail-under=100`
- `./tools/ci-smoke.sh`
- при наличии PowerShell: `./tools/ci-smoke.ps1`
- при изменениях install-flow: `./setup.sh`, `MCP_SETUP_CI=1 ./setup.sh`, `./install.ps1`

## Agent protocol (правила работы для AI-клиента)

Этот раздел — самодостаточный source of truth для любого AI-клиента. Те же правила gateway также публикует в `initialize.instructions`; текст хранится в `gateway/gateway/mcp_server.py::AGENT_INSTRUCTIONS`.

Коротко:

- **Intent recognition.** Фразы «используем Postgres `<имя>`», «работаем с PG `<имя>`», «подключись к Postgres `<имя>`», «Postgres / PostgreSQL / PG / постгрес», любые PG-термины (`postgresql://`, `pg_*`, VACUUM, ANALYZE, EXPLAIN, WAL, replication slot, схема `public`) → **этот MCP**. При упоминании базы: `list_databases` → если есть, `switch_database`; иначе попросить `postgresql://` URI и `connect_database` (default `access_mode=restricted`). Если пользователь сказал «база X» без указания системы — `list_databases`; если есть — работаем, если нет — честно сказать «в Postgres-MCP такой базы нет», не выдумывать.
- **Все PostgreSQL-задачи — через MCP `postgres-mcp-universal`** (`http://localhost:8090/mcp`). Не писать SQL против таблицы до `get_table_info`.
- **Pre-flight:** `list_databases` → если пусто, `connect_database` → `get_server_status`.
- **Read path:** `list_schemas` → `list_tables` → `get_table_info` → `execute_sql`/`explain_query`.
- **Diagnostics:** `pg_overview` / `db_health` сначала, затем `active_queries`/`pg_activity`/`lock_info`/`table_bloat`/`pg_index_stats`.
- **Destructive SQL** (DDL + DML) — ТОЛЬКО после явного «да» пользователя. В restricted-профиле — отказ.
- **ANALYZE в EXPLAIN** действительно выполняет запрос; не использовать в restricted-режиме и по умолчанию `analyze=false`.
- **Fallback запрещён:** если бэкенд недоступен или БД не подключена — сообщить пользователю, не писать SQL из памяти.
- **Готовые сценарии** через `prompts/list`: `connect_and_inspect`, `describe_table`, `safe_query`, `diagnose_performance`, `propose_migration`.

### Частые ошибки (не наступать)

1. **Читай `inputSchema` из `tools/list` перед первым вызовом.** Большинство tool-level ошибок (`'X' is a required property`) — из-за выдуманных имён аргументов.
2. **`connect_database`** принимает **либо** `uri`, **либо** `connection_string` (одно из двух обязательно). `access_mode` по умолчанию `restricted` (read-only). `unrestricted` передавай только когда пользователь явно просит записи.
3. **`execute_sql` в restricted-профиле** отказывает в `INSERT/UPDATE/DELETE/ALTER/DROP/CREATE/TRUNCATE`. Перед записью проверяй `access_mode` через `list_databases`; если запись нужна — скажи пользователю «переподключиться с `access_mode=unrestricted`».
4. **`explain_query.analyze=true` реально выполняет запрос.** По умолчанию `analyze=false`; в restricted никогда не ставь `true`.
5. **`schema` по умолчанию `public`** в `list_tables/list_indexes/list_functions/get_table_info/table_bloat/vacuum_stats/pg_table_stats/pg_index_stats`. Если объекты в другой схеме — указывай явно, не угадывай.
6. **Активная БД — per-session.** `switch_database` один раз на `Mcp-Session-Id`. Параллельные сессии могут работать с разными БД одновременно и независимо.
7. **Кеш метаданных — 600s TTL.** После `ALTER/CREATE/DROP` повторно дёргай `get_table_info`; предупреди пользователя о возможном лаге.
8. **HTTP 404 или зависшая сессия** — gateway удалил устаревшую сессию. Переинициализируй (`initialize` + `notifications/initialized`), не ретраи со старым `Mcp-Session-Id`.
9. **Перед деструктивным SQL** (`UPDATE/DELETE/DROP/ALTER/CREATE/TRUNCATE`) — показать итоговый SQL пользователю, получить явное «да», только потом `execute_sql`.
