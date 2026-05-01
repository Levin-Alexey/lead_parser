import os
import sys
import json
import asyncio
import aiohttp
import aio_pika
from dotenv import load_dotenv
from supabase import create_client, Client

# Настраиваем пути
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)
load_dotenv(os.path.join(BASE_DIR, '.env'))

# Забираем доступы
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
AMQP_URL = os.getenv("AMQP_URL")
VK_ACCESS_TOKEN = os.getenv("VK_ACCESS_TOKEN")

# Инициализируем БД и очередь
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
VK_QUEUE_NAME = "raw_vk_leads"
VK_API_VERSION = "5.199"

async def fetch_active_groups():
    """Получает список всех активных групп для парсинга из БД."""
    try:
        response = supabase.table("vk_target_groups").select("*").eq("is_active", True).execute()
        return response.data
    except Exception as e:
        print(f"⚠️ Ошибка получения групп из БД: {e}")
        return []

async def update_last_checked_post(db_id: int, last_post_id: int):
    """Обновляет 'память' парсера для конкретной группы."""
    try:
        supabase.table("vk_target_groups").update({"last_checked_post_id": last_post_id}).eq("id", db_id).execute()
    except Exception as e:
        print(f"⚠️ Ошибка обновления last_checked_post_id: {e}")

def chunk_list(data, chunk_size):
    """Разбивает список на куски (для лимита в 25 запросов метода execute)."""
    for i in range(0, len(data), chunk_size):
        yield data[i:i + chunk_size]

async def process_vk_batch(session: aiohttp.ClientSession, groups_chunk, rmq_channel: aio_pika.Channel):
    """Формирует VKScript, делает один запрос к API и рассылает лиды в очередь."""
    
    # 1. Формируем код для метода execute
    vk_script = "var res = {};\n"
    for group in groups_chunk:
        owner_id = group["group_id"]
        # Запрашиваем 5 последних постов со стены
        vk_script += f'res["{owner_id}"] = API.wall.get({{"owner_id": {owner_id}, "count": 5}});\n'
    vk_script += "return res;"

    payload = {
        "access_token": VK_ACCESS_TOKEN,
        "v": VK_API_VERSION,
        "code": vk_script
    }

    try:
        async with session.post("https://api.vk.com/method/execute", data=payload) as resp:
            data = await resp.json()
            
            if "error" in data:
                print(f"⚠️ Ошибка API ВК: {data['error'].get('error_msg')}")
                return

            results = data.get("response", {})
            
            # 2. Разбираем ответ
            for group in groups_chunk:
                owner_id = group["group_id"]
                db_id = group["id"]
                last_checked_id = group.get("last_checked_post_id", 0)
                
                group_data = results.get(str(owner_id), {})
                if not group_data or not isinstance(group_data, dict):
                    continue
                    
                posts = group_data.get("items", [])
                max_post_id_in_batch = last_checked_id

                for post in reversed(posts): # Идем от старых к новым
                    post_id = post.get("id")
                    
                    # Пропускаем закрепленные посты, если они старые
                    if post_id <= last_checked_id:
                        continue
                    
                    text = post.get("text", "")
                    if not text:
                        continue

                    max_post_id_in_batch = max(max_post_id_in_batch, post_id)

                    # Формируем посылку для RabbitMQ
                    lead_data = {
                        "source": "vk",
                        "chat_id": str(owner_id),
                        "message_id": str(post_id),
                        "chat_username": group.get("name", f"vk.com/wall{owner_id}"),
                        "text": text
                    }

                    # Отправляем в очередь
                    message = aio_pika.Message(body=json.dumps(lead_data).encode("utf-8"))
                    await rmq_channel.default_exchange.publish(message, routing_key=VK_QUEUE_NAME)
                    
                    print(f"📥 [VK] Перехвачен пост {post_id} из группы {owner_id}. Отправлен в очередь!")

                # Обновляем память в БД, если нашли новые посты
                if max_post_id_in_batch > last_checked_id:
                    await update_last_checked_post(db_id, max_post_id_in_batch)

    except Exception as e:
        print(f"⚠️ Ошибка при обработке батча ВК: {e}")

async def main():
    print("🚀 Запуск VK Parser...")
    
    # Подключаемся к RabbitMQ
    connection = await aio_pika.connect_robust(AMQP_URL)
    
    async with aiohttp.ClientSession() as http_session:
        async with connection:
            channel = await connection.channel()
            # Убеждаемся, что очередь существует
            await channel.declare_queue(VK_QUEUE_NAME, durable=True)
            
            while True:
                groups = await fetch_active_groups()
                if not groups:
                    print("💤 Нет активных групп для парсинга. Жду 5 минут...")
                else:
                    print(f"🔄 Опрашиваю {len(groups)} групп ВК...")
                    # Разбиваем на пачки по 25 штук
                    for chunk in chunk_list(groups, 25):
                        await process_vk_batch(http_session, chunk, channel)
                        await asyncio.sleep(1) # Небольшая пауза между батчами, чтобы ВК не ругался

                # Спим 5 минут до следующего цикла проверки
                await asyncio.sleep(300)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️ Парсер ВК остановлен.")