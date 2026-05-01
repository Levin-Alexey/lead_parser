import asyncio
import os
from dotenv import load_dotenv
from supabase import create_client, Client
import aio_pika

# Загружаем переменные из .env
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
AMQP_URL = os.getenv("AMQP_URL")

def test_supabase():
    print("⏳ Проверка подключения к Supabase...")
    try:
        # Инициализируем клиент
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # Пробуем сделать простой запрос к нашей созданной таблице
        response = supabase.table("parsed_leads").select("*").limit(1).execute()
        
        print("✅ УСПЕХ: Подключение к Supabase работает! Таблица 'parsed_leads' найдена.")
        return True
    except Exception as e:
        print(f"❌ ОШИБКА подключения к Supabase:\n{e}")
        return False

async def test_amqp():
    print("\n⏳ Проверка подключения к CloudAMQP...")
    try:
        # Пробуем подключиться к брокеру
        connection = await aio_pika.connect_robust(AMQP_URL)
        async with connection:
            # Пробуем открыть канал
            channel = await connection.channel()
            # Пробуем создать очередь (если её нет) или получить к ней доступ
            await channel.declare_queue("raw_telegram_leads", durable=True)
            
            print("✅ УСПЕХ: Подключение к CloudAMQP работает! Очередь 'raw_telegram_leads' доступна.")
        return True
    except Exception as e:
        print(f"❌ ОШИБКА подключения к CloudAMQP:\n{e}")
        return False

async def main():
    print("=== ЗАПУСК ДИАГНОСТИКИ ===\n")
    
    # Проверяем Supabase (синхронно)
    test_supabase()
    
    # Проверяем RabbitMQ (асинхронно)
    await test_amqp()
    
    print("\n=== ДИАГНОСТИКА ЗАВЕРШЕНА ===")

if __name__ == "__main__":
    # Запускаем асинхронный цикл событий
    asyncio.run(main())