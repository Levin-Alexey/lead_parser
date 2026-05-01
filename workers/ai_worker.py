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
NOTIFIER_WEBHOOK_URL = os.getenv("NOTIFIER_WEBHOOK_URL_TG")

# Инициализируем БД
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
LEADS_QUEUE = "raw_telegram_leads"

# ---------------------------------------------------------
# 1. МОЩНЫЙ REGEX ФИЛЬТР (Предквалификация)
# ---------------------------------------------------------
# \b означает границу слова, \w* захватывает любые окончания
KEYWORDS_PATTERN = re.compile(
    r"\b("
    # Базовые боты и ИИ
    r"чат-?бот\w*|бот\w*|bot\w*|ии\s*бот\w*|ai\s*бот\w*|"
    r"ии\w*|ai\w*|нейросеть\w*|chatgpt|gpt|llm|openai|claude|"
    # Автоматизация и бизнес-процессы
    r"автоматизац\w*|внедрен\w*|интеграц\w*|"
    r"n8n|langgraph|openclaw|nemoclaw|"
    # Маркетплейсы и парсинг
    r"маркетплейс\w*|wildberries|вайлдберриз|wb|ozon|озон|"
    r"аналитик\w*|воронка\s*продаж|парсер\w*|парсинг\w*|"
    # Агенты и аватары
    r"агент\w*|ai\s*агент\w*|ии\s*агент\w*|"
    r"3[dд]-?\s*аватар\w*|"
    # Платформы
    r"вк|vk|vkontakte|телеграм\w*|telegram|тг|"
    # Намерения (глаголы)
    r"сделать|запрограммировать|разработа\w*|созда\w*|ищу\s*программиста|нужен\s*разработчик"
    r")\b",
    re.IGNORECASE
)

def is_relevant_text(text: str) -> bool:
    """Молниеносная проверка регуляркой (True, если есть совпадения)"""
    return bool(KEYWORDS_PATTERN.search(text))

# ---------------------------------------------------------
# 2. ПРОМПТ ДЛЯ LLM (Основная квалификация)
# ---------------------------------------------------------
SYSTEM_PROMPT = """Ты — опытный квалификатор лидов для IT-агентства.
Твоя задача: проанализировать перехваченное сообщение из чата и понять, ищет ли автор исполнителя на коммерческую разработку.

НАШИ ЦЕЛЕВЫЕ ЛИДЫ ИЩУТ:
- Создание Telegram или VK ботов (в т.ч. для ресторанов, доставки, техподдержки).
- Внедрение ИИ, LLM, нейросетей, 3D-аватаров.
- Разработку AI-агентов (в т.ч. многоагентных систем) и автоматизацию бизнес-процессов (n8n, LangGraph).
- Автоматизацию работы с маркетплейсами (парсеры, логистика, сбор данных для сложных воронок на Wildberries/Ozon).

ОТБРАКОВЫВАЙ:
- Программистов, которые просят помощи с кодом (ошибки, дебаг).
- Людей, которые обсуждают новости ИИ или просто общаются.
- Тех, кто предлагает СВОИ услуги разработки (конкурентов).
- Спам и рекламу каналов.

Отвечай СТРОГО в формате JSON:
{"is_lead": true/false, "reason": "Кратко, почему это наш клиент или почему мусор"}"""

async def check_duplicate_in_db(message_id: int, chat_id: int) -> bool:
    """Проверяет, было ли уже это сообщение в БД."""
    try:
        response = supabase.table("parsed_leads").select("id").eq("message_id", message_id).eq("chat_id", chat_id).execute()
        return len(response.data) > 0
    except Exception as e:
        print(f"⚠️ Ошибка проверки БД: {e}")
        return False

async def save_to_db(lead_data: dict, status: str):
    """Сохраняет сообщение в БД со статусом."""
    try:
        supabase.table("parsed_leads").insert({
            "message_id": lead_data["message_id"],
            "chat_id": lead_data["chat_id"],
            "chat_username": lead_data.get("chat_username", ""),
            "text": lead_data["text"],
            "status": status
        }).execute()
    except Exception as e:
        print(f"⚠️ Ошибка записи в БД: {e}")

async def analyze_text_with_llm(session: aiohttp.ClientSession, text: str) -> dict:
    """Отправляет текст в OpenRouter и возвращает JSON-ответ."""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "google/gemini-2.5-flash", # Отличная модель для JSON-задач
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
                print(f"⚠️ Ошибка OpenRouter: {resp.status} - {await resp.text()}")
                return {"is_lead": False, "reason": "API Error"}
    except Exception as e:
        print(f"⚠️ Ошибка парсинга ответа LLM: {e}")
        return {"is_lead": False, "reason": "Parsing Error"}

async def notify_cf_worker(session: aiohttp.ClientSession, lead_data: dict, analysis: dict):
    """Отправляет отфильтрованный лид на Cloudflare Worker."""
    payload = {
        "chat_username": lead_data.get("chat_username"),
        "text": lead_data["text"],
        "reason": analysis.get("reason"),
        "chat_id": lead_data["chat_id"],        # ДОБАВИЛИ ЭТО
        "message_id": lead_data["message_id"]   # И ЭТО
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
    """Главная функция обработки одного сообщения из очереди."""
    async with message.process(): 
        lead_data = json.loads(message.body.decode('utf-8'))
        text = lead_data["text"]

        # 0. ЖЕСТКАЯ ПРЕДКВАЛИФИКАЦИЯ
        if not is_relevant_text(text):
            # Сообщение не содержит ключей. Дропаем.
            # print("🗑️ Пропуск: нет ключевых слов") # Раскомментируй для дебага
            return

        msg_id, chat_id = lead_data["message_id"], lead_data["chat_id"]
        print(f"🎯 Прошел регулярку: {msg_id} из {lead_data.get('chat_username')}")

        # 1. Проверка на дубликат в БД
        is_duplicate = await check_duplicate_in_db(msg_id, chat_id)
        if is_duplicate:
            print("⏭️ Пропуск: сообщение уже есть в базе.")
            return

        # 2. Анализ через LLM
        print("🧠 Отправляем в LLM...")
        analysis = await analyze_text_with_llm(session, text)
        
        # 3. Маршрутизация
        if analysis.get("is_lead"):
            print(f"🔥 ЛИД! Причина: {analysis.get('reason')}")
            await save_to_db(lead_data, "ai_approved")
            await notify_cf_worker(session, lead_data, analysis)
        else:
            print(f"❌ Забраковано LLM. Причина: {analysis.get('reason')}")
            await save_to_db(lead_data, "ai_rejected")

async def main():
    print("🧠 AI Worker запускается...")
    connection = await aio_pika.connect_robust(AMQP_URL)
    
    async with aiohttp.ClientSession() as http_session:
        async with connection:
            channel = await connection.channel()
            await channel.set_qos(prefetch_count=1)
            queue = await channel.declare_queue(LEADS_QUEUE, durable=True)
            
            print("🎧 Слушаю очередь. Нажми Ctrl+C для выхода.")
            
            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    await process_message(message, http_session)

if __name__ == "__main__":
    asyncio.run(main())