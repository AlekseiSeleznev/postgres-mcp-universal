# Инструкции для AI-ассистентов (Claude Code / Codex / Cursor)

Протокол работы AI-ассистента с `postgres-mcp-universal`. Claude Code автоматически подхватывает `CLAUDE.md` при открытии репозитория; Codex читает `AGENTS.md`.

---

## TL;DR

Любая задача по PostgreSQL (запросы, инспекция схемы, диагностика производительности, планирование миграций) **делается через MCP-сервер `postgres-mcp-universal`** (`http://localhost:8090/mcp`).

**Не гадай структуру таблиц и не пиши SQL из памяти. Сначала вызывай MCP. Если инструмент недоступен — скажи об этом пользователю, не имитируй ответ.**

---

## Распознавание намерения — когда маршрутизировать сюда

**Фразы, пинящие сессию на этот MCP:**
- «Postgres / PostgreSQL / PG / постгрес», «используем Postgres `<имя>`», «работаем с PG `<имя>`», «подключись к Postgres `<имя>`», «в базе postgres `<имя>`», «switch to Postgres `<name>`».

**Postgres-терминология — любой маркер ниже → этот MCP:**
`postgresql://` / `postgres://` DSN, `pg_*` таблицы/views (`pg_stat_*`, `pg_index`, `pg_catalog`), VACUUM, ANALYZE (SQL), EXPLAIN (ANALYZE), psql, WAL, hot-standby, replication slot, схема `public`/`pgcrypto`/`uuid-ossp`.

**Типовые имена баз:** `main`, `prod`, `staging`, `dev`, `analytics`, `warehouse`, `<app>_prod`, `<app>_db`, lowercase snake_case (без 1С-контекста).

**Что делать, когда пользователь назвал базу** («используем Postgres main»):
1. `list_databases` — если `main` есть → `switch_database name=main`.
2. Если нет — спросить `postgresql://…` URI или classic `connection_string` и вызвать `connect_database` (по умолчанию `access_mode=restricted`).

**Если пользователь сказал просто «база X»** без явного указания системы — вызови `list_databases` здесь; если `X` есть — работаем с ним, если нет — честно сообщи «в Postgres-MCP такой базы нет» и попроси уточнения. Не выдумывай подключение.

---

## Pre-flight перед любой задачей

1. `list_databases` — есть ли активная БД. Если пусто — запроси у пользователя URI и вызови `connect_database`. Дефолтный профиль — restricted (read-only).
2. `get_server_status` — здоровье пула.

---

## Чтение данных

- **Схема:** `list_schemas` → `list_tables` → `get_table_info` (колонки, PK/FK, индексы). **Никогда не пиши SQL против таблицы до вызова `get_table_info`** — подтверди реальные имена колонок.
- **Запрос:** `execute_sql` для `SELECT/EXPLAIN/SHOW/WITH`. Дорогие аналитические вещи обворачивай в `explain_query` с `analyze=false`. Не отправляй `ANALYZE` в restricted-режиме — это фактически выполняет запрос.

---

## Диагностика производительности

1. **Server-wide:** `pg_overview` / `db_health` — commits, rollbacks, deadlocks, cache hit, WAL, replication.
2. **Узкое место:** `active_queries` / `pg_activity` → `lock_info` (кто кого блокирует) → `table_bloat` + `vacuum_stats` (нужен ли VACUUM) → `list_indexes` / `pg_index_stats` (отсортировано по `scan_count` ASC — кандидаты на DROP INDEX) → `pg_table_stats`.
3. **Реплики:** `pg_replication` — лаг (time/bytes), слоты репликации.

---

## Записи / миграции (DDL + DML)

- **Сначала проверь access-mode БД.** Restricted профиль отклоняет `INSERT/UPDATE/DELETE/ALTER/DROP/CREATE`.
- **Для каждого destructive SQL:** покажи пользователю итоговый текст, получи явное «да», только потом вызывай `execute_sql`. Не исполняй молча.
- **Для нетривиальных изменений:** сначала `explain_query` (без `ANALYZE` если страшно).
- **Миграции:** `get_table_info` → собрать SQL → (опционально `explain_query` для тяжёлых индексов) → показать пользователю → подтверждение → `execute_sql` → повторный `get_table_info` чтобы показать результат.

---

## Категории инструментов

| Категория | Инструменты |
|---|---|
| Жизненный цикл | `connect_database`, `disconnect_database`, `switch_database`, `list_databases`, `get_server_status` |
| Запросы | `execute_sql`, `explain_query` |
| Схема | `list_schemas`, `list_tables`, `get_table_info`, `list_indexes`, `list_functions` |
| Здоровье (базовое) | `db_health`, `active_queries`, `table_bloat`, `vacuum_stats`, `lock_info` |
| Мониторинг | `pg_overview`, `pg_activity`, `pg_table_stats`, `pg_index_stats`, `pg_replication`, `pg_schemas` |

---

## Готовые MCP-prompts

Сервер отдаёт `prompts/list`:

- **connect_and_inspect** — подключиться и показать обзор сервера.
- **describe_table** (arg: `table`) — колонки, индексы, bloat, use-stats.
- **safe_query** (arg: `query`) — EXPLAIN → оценить план → `execute_sql` с LIMIT.
- **diagnose_performance** — триаж по уровням: overview → активные запросы → локи → bloat → индексы → реплика.
- **propose_migration** (arg: `intent`) — план миграции с подтверждением перед исполнением.

---

## Частые ошибки (не наступать)

1. **Читай `inputSchema` из `tools/list` перед первым вызовом.** Большинство tool-level ошибок (`'X' is a required property`) — из-за выдуманных имён аргументов.
2. **`connect_database`** принимает **либо** `uri`, **либо** `connection_string` (одно из двух обязательно). `access_mode` по умолчанию `restricted` (read-only). `unrestricted` передавай только когда пользователь явно просит записи.
3. **`execute_sql` в restricted-профиле** отказывает в `INSERT/UPDATE/DELETE/ALTER/DROP/CREATE/TRUNCATE`. Перед записью проверяй `access_mode` через `list_databases`; если запись нужна — скажи пользователю «переподключиться с `access_mode=unrestricted`».
4. **`explain_query.analyze=true` реально выполняет запрос.** По умолчанию `analyze=false`; в restricted никогда не ставь `true`.
5. **`schema` по умолчанию `public`** в `list_tables/list_indexes/list_functions/get_table_info/table_bloat/vacuum_stats/pg_table_stats/pg_index_stats`. Если объекты в другой схеме — указывай явно, не угадывай.
6. **Активная БД — per-session.** `switch_database` один раз на `Mcp-Session-Id`. Параллельные сессии могут работать с разными БД одновременно и независимо.
7. **Кеш метаданных — 600s TTL.** После `ALTER/CREATE/DROP` повторно дёргай `get_table_info`; предупреди пользователя о возможном лаге.
8. **HTTP 404 или зависшая сессия** — gateway удалил устаревшую сессию. Переинициализируй (`initialize` + `notifications/initialized`), не ретраи со старым `Mcp-Session-Id`.
9. **Перед деструктивным SQL** (`UPDATE/DELETE/DROP/ALTER/CREATE/TRUNCATE`) — показать итоговый SQL пользователю, получить явное «да», только потом `execute_sql`.

---

## Поведение при сбоях

| Ситуация | Поведение |
|---|---|
| `list_databases` пуст | Запросить URI и вызвать `connect_database` |
| DDL/DML отклонён (restricted) | Сказать пользователю: «БД в read-only профиле; чтобы сделать запись — переподключиться с `access_mode=unrestricted`» |
| EXPLAIN вернул очень дорогой план | Предложить переписать запрос / добавить индекс, НЕ выполнять бездумно |
| `get_server_status` показывает красный пул | Сказать какая БД отваливается, не гадать данные |
| Кеш метаданных устарел (600s TTL) | После ALTER/CREATE/DROP делать `get_table_info` повторно, предупредить о возможном лаге |
