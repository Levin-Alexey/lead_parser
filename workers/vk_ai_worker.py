import os
import sys
import json
import asyncio
import re
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
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
NOTIFIER_WEBHOOK_URL = os.getenv("NOTIFIER_WEBHOOK_URL")

# Инициализируем БД
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
VK_QUEUE_NAME = "raw_vk_leads"

# ---------------------------------------------------------
# 1. ЖЕСТКИЙ REGEX ФИЛЬТР (Тот же мощный словарь)
# ---------------------------------------------------------
KEYWORDS_PATTERN = re.compile(
    r"\b("
    r"чат-?бот\w*|бот\w*|bot\w*|ии\s*бот\w*|ai\s*бот\w*|"
    r"ии\w*|ai\w*|нейросеть\w*|chatgpt|gpt|llm|openai|claude|"
    r"автоматизац\w*|внедрен\w*|интеграц\w*|"
    r"n8n|langgraph|openclaw|nemoclaw|"
    r"маркетплейс\w*|wildberries|вайлдберриз|wb|ozon|озон|"
    r"аналитик\w*|воронка\s*продаж|парсер\w*|парсинг\w*|"
    r"агент\w*|ai\s*агент\w*|ии\s*агент\w*|"
    r"3[dд]-?\s*аватар\w*|"
    r"вк|vk|vkontakte|телеграм\w*|telegram|тг|"
    r"сделать|запрограммировать|разработа\w*|созда\w*|ищу\s*программиста|нужен\s*разработчик"
    r")\b",
    re.IGNORECASE
)

def is_relevant_text(text: str) -> bool:
    return bool(KEYWORDS_PATTERN.search(text))

# ---------------------------------------------------------
# 2. ПРОМПТ ДЛЯ LLM (Адаптирован под ВКонтакте)
# ---------------------------------------------------------
SYSTEM_PROMPT = """Ты — опытный квалификатор лидов для IT-агентства.
Твоя задача: проанализировать пост со стены ВКонтакте и понять, ищет ли автор исполнителя на коммерческую разработку.

НАШИ ЦЕЛЕВЫЕ ЛИДЫ ИЩУТ:
- Создание Telegram или VK ботов.
- Внедрение ИИ, LLM, нейросетей, 3D-аватаров.
- Разработку AI-агентов и автоматизацию бизнес-процессов (n8n, LangGraph).
- Автоматизацию работы с маркетплейсами (Wildberries/Ozon).

ВК-СПЕЦИФИКА ОТБРАКОВКИ:
- В ВК часто публикуют обучающие статьи, новости ИИ или рекламные кейсы студий. Это мусор, нам нужны только те, кто ИЩЕТ ИСПОЛНИТЕЛЯ или просит оценить проект.
- Отбраковывай программистов, которые просят помощи с кодом.
- Спам и рекламу своих услуг.

Отвечай СТРОГО в формате JSON:
{"is_lead": true/false, "reason": "Кратко, почему это наш клиент или почему мусор"}"""

async def check_duplicate_in_db(owner_id: str, post_id: str) -> bool:
    """Проверяет дубликаты по таблице ВК."""
    try:
        response = supabase.table("parsed_vk_leads").select("id").eq("owner_id", owner_id).eq("post_id", post_id).execute()
        return len(response.data) > 0
    except Exception as e:
        print(f"⚠️ Ошибка проверки БД ВК: {e}")
        return False

async def save_to_db(lead_data: dict, status: str):
    """Сохраняет сообщение в таблицу ВК."""
    try:
        supabase.table("parsed_vk_leads").insert({
            "owner_id": lead_data["chat_id"],  # Парсер шлет это в поле chat_id
            "post_id": lead_data["message_id"], # Парсер шлет это в поле message_id
            "text": lead_data["text"],
            "status": status
        }).execute()
    except Exception as e:
        print(f"⚠️ Ошибка записи в БД ВК: {e}")

async def analyze_text_with_llm(session: aiohttp.ClientSession, text: str) -> dict:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "google/gemini-2.5-flash",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text}
        ],
        "response_format": {"type": "json_object"}
    }
    try:
        async with session.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload) as resp:
            if resp.status == 200:
                result = await resp.json()
                content = result['choices'][0]['message']['content']
                clean_content = content.replace('```json', '').replace('```', '').strip()
                return json.loads(clean_content)
            else:
                return {"is_lead": False, "reason": "API Error"}
    except Exception as e:
        print(f"⚠️ Ошибка парсинга LLM: {e}")
        return {"is_lead": False, "reason": "Parsing Error"}

async def notify_cf_worker(session: aiohttp.ClientSession, lead_data: dict, analysis: dict):
    """Отправляет лид на Cloudflare Worker. Обязательно передаем source='vk'"""
    payload = {
        "chat_username": lead_data.get("chat_username"),
        "text": lead_data["text"],
        "reason": analysis.get("reason"),
        "chat_id": lead_data["chat_id"],
        "message_id": lead_data["message_id"]
    }
    try:
        async with session.post(NOTIFIER_WEBHOOK_URL, json=payload) as resp:
            if resp.status == 200:
                print("✅ Успешно отправлено на Cloudflare Worker!")
            else:
                print(f"⚠️ Ошибка вебхука CF: {resp.status}")
    except Exception as e:
        print(f"⚠️ Ошибка вызова CF Worker: {e}")

async def process_message(message: aio_pika.IncomingMessage, session: aiohttp.ClientSession):
    async with message.process(): 
        lead_data = json.loads(message.body.decode('utf-8'))
        text = lead_data["text"]

        # 0. ПРЕДКВАЛИФИКАЦИЯ (Регулярка)
        if not is_relevant_text(text):
            return

        owner_id = lead_data["chat_id"]
        post_id = lead_data["message_id"]
        print(f"🎯 Прошел регулярку ВК: Пост {post_id} из группы {owner_id}")

        # 1. Проверка на дубликат в БД
        is_duplicate = await check_duplicate_in_db(str(owner_id), str(post_id))
        if is_duplicate:
            print("⏭️ Пропуск: пост уже есть в базе.")
            return

        # 2. Анализ через LLM
        print("🧠 Отправляем ВК-пост в LLM...")
        analysis = await analyze_text_with_llm(session, text)
        
        # 3. Маршрутизация
        if analysis.get("is_lead"):
            print(f"🔥 ВК-ЛИД! Причина: {analysis.get('reason')}")
            await save_to_db(lead_data, "ai_approved")
            await notify_cf_worker(session, lead_data, analysis)
        else:
            print(f"❌ Забраковано LLM. Причина: {analysis.get('reason')}")
            await save_to_db(lead_data, "ai_rejected")

async def main():
    print("🧠 VK AI Worker запускается...")
    connection = await aio_pika.connect_robust(AMQP_URL)
    
    async with aiohttp.ClientSession() as http_session:
        async with connection:
            channel = await connection.channel()
            await channel.set_qos(prefetch_count=1)
            queue = await channel.declare_queue(VK_QUEUE_NAME, durable=True)
            
            print("🎧 Слушаю очередь ВК. Нажми Ctrl+C для выхода.")
            
            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    await process_message(message, http_session)

if __name__ == "__main__":
    asyncio.run(main())