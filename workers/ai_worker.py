from __future__ import annotations

import asyncio
import json
import logging

import aiohttp
from openai import OpenAI

from config import (
	AMQP_QUEUE_LEADS,
	AMQP_URL,
	NOTIFIER_WEBHOOK_URL,
	OPENROUTER_API_KEY,
	OPENROUTER_MODEL,
	SUPABASE_KEY,
	SUPABASE_URL,
)
from core.database import save_lead
from core.rabbitmq import RabbitMQClient


logging.basicConfig(
	level=logging.INFO,
	format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ai_worker")


PROMPT_TEMPLATE = """
Ты анализируешь сообщения из Telegram-чатов и определяешь, является ли сообщение реальным коммерческим запросом на услуги разработки.

Считай LEAD=true только если есть явный запрос на заказ/разработку/поиск исполнителя для:
- AI-бота
- Telegram-бота
- автоматизации на n8n
- похожих AI/automation решений

Ответь только JSON-объектом без markdown:
{
  "is_lead": true/false,
  "confidence": 0..1,
  "reason": "кратко"
}

Сообщение:
{text}
""".strip()


def classify_message(client: OpenAI, text: str) -> dict:
	prompt = PROMPT_TEMPLATE.format(text=text.strip())
	response = client.chat.completions.create(
		model=OPENROUTER_MODEL,
		messages=[
			{"role": "system", "content": "Ты строгий классификатор лидов."},
			{"role": "user", "content": prompt},
		],
		temperature=0,
	)
	content = (response.choices[0].message.content or "{}").strip()

	try:
		data = json.loads(content)
	except json.JSONDecodeError:
		return {"is_lead": False, "confidence": 0.0, "reason": "invalid_json"}

	return {
		"is_lead": bool(data.get("is_lead", False)),
		"confidence": float(data.get("confidence", 0.0)),
		"reason": str(data.get("reason", ""))[:500],
	}


async def send_notification(payload: dict) -> bool:
	if not NOTIFIER_WEBHOOK_URL:
		logger.warning("NOTIFIER_WEBHOOK_URL is empty; skipping notification")
		return True

	timeout = aiohttp.ClientTimeout(total=15)
	async with aiohttp.ClientSession(timeout=timeout) as session:
		async with session.post(NOTIFIER_WEBHOOK_URL, json=payload) as response:
			if response.status < 300:
				return True

			body = await response.text()
			logger.error("Webhook failed: status=%s body=%s", response.status, body)
			return False


def main() -> None:
	if not AMQP_URL:
		raise SystemExit("AMQP_URL is missing")
	if not OPENROUTER_API_KEY:
		raise SystemExit("OPENROUTER_API_KEY is missing")

	rabbit = RabbitMQClient(AMQP_URL)
	rabbit.connect()
	llm = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)

	logger.info("AI worker started, queue=%s model=%s", AMQP_QUEUE_LEADS, OPENROUTER_MODEL)

	def process(payload: dict) -> bool:
		text = (payload.get("message_text") or "").strip()
		if not text:
			return True

		try:
			verdict = classify_message(llm, text)
		except Exception:
			logger.exception("LLM classify error")
			return False

		if not verdict.get("is_lead"):
			logger.info("Not a lead | msg_id=%s", payload.get("message_id"))
			return True

		notify_payload = {
			"type": "lead_detected",
			"source": payload.get("source"),
			"chat_title": payload.get("chat_title"),
			"message_text": payload.get("message_text"),
			"message_link": payload.get("message_link"),
			"confidence": verdict.get("confidence"),
			"reason": verdict.get("reason"),
		}

		if SUPABASE_URL and SUPABASE_KEY:
			try:
				save_lead(
					{
						"source": payload.get("source"),
						"chat_id": payload.get("chat_id"),
						"chat_title": payload.get("chat_title"),
						"message_id": payload.get("message_id"),
						"message_text": payload.get("message_text"),
						"message_link": payload.get("message_link"),
						"author_id": payload.get("author_id"),
						"author_username": payload.get("author_username"),
						"confidence": verdict.get("confidence"),
						"reason": verdict.get("reason"),
					}
				)
			except Exception:
				logger.exception("Supabase save failed")

		try:
			sent = asyncio.run(send_notification(notify_payload))
		except Exception:
			logger.exception("Webhook send error")
			return False

		if sent:
			logger.info(
				"Lead notified | msg_id=%s confidence=%.2f",
				payload.get("message_id"),
				verdict.get("confidence", 0.0),
			)
			return True

		return False

	try:
		rabbit.consume_json(AMQP_QUEUE_LEADS, process)
	finally:
		rabbit.close()


if __name__ == "__main__":
	main()
