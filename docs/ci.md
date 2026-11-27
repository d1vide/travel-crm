# Проверки CI

Workflow `.github/workflows/ci.yml` запускается на каждый PR, push в main и вручную через workflow_dispatch. Четыре независимых задания: backend, frontend, contract, docker. Повторный запуск в той же ветке отменяет предыдущий незавершённый прогон. Доступ workflow ограничен чтением репозитория; публикация образов и деплой не выполняются. Actions закреплены SHA.

## Локальный запуск

Backend (Python 3.12, uv 0.13.8):

```sh
uv sync --directory backend --frozen
cd backend
uv run --frozen ruff check . ../stubs ../scripts
uv run --frozen ruff format --check . ../stubs ../scripts
uv run --frozen pytest -q
```

До pytest задайте TEST_DATABASE_URL на отдельную PostgreSQL 16 с именем БД, заканчивающимся на `_test`. PowerShell: `$env:TEST_DATABASE_URL = 'postgresql+psycopg://USER:PASSWORD@127.0.0.1:PORT/travelcrm_test'`; Bash: `export TEST_DATABASE_URL='...'`. Каждый тест использует собственную случайную схему. В CI PostgreSQL создаётся сервисом job с одноразовой тестовой учётной записью; секреты демонстрационного стенда не используются.

Из корня, с Node 22:

```sh
node --test stubs/checkout.test.mjs
cd frontend
npm ci
npm run lint:check
npm run type-check
npm run test:unit -- --run
npm run build-only
```

`lint:check` проверяет oxlint и eslint без изменения файлов. Существующий `npm run lint` по-прежнему предназначен для автоисправлений.

Контракт, из корня:

```sh
uv run docs/api/validate_contract.py
cd frontend
npm run gen:api
git diff --exit-code -- src/api/schema.d.ts
```

Валидатор проверяет JSON Schema, примеры, реестр операций и актуальность собранного OpenAPI. Backend-тесты сверяют ответы с контрактом и список реализованных HTTP-операций. Полный экспорт OpenAPI из кода остаётся отдельной задачей #26; CI не подменяет спецификацию неполным runtime-экспортом.

Docker, из корня:

```sh
python scripts/init_env.py
docker compose config --quiet
docker compose build
```

В CI dotenv создаётся с новыми случайными значениями в одноразовом runner и не публикуется. Локальный скрипт сохраняет существующий `.env`. Проверка Docker в CI собирает образы; проверка сценария и запуска сервисов описана отдельно в demo-preparation.md и test-report.md.

## Обязательные проверки main

В ruleset `main-review` используются имена backend, frontend, contract, docker. Их изменение в workflow требует одновременного обновления ruleset. Правила удаления и force-push сохраняются, обязательное ревью коллеги не добавляется. Результаты проверки workflow, отрицательного прогона и применения ruleset фиксируются в #25.

Отрицательная проверка: в PR #81 временно изменён заголовок OpenAPI без изменения генератора. Задание contract в [прогоне 46025132781](https://github.com/d1vide/travel-crm/actions/runs/46025132781) завершилось failure. Затем контракт восстановлен; отрицательное изменение отсутствует в итоговом diff. Остальные задания этого прогона отменены последующим push по concurrency.
