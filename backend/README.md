# Бэкенд TravelCRM

Основа по #9: FastAPI, PostgreSQL 16, SQLAlchemy 2, Alembic, демонстрационные сотрудники и серверная авторизация. Реализованы login, refresh, logout, me и проверки состояния. Доменные таблицы клиентов, заявок, броней и денег добавляются миграциями в задачах соответствующих функций.

## Требования

- Python 3.12 и uv; версии зависимостей закреплены в uv.lock.
- Docker Engine с Compose либо доступный локальный PostgreSQL 16.
- Все команды ниже выполняются из корня репозитория.

## Первый запуск с Docker

```bash
python scripts/init_env.py
docker compose up --build
```

Скрипт создаёт корневой .env со случайными секретами и не перезаписывает существующий файл. Образец полей — в .env.example; плейсхолдер JWT заведомо не принимается сервером. В Compose сейчас только db и backend; frontend/nginx и платёжная заглушка относятся к #24 и #15.

При старте backend выполняет `alembic upgrade head`, затем добавляет демо-пользователей при SEED_DEMO=true и запускает сервер. База использует постоянный том; обычный перезапуск контейнеров сохраняет данные. DB и API публикуются только на 127.0.0.1, по умолчанию 5432 и 8000. Порты переопределяются POSTGRES_PORT/BACKEND_PORT. В контейнере backend работает непривилегированным пользователем.

Адреса:

- http://localhost:8000/docs — документация реально реализованных маршрутов.
- GET /api/health/live — процесс отвечает независимо от состояния БД.
- GET /api/health/ready — соединение с БД и таблица пользователей доступны; иначе единый Error с 503.

Для текущего Vue-каркаса /api уже проксируется на localhost:8000. Форма настоящего входа и вызов выхода на фронтенде подключаются в #11.

## Разработка с uv

```bash
uv sync --directory backend --frozen
docker compose up -d db
uv run --directory backend python -m app.bootstrap
```

Команда bootstrap подходит для повторного запуска: миграции не применяются повторно, seed не создаёт дублей и не меняет существующие пароли/роли. Изменение DEMO_PASSWORD в .env не сбрасывает пароль уже созданного пользователя.

Для горячей перезагрузки после первоначальной подготовки:

```bash
uv run --directory backend alembic upgrade head
uv run --directory backend python -m app.seed
uv run --directory backend uvicorn app.main:create_app --factory --reload --host 127.0.0.1 --port 8000
```

Без Docker сначала создать БД travelcrm в PostgreSQL 16 и указать подключение в корневом .env как `DATABASE_URL=postgresql+psycopg://USER:PASSWORD@127.0.0.1:PORT/travelcrm`. Затем выполнить uv sync и bootstrap, пропустив команду Docker. PostgreSQL и его данные на Windows рекомендуется устанавливать в путь без кириллицы; репозиторий может оставаться в своей папке.

Для новой миграции изменяются ORM-модели и выполняется `uv run --directory backend alembic revision --autogenerate -m "описание"`; полученный SQL проверяется перед коммитом. `Base.metadata.create_all` для запуска приложения не используется. `uv run --directory backend alembic check` проверяет отсутствие расхождения моделей и БД.

## Демо-вход и сессии

| Email | Роль |
|---|---|
| manager@example.com | manager |
| head@example.com | head |
| accountant@example.com | accountant |

Это вымышленные данные. Пароль берётся из DEMO_PASSWORD локального .env. Seed включается только явно; в production он запрещён. Самостоятельной регистрации и административного интерфейса пользователей нет.

- POST /api/auth/login принимает JSON email/password и возвращает AuthResult из контракта 0.2.
- POST /api/auth/refresh использует только cookie refresh_token и возвращает новый access/профиль, ротируя cookie.
- POST /api/auth/logout отзывает семейство refresh-сессии и очищает cookie; повторный выход даёт 204.
- GET /api/auth/me требует Bearer access и возвращает только id/full_name/role.

Access JWT действует 15 минут, проверяются подпись, issuer, audience, срок и обязательные claims; сотрудник должен оставаться активным. Access хранится только в памяти фронтенда. После logout уже выданный access живёт до истечения своего короткого срока; refresh отозван сразу.

В БД хранится SHA-256 refresh и Argon2id-хеш пароля. Refresh действует 7 дней, принадлежит семейству. Повторное использование заменённого токена отзывает семейство. Одновременные запросы refresh сериализуются блокировками PostgreSQL; фронтенд должен сохранять существующий общий refresh для параллельных запросов. Cookie: HttpOnly, SameSite=Strict, Path=/api/auth; Secure обязателен в production. Разрешённые браузерные Origin задаются ALLOWED_ORIGINS; при разработке используются адреса Vite/localhost. Origin другой площадки и Sec-Fetch-Site=cross-site отклоняются.

Зависимости get_current_user/require_roles — основа серверных прав. Ограничения по владельцу клиента/заявки будут реализованы вместе с этими сущностями в #12/#13; выполнение всей FR-01 этим каркасом не заявляется.

## Проверки

Нужна отдельная БД с именем, оканчивающимся на _test. Например, один раз создать её в текущем контейнере:

```bash
docker compose exec db createdb -U travelcrm travelcrm_test
```

PowerShell, с паролем и портом своей локальной БД:

```powershell
$env:TEST_DATABASE_URL = 'postgresql+psycopg://travelcrm:PASSWORD@127.0.0.1:5432/travelcrm_test'
uv run --directory backend pytest -q
uv run --directory backend ruff check .
uv run --directory backend ruff format --check .
```

В Bash используется `export TEST_DATABASE_URL='...'`. Тесты отказываются использовать БД без суффикса _test. Каждый тест создаёт собственную случайную схему и удаляет только её. SQLite и пропуск интеграционных проверок вместо PostgreSQL не используются.

Проверяются миграции вверх/вниз и их повторное применение, отсутствие schema drift, повторный seed, ограничения БД, хеши, сохранение данных после переподключения, роли, истечение/отзыв/ротация токенов, параллельный refresh, Cookie/Origin и соответствие ответов зафиксированному контракту. Секреты и исходный пользовательский ввод в ответы об ошибках не включаются.

## Контракт и следующие шаги

Полная спецификация MVP остаётся в docs/api/openapi.json. Runtime /openapi.json показывает реализованный поднабор auth/health. Его нельзя целиком записывать поверх полной спецификации, удаляя будущие операции. В #26 экспорт из серверных схем должен заменить временный генератор с сохранением всех согласованных маршрутов/моделей; порядок описан в docs/api/README.md. Бизнес-маршруты за пределами этого каркаса пока не зарегистрированы.

Backend и DB готовы для подключения формы входа и последующей разработки клиентов/заявок. Полный запуск Vue/nginx/заглушки, CI, объектные права и финансовые сценарии выполняются в соответствующих задачах.
