# lead_parser

Парсер открытых Telegram-чатов для поиска потенциальных заявок на:
- разработку AI-ботов
- разработку Telegram-ботов
- автоматизацию и проекты на n8n

Пайплайн:
1. Telegram parser получает новые сообщения из заданных чатов.
2. Regex prefilter отбрасывает очевидно нерелевантные сообщения.
3. Кандидаты отправляются в AMQP очередь.
4. AI worker классифицирует сообщение через OpenRouter (LLM).
5. Если это реальный лид, уходит webhook-уведомление в ваш CF Worker.

## Установка

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Если установка падает на `tgcrypto` (особенно на Python 3.12), поставьте системные пакеты сборки:

```bash
sudo apt update
sudo apt install -y python3-dev build-essential
```

После этого повторите установку зависимостей.

## Конфигурация

Скопируйте пример:

```bash
cp .env.example .env
```

Заполните как минимум:
- API_ID
- API_HASH
- TG_SOURCE_CHATS
- AMQP_URL

Для AI worker дополнительно:
- OPENROUTER_API_KEY
- NOTIFIER_WEBHOOK_URL

## Запуск

Telegram parser:

```bash
python -m parsers.tg_userbot
```

AI worker:

```bash
python -m workers.ai_worker
```

## TODO (ближайшие шаги)

1. Добавить дедупликацию по message_link/message_id.
2. Вынести regex-словарь в отдельный конфиг (быстрый тюнинг без деплоя).
3. Добавить rate limit/retry policy для webhook.
4. Добавить тесты на prefilter и парсинг payload.
5. Добавить отдельную очередь для DLQ (ошибки LLM/webhook).