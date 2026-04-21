# CODEX.md

> **Правила работы AI-ассистента** (какие инструменты в каком порядке вызывать, когда отказываться вместо выдумывания) описаны в [`AGENTS.md`](AGENTS.md) (секция «Agent protocol»). MCP-сервер также возвращает агрегированный `instructions`-блок при `initialize`, поэтому современные MCP-клиенты подмешивают те же правила в системный контекст автоматически. Ниже — только Codex-специфичные шаги развёртывания.

Подробная инструкция по установке, проверке, удалению и повторному чистому развёртыванию `postgres-mcp-universal` именно для Codex.

## Распознавание намерения — когда маршрутизировать сюда

- **Триггер-фразы**: «Postgres / PostgreSQL / PG / постгрес», «используем Postgres `<имя>`», «работаем с PG `<имя>`», «подключись к Postgres `<имя>`», «в базе postgres `<имя>`», «switch to Postgres `<name>`».
- **Postgres-терминология**: `postgresql://` / `postgres://` DSN, `pg_*` таблицы/views, VACUUM, ANALYZE (SQL), EXPLAIN (ANALYZE), psql, WAL, hot-standby, replication slot, схема `public`/`pgcrypto`/`uuid-ossp`.
- **Типовые имена баз**: `main`, `prod`, `staging`, `dev`, `analytics`, `warehouse`, `<app>_prod`, `<app>_db`, lowercase snake_case.
- **Когда пользователь назвал базу**: `list_databases` → если есть, `switch_database`; иначе попросить `postgresql://…` URI / `connection_string` и `connect_database` (по умолчанию `access_mode=restricted`).
- **«База X» без указания системы** — `list_databases` здесь; если есть — работаем, если нет — честно сказать «в Postgres-MCP такой базы нет» и попросить уточнение. Не выдумывать.

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

## Назначение

`postgres-mcp-universal` — HTTP MCP-шлюз для PostgreSQL. Он запускается в Docker, хранит состояние подключённых баз в volume и при наличии `codex` CLI автоматически регистрируется в Codex как MCP server `postgres-universal`.

## Предварительные требования

### Linux / macOS

- Docker Engine или Docker Desktop с запущенным daemon
- Docker Compose V2
- `curl`
- `codex` CLI в `PATH`, если нужна автоматическая регистрация MCP

### Windows

- Docker Desktop
- PowerShell для `install.ps1`
- `curl`
- `codex` CLI в `PATH`, если нужна автоматическая регистрация MCP

## Чистая установка

### Linux / macOS / Git Bash / WSL2

```bash
git clone https://github.com/AlekseiSeleznev/postgres-mcp-universal.git
cd postgres-mcp-universal
./setup.sh
```

### Windows PowerShell

```powershell
git clone https://github.com/AlekseiSeleznev/postgres-mcp-universal.git
cd postgres-mcp-universal
.\install.cmd
```

`install.cmd` запускает `install.ps1` через `ExecutionPolicy Bypass`, поэтому это самый беспроблемный путь для чистой Windows-машины.
Если нужен прямой вызов PowerShell, используйте `powershell -ExecutionPolicy Bypass -File .\install.ps1`.

## Что делает установка

`setup.sh` и `install.ps1` используют одинаковую базовую модель, а `install.cmd` просто запускает `install.ps1` в Windows без ручной настройки execution policy:

1. Проверяют Docker / Compose и состояние daemon.
2. Создают `.env` из `.env.example`, если нужно.
3. Оставляют `PG_MCP_API_KEY=` пустым для no-auth режима по умолчанию.
4. Удаляют legacy `docker-compose.override.yml`, если он остался от старых host-networking версий.
5. Запускают `docker compose up -d --build --remove-orphans`.
6. Ждут успешный ответ `/health`.
7. На Linux `setup.sh` устанавливает и сразу запускает systemd unit без forced rebuild на каждый boot.
8. Если найден `codex`, выполняют регистрацию:

```bash
codex mcp remove postgres-universal >/dev/null 2>&1 || true
codex mcp add postgres-universal --url http://localhost:${PG_MCP_PORT:-8090}/mcp
```

## Проверка после установки

```bash
curl http://localhost:8090/health
codex mcp get postgres-universal
curl -X POST http://localhost:8090/mcp
```

Ожидаемо на пустой `POST /mcp` получить транспортный ответ MCP-сервера, а не `404`.

Дальше:

1. Откройте `http://localhost:8090/dashboard`.
2. Добавьте PostgreSQL-подключение через dashboard или MCP tool `connect_database`.
3. Используйте MCP server `postgres-universal` в Codex.

Tool `connect_database` принимает и `uri`, и alias `connection_string`.

## Сценарий с Bearer auth

По умолчанию `setup.sh` и `install.ps1` очищают `PG_MCP_API_KEY`, поэтому этот раздел нужен только для ручного сценария.

```bash
export PG_MCP_API_KEY=your-secret
codex mcp remove postgres-universal >/dev/null 2>&1 || true
codex mcp add postgres-universal --url http://localhost:8090/mcp --bearer-token-env-var PG_MCP_API_KEY
```

Важно: Codex хранит имя переменной окружения, а не копирует сам секрет. Значит `PG_MCP_API_KEY` должен присутствовать в окружении в момент запуска Codex.

## Поведение после перезагрузки

- контейнер поднимается через `restart: always`
- на Linux `setup.sh` устанавливает и сразу запускает `postgres-mcp-universal.service` без forced rebuild на boot
- ожидаемый статус `systemctl status postgres-mcp-universal`: `active (exited)`, потому что unit одноразово вызывает `docker compose up -d`, а сам gateway живёт внутри контейнера
- регистрация в Codex остаётся в локальной конфигурации Codex
- на Windows автоматический подъём зависит от автозапуска Docker Desktop

## Безопасное удаление

### Linux / macOS / Git Bash / WSL2

```bash
docker compose down -v --rmi local || true
codex mcp remove postgres-universal || true
sudo systemctl disable --now postgres-mcp-universal.service || true
sudo rm -f /etc/systemd/system/postgres-mcp-universal.service
sudo systemctl daemon-reload
```

### Windows PowerShell

```powershell
.\uninstall.cmd
```

`uninstall.cmd` запускает `uninstall.ps1` через `ExecutionPolicy Bypass`.

### Быстрое удаление на Windows через Git Bash

```bash
docker compose down -v --rmi local || true
codex mcp remove postgres-universal || true
```

После этого:

1. Выйдите из каталога репозитория.
2. Удалите каталог проекта.
3. Убедитесь, что `codex mcp get postgres-universal` больше не находит регистрацию.
4. Если удаляете из проводника Windows, сначала закройте PowerShell, CMD и редакторы, открытые внутри каталога репозитория.

## Полный clean reinstall cycle

1. Удалите проект по разделу «Безопасное удаление».
2. Снова клонируйте репозиторий из GitHub.
3. Запустите `./setup.sh` или `.\install.cmd`.
4. Проверьте:
   - `curl http://localhost:8090/health`
   - `http://localhost:8090/dashboard`
   - `codex mcp get postgres-universal`
   - `MCP_SETUP_CI=1 ./setup.sh`
   - `python3 -m venv gateway/.venv && . gateway/.venv/bin/activate && python -m pip install --upgrade pip && python -m pip install -r gateway/requirements-dev.txt`
   - `cd gateway && python -m pytest tests/ -v --cov=gateway --cov-branch --cov-report=term-missing --cov-fail-under=100`
   - `./tools/ci-smoke.sh`

## Troubleshooting

- `docker compose` не найден: нужен Docker Compose V2
- Docker daemon не запущен: запустите Docker Engine или Docker Desktop
- `codex` не найден: установка завершится, но MCP registration нужно выполнить вручную
- `/health` не отвечает: проверьте `docker compose logs --tail=100`
- занят порт `8090`: измените `PG_MCP_PORT` в `.env` и повторите установку
- Codex не проходит auth: проверьте `PG_MCP_API_KEY` и `--bearer-token-env-var`
- сервер отвечает `429`: при локальной отладке проверьте `PG_MCP_RATE_LIMIT_*` или временно установите `PG_MCP_RATE_LIMIT_ENABLED=false`
- после перезагрузки на Linux gateway не стартует: проверьте `systemctl status postgres-mcp-universal`
- после перезагрузки на Windows gateway не стартует: включите автозапуск Docker Desktop
