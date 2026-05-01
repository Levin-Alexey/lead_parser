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

# Фильтр: слушаем только текстовые сообщения в группах
@app.on_message(filters.group & filters.text)
async def handle_new_message(client: Client, message: Message):
    # Отсекаем слишком короткие сообщения (мусор)
    if len(message.text) < 15:
        return

    # Собираем данные
    chat_id = message.chat.id
    message_id = message.id
    chat_username = message.chat.username or message.chat.title
    text = message.text

    # Формируем посылку для очереди
    lead_data = {
        "chat_id": chat_id,
        "message_id": message_id,
        "chat_username": chat_username,
        "text": text
    }

    # Отправляем в RabbitMQ
    try:
        await publish_lead(lead_data)
        # Выводим в консоль кусочек текста для наглядности
        print(f"📥 Перехвачено: '{text[:40]}...' из '{chat_username}'. Отправлено в очередь!")
    except Exception as e:
        print(f"❌ Ошибка при отправке в очередь: {e}")

if __name__ == "__main__":
    print("🚀 Запуск Telegram Userbot на VDS...")
    print("Нажми Ctrl+C для остановки.")
    app.run()