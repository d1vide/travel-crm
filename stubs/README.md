# Заглушка оплаты

Отдельный HTTP-сервис на FastAPI и PostgreSQL. Карты и реальные платежи не используются. Браузер выбирает учебный исход: успех, отказ или тайм-аут; CRM получает подтверждённое состояние через адаптер.

Запуск в составе проекта: `python scripts/init_env.py`, затем `docker compose up --build`. Для существующего `.env` добавить новые настройки командой `python scripts/init_env.py --add-payment-settings`. Значения секретов не выводятся и не заменяются.

Нативный запуск из корня: `backend/.venv/Scripts/python.exe -m stubs.bootstrap` (Windows) либо `backend/.venv/bin/python -m stubs.bootstrap` (Linux). Нужны корневой `.env` и PostgreSQL 16. Сервис слушает 8010; миграции создают отдельную схему `payment_stub`, которую можно изменить через `STUB_SCHEMA`. Перезапуск не сбрасывает операции.

`/v1/payments` и `/v1/payments/{id}` доступны только с общим серверным ключом. Через nginx/Vite публикуется только `/payment-stub/pay/{token}`. Не передавать `PAYMENT_STUB_KEY` во фронтенд. Access logging отключён, публичные ответы защищены no-store/no-referrer. POST формы проверяет Origin, заданный PUBLIC_APP_URL.

Полный протокол, права, повторы и обработка тайм-аутов — в [инструкции оплаты](../docs/api/payments-integration.md).
