import os
import sys
from pyrogram import Client, filters
from pyrogram.types import Message
from dotenv import load_dotenv

# 1. Динамически определяем абсолютный путь до корня проекта (папка lead_parser)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 2. Добавляем корень в пути, чтобы Python мог импортировать папку core
sys.path.append(BASE_DIR)

from core.rabbitmq import publish_lead

# 3. Загружаем секреты из .env
load_dotenv(os.path.join(BASE_DIR, '.env'))

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")

# 4. Инициализируем клиента.
# Никаких прокси! Указываем workdir, чтобы скрипт нашел my_account.session в корне
app = Client(
    "my_account",
    api_id=API_ID,
    api_hash=API_HASH,
    workdir=BASE_DIR
)

# РЕЖИМ РЕНТГЕНА: слушаем абсолютно все текстовые сообщения (убрали ограничение filters.group)
@app.on_message(filters.text)
async def handle_new_message(client: Client, message: Message):
    try:
        # Безопасно пытаемся получить текст (вдруг это медиа с подписью)
        text = message.text or message.caption or ""
        if not text:
            return

        # 1. ПЕЧАТАЕМ В ЛОГ АБСОЛЮТНО ВСЁ, ЧТО ВИДИМ
        chat_type = message.chat.type
        chat_title = message.chat.title or message.chat.username or "Личные сообщения"
        print(f"👀 [РЕНТГЕН] Тип: {chat_type} | Чат: {chat_title} | Текст: {text[:40]}...")

        # 2. Временно ЗАКОММЕНТИРУЕМ фильтр длины (чтобы видеть даже короткие запросы)
        # if len(text) < 15:
        #     return

        # Собираем данные
        chat_id = message.chat.id
        message_id = message.id
        chat_username = message.chat.username or message.chat.title

        # Формируем посылку для очереди
        lead_data = {
            "chat_id": chat_id,
            "message_id": message_id,
            "chat_username": chat_username,
            "text": text
        }

        # Отправляем в RabbitMQ
        await publish_lead(lead_data)
        print(f"✅ Ушло в очередь!")

    except UnicodeDecodeError as e:
        # Тихо игнорируем кривые спам-сообщения (ошибка utf-16-le)
        print(f"⚠️ Пропуск кривого сообщения (ошибка юникода): {e}")
    except Exception as e:
        # Ловим остальные ошибки
        print(f"❌ Ошибка при обработке или отправке в очередь: {e}")

if __name__ == "__main__":
    print("🚀 Запуск Telegram Userbot на VDS (Включен РЕЖИМ РЕНТГЕНА)...")
    print("Нажми Ctrl+C для остановки.")
    app.run()
