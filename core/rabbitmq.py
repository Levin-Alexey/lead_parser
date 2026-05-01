import json
import aio_pika
from config import AMQP_URL

# Название нашей очереди
LEADS_QUEUE = "raw_telegram_leads"

async def get_mq_connection():
    """Создает и возвращает надежное подключение к CloudAMQP"""
    # connect_robust автоматически восстанавливает соединение при обрывах
    return await aio_pika.connect_robust(AMQP_URL)

async def publish_lead(message_data: dict):
    """
    Отправляет сырое сообщение из Telegram в очередь.
    Вызывается продюсером (парсером).
    """
    connection = await get_mq_connection()
    async with connection:
        channel = await connection.channel()
        
        # Объявляем очередь (durable=True значит, что очередь переживет рестарт брокера)
        queue = await channel.declare_queue(LEADS_QUEUE, durable=True)
        
        # Пакуем словарь в JSON и отправляем
        body = json.dumps(message_data, ensure_ascii=False).encode('utf-8')
        
        await channel.default_exchange.publish(
            aio_pika.Message(
                body=body,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT # Сообщения сохраняются на диск
            ),
            routing_key=LEADS_QUEUE
        )