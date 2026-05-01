from __future__ import annotations

import logging
from datetime import timezone

from pyrogram import Client, filters
from pyrogram.types import Message

from config import AMQP_QUEUE_LEADS, AMQP_URL, API_HASH, API_ID, TG_SOURCE_CHATS, missing_required_env
from core.lead_filter import LeadPrefilter
from core.rabbitmq import RabbitMQClient


logging.basicConfig(
	level=logging.INFO,
	format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("tg_userbot")


def _build_message_link(message: Message) -> str | None:
	chat = message.chat
	if chat and chat.username and message.id:
		return f"https://t.me/{chat.username}/{message.id}"

	return None


def _to_payload(message: Message) -> dict:
	user = message.from_user
	chat = message.chat
	message_text = message.text or message.caption or ""
	dt = message.date
	if dt is not None and dt.tzinfo is None:
		dt = dt.replace(tzinfo=timezone.utc)

	return {
		"source": "telegram",
		"chat_id": chat.id if chat else None,
		"chat_title": chat.title if chat else None,
		"chat_username": chat.username if chat else None,
		"message_id": message.id,
		"message_text": message_text,
		"message_date": dt.isoformat() if dt else None,
		"message_link": _build_message_link(message),
		"author_id": user.id if user else None,
		"author_username": user.username if user else None,
		"author_name": " ".join(filter(None, [user.first_name if user else None, user.last_name if user else None]))
		if user
		else None,
	}


def main() -> None:
	missing = missing_required_env()
	if missing:
		logger.error("Missing required env vars: %s", ", ".join(missing))
		raise SystemExit(1)

	publisher = RabbitMQClient(AMQP_URL)
	publisher.connect()

	app = Client("lead_parser_userbot", api_id=API_ID, api_hash=API_HASH)
	prefilter = LeadPrefilter()

	logger.info("Watching chats: %s", TG_SOURCE_CHATS)
	logger.info("Publishing candidates to queue: %s", AMQP_QUEUE_LEADS)

	@app.on_message(filters.chat(TG_SOURCE_CHATS) & (filters.text | filters.caption))
	def handle_message(_: Client, message: Message) -> None:
		text = message.text or message.caption or ""
		if not prefilter.is_candidate(text):
			return

		payload = _to_payload(message)
		publisher.publish_json(AMQP_QUEUE_LEADS, payload)
		logger.info(
			"Candidate queued | chat=%s msg_id=%s link=%s",
			payload.get("chat_title") or payload.get("chat_username") or payload.get("chat_id"),
			payload.get("message_id"),
			payload.get("message_link"),
		)

	try:
		app.run()
	finally:
		publisher.close()


if __name__ == "__main__":
	main()
