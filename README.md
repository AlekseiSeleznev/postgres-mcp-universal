# postgres-mcp-universal

`postgres-mcp-universal` — HTTP MCP-шлюз для PostgreSQL. Он поднимает endpoint `POST /mcp`, web dashboard для управления подключениями и набор из 23 MCP tools для запросов, схемы и мониторинга PostgreSQL.

Основная модель проекта в `v1.0.0`: единая Docker-схема на bridge-сети с явным пробросом порта на Linux, Windows и macOS. Сам сервер клиент-агностичен; для Codex предусмотрен отдельный удобный install-path.

![Dashboard preview](docs/dashboard-preview.png)

## Что делает проект

- подключать несколько PostgreSQL-баз одновременно
- маршрутизировать активную базу по MCP session id
- отдавать 23 MCP tools через `/mcp`
- хранить список подключённых баз в Docker volume
- поднимать dashboard на `/dashboard`
- работать без Bearer auth по умолчанию
- включать Bearer auth вручную через `PG_MCP_API_KEY`
- автоматически регистрироваться в Codex через `codex mcp add`, если `codex` CLI доступен
- содержит runbook-файлы:
  - `CODEX.md` для Codex;
  - `AGENTS.md` для любого другого MCP-клиента.

## Требования

| Компонент | Требуется | Примечание |
|-----------|-----------|------------|
| Docker Engine / Docker Desktop | Да | Docker daemon должен быть запущен |
| Docker Compose V2 | Да | Нужен именно `docker compose` |
| `curl` | Желательно | Используется для быстрых health-checks на POSIX |
| PowerShell на Windows | Желательно | Нужен для `install.ps1` / `uninstall.ps1`, но можно запускать через `.cmd` wrappers |
| Codex CLI | Опционально | Нужен только для автоматической регистрации в Codex |

## Быстрый старт

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

`install.cmd` запускает `install.ps1` через `ExecutionPolicy Bypass`, поэтому на чистой Windows-машине не нужно отдельно разбираться с политикой выполнения PowerShell.
Если нужен прямой вызов PowerShell-скрипта, используйте `powershell -ExecutionPolicy Bypass -File .\install.ps1`.
Важно: на Windows Docker Desktop должен быть запущен до старта установки.

## Что делает установка

Основной install-flow:

- создаёт `.env` из `.env.example`, если файла ещё нет
- принудительно оставляет `PG_MCP_API_KEY=` пустым для no-auth режима по умолчанию
- удаляет legacy `docker-compose.override.yml`, если он остался от старых host-networking версий
- собирает и запускает контейнер через `docker compose up -d --build --remove-orphans`
- ждёт успешный ответ `/health`
- на Linux через `setup.sh` устанавливает и сразу запускает `postgres-mcp-universal.service` без forced rebuild на каждом boot
- на Windows может запускаться через `install.cmd`, который снимает проблему execution policy
- при наличии `codex` автоматически регистрирует MCP server `postgres-universal`

## Подключение MCP-клиента

Базовый клиент-агностичный контракт:

- transport: Streamable HTTP
- endpoint: `POST http://localhost:8090/mcp`
- auth: по умолчанию выключен

Если вы используете другой MCP-клиент, ему нужен только URL `http://localhost:8090/mcp`, а при включённом auth — Bearer header с `PG_MCP_API_KEY`.

## Подключение через Codex

Если `codex` уже установлен, `setup.sh` и `install.ps1` попытаются зарегистрировать MCP server автоматически.

Ручная регистрация:

```bash
codex mcp remove postgres-universal >/dev/null 2>&1 || true
codex mcp add postgres-universal --url http://localhost:8090/mcp
codex mcp get postgres-universal
```

Если вы вручную включили Bearer auth:

```bash
export PG_MCP_API_KEY=your-secret
codex mcp remove postgres-universal >/dev/null 2>&1 || true
codex mcp add postgres-universal --url http://localhost:8090/mcp --bearer-token-env-var PG_MCP_API_KEY
```

## Проверка после установки

Минимальная проверка:

```bash
curl http://localhost:8090/health
```

Проверка доступности MCP endpoint:

```bash
curl -X POST http://localhost:8090/mcp
```

Ожидаемо получить не `404`, а транспортный ответ MCP-сервера, обычно `400` на пустой запрос.

После этого:

1. Откройте `http://localhost:8090/dashboard`
2. Добавьте первое PostgreSQL-подключение
3. Подключите нужный MCP-клиент к `http://localhost:8090/mcp`

Пример первого подключения через MCP:

```text
connect_database(
  name="mydb",
  uri="postgresql://user:pass@host:5432/dbname"
)
```

Tool `connect_database` также принимает alias `connection_string`.

## Ручная установка

### Универсальный путь

```bash
cp .env.example .env
docker compose up -d --build
```

Если вы меняете порт, обновите `PG_MCP_PORT` в `.env` перед запуском.

## Dashboard

Dashboard доступен по адресу:

```text
http://localhost:8090/dashboard
```

Он умеет:

- добавлять и удалять подключения к PostgreSQL
- редактировать URI подключения
- переключать активную базу по умолчанию
- выбирать `unrestricted` или `restricted` access mode
- показывать встроенную документацию на русском и английском
- работать без вшивания API key в HTML

Встроенная документация dashboard находится на:

```text
/dashboard/docs
```

## MCP tools

Полный автогенерируемый каталог: [docs/mcp-tool-catalog.md](docs/mcp-tool-catalog.md)

### Управление базами

| Tool | Назначение |
|------|------------|
| `connect_database` | подключение новой базы, принимает `uri` или `connection_string` |
| `disconnect_database` | отключение базы |
| `switch_database` | переключение активной базы для текущей сессии |
| `list_databases` | список зарегистрированных баз |
| `get_server_status` | статус gateway, пулов и сессий |

### Запросы

| Tool | Назначение |
|------|------------|
| `execute_sql` | выполнение SQL |
| `explain_query` | `EXPLAIN ANALYZE` с планом выполнения |

### Навигация по схеме

| Tool | Назначение |
|------|------------|
| `list_schemas` | список схем |
| `list_tables` | таблицы и views |
| `get_table_info` | колонки, ключи, индексы, размеры |
| `list_indexes` | индексы и статистика использования |
| `list_functions` | функции и процедуры |

### Мониторинг

| Tool | Назначение |
|------|------------|
| `db_health` | версия, uptime, соединения, cache ratio, deadlocks |
| `active_queries` | активные запросы |
| `table_bloat` | оценка bloat |
| `vacuum_stats` | vacuum/autovacuum статистика |
| `lock_info` | блокировки и blocked queries |

### Расширенный мониторинг

| Tool | Назначение |
|------|------------|
| `pg_overview` | верхнеуровневая сводка по PostgreSQL |
| `pg_activity` | activity и blocked/blocking пары |
| `pg_table_stats` | статистика таблиц по схемам |
| `pg_index_stats` | статистика индексов |
| `pg_replication` | состояние репликации |
| `pg_schemas` | пользовательские схемы и число таблиц |

## Конфигурация

Все настройки читаются из `.env` и переменных окружения с префиксом `PG_MCP_`.

| Переменная | По умолчанию | Назначение |
|------------|--------------|------------|
| `PG_MCP_PORT` | `8090` | порт HTTP gateway |
| `PG_MCP_LOG_LEVEL` | `INFO` | уровень логирования |
| `PG_MCP_DATABASE_URI` | пусто | URI для автоподключения одной базы при старте |
| `PG_MCP_ACCESS_MODE` | `unrestricted` | access mode по умолчанию |
| `PG_MCP_QUERY_TIMEOUT` | `30` | timeout запросов в секундах |
| `PG_MCP_POOL_MIN_SIZE` | `2` | минимальный размер пула |
| `PG_MCP_POOL_MAX_SIZE` | `10` | максимальный размер пула |
| `PG_MCP_METADATA_CACHE_TTL` | `600` | TTL кэша метаданных |
| `PG_MCP_SESSION_TIMEOUT` | `28800` | idle timeout сессии |
| `PG_MCP_API_KEY` | пусто | Bearer auth для `/mcp` и dashboard API |
| `PG_MCP_RATE_LIMIT_ENABLED` | `true` | включает in-memory rate limiting для `/mcp`, `/api/*`, `/oauth/token` |
| `PG_MCP_RATE_LIMIT_WINDOW_SECONDS` | `60` | окно rate limiting в секундах |
| `PG_MCP_RATE_LIMIT_MCP_REQUESTS` | `60` | лимит запросов к `/mcp` на IP в одном окне |
| `PG_MCP_RATE_LIMIT_API_REQUESTS` | `60` | лимит запросов к `/api/*` на IP в одном окне |
| `PG_MCP_RATE_LIMIT_OAUTH_REQUESTS` | `10` | лимит запросов к `/oauth/token` на IP в одном окне |
| `PG_MCP_ENABLE_SIMPLE_TOKEN_ENDPOINT` | `false` | включает совместимый `/oauth/token` endpoint |
| `PG_MCP_STATE_FILE` | `/data/db_state.json` | путь к файлу состояния подключённых баз |

## HTTP endpoints

| Endpoint | Метод | Назначение |
|----------|-------|------------|
| `/mcp` | `POST` | MCP Streamable HTTP transport |
| `/health` | `GET` | health check и состояние пулов |
| `/dashboard` | `GET` | web dashboard |
| `/dashboard/docs` | `GET` | встроенная документация |
| `/api/databases` | `GET` | список баз |
| `/api/connect` | `POST` | подключение новой базы |
| `/api/disconnect` | `POST` | отключение базы |
| `/api/edit` | `POST` | редактирование подключения |
| `/api/switch` | `POST` | переключение активной базы |
| `/.well-known/oauth-protected-resource` | `GET` | RFC 9728 metadata |
| `/.well-known/oauth-authorization-server` | `GET` | RFC 8414 metadata |
| `/oauth/token` | `POST` | совместимый token endpoint, по умолчанию выключен |

Dashboard API требует Bearer token только если задан `PG_MCP_API_KEY`.
Для `/mcp`, `/api/*` и `/oauth/token` действует in-memory rate limiting; при превышении сервер отвечает `429` и заголовком `Retry-After`.

## Архитектура

Основные компоненты:

- `gateway/gateway/server.py` — Starlette ASGI app, MCP transport, cleanup loop
- `gateway/gateway/mcp_server.py` — регистрация MCP tools и dispatch
- `gateway/gateway/pg_pool.py` — `asyncpg` pools и session routing
- `gateway/gateway/db_registry.py` — хранение списка баз и активной базы
- `gateway/gateway/web_ui.py` — dashboard endpoints
- `gateway/gateway/web_ui_content.py` — HTML dashboard и встроенная документация

Основной контейнер собирается из `gateway/Dockerfile`.  
Состояние подключений хранится в volume `gw-data`, внутри контейнера — в `/data/db_state.json`.

## Тестирование

Подготовка из чистого клона:

```bash
python3 -m venv gateway/.venv
. gateway/.venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r gateway/requirements-dev.txt
```

Локальный прогон:

```bash
cd gateway
python -m pytest -q
```

Прогон с coverage-флагами, как в CI:

```bash
cd gateway
python -m pytest tests/ -v --cov=gateway --cov-branch --cov-report=term-missing --cov-fail-under=100
```

Smoke-checks:

```bash
./tools/ci-smoke.sh
```

Повторная проверка install-flow без повторной регистрации в Codex:

```bash
MCP_SETUP_CI=1 ./setup.sh
```

На CI выполняются:

- Python tests на Linux и Windows
- coverage gate `100%`
- `tools/ci-smoke.sh` на POSIX
- `tools/ci-smoke.ps1` на Windows
- Linux fresh-install smoke с реальным `MCP_SETUP_CI=1 ./setup.sh`
- Windows static install smoke через PowerShell path и bash compatibility checks

## Удаление и чистый повторный подъём

### Bash / POSIX

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

После этого:

1. выйдите из каталога репозитория
2. удалите каталог проекта
3. заново клонируйте репозиторий
4. снова запустите установку
5. отдельно прогоните `MCP_SETUP_CI=1 ./setup.sh`, чтобы повторить CI-friendly install path без пере-регистрации в Codex
6. снова проверьте `/health`, `/dashboard`, `/mcp` и тесты

## Поведение после перезагрузки

- контейнер поднимается через `restart: always`
- на Linux `setup.sh` устанавливает и сразу запускает systemd service `postgres-mcp-universal` без forced rebuild
- ожидаемый статус `systemctl status postgres-mcp-universal`: `active (exited)`, потому что это `oneshot` wrapper вокруг `docker compose up -d`, а сам gateway живёт внутри контейнера
- регистрация MCP в Codex сохраняется в локальной конфигурации Codex
- на Windows для автоподъёма Docker должен стартовать вместе с системой

## Troubleshooting

| Проблема | Что проверить |
|----------|---------------|
| `docker compose` не найден | нужен Docker Compose V2 |
| Docker daemon не запущен | запустите Docker Engine или Docker Desktop |
| `codex` не найден | MCP registration в Codex выполните вручную, сам сервер всё равно запустится |
| `/health` не отвечает | `docker compose logs --tail=100` |
| занят порт `8090` | измените `PG_MCP_PORT` в `.env` и повторите установку |
| MCP-клиент не проходит auth | проверьте `PG_MCP_API_KEY` и Bearer header |
| сервер отвечает `429 Too Many Requests` | проверьте rate limiting переменные `PG_MCP_RATE_LIMIT_*` |
| после перезагрузки на Linux gateway не стартует | `systemctl status postgres-mcp-universal` |
| после перезагрузки на Windows gateway не стартует | включите автозапуск Docker Desktop |

## Совместимость

- PostgreSQL 14, 15, 16, 17, 18
- Python 3.12+
- Docker / Docker Compose V2
- Linux, Windows, macOS

## Лицензия

[MIT](LICENSE)
