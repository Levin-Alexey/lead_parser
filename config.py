import os
from dotenv import load_dotenv

load_dotenv()

# Telegram API (my.telegram.org)
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

# CloudAMQP
AMQP_URL = os.getenv("AMQP_URL", "")

# OpenRouter
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# Cloudflare Worker URL (для отправки уведомлений)
NOTIFIER_WEBHOOK_URL = os.getenv("NOTIFIER_WEBHOOK_URL", "")

# OpenRouter model used by AI worker
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")

# Parser settings
TG_SOURCE_CHATS = [chat.strip() for chat in os.getenv("TG_SOURCE_CHATS", "").split(",") if chat.strip()]
AMQP_QUEUE_LEADS = os.getenv("AMQP_QUEUE_LEADS", "leads_candidates")


def missing_required_env() -> list[str]:
	missing: list[str] = []
	required = {
		"API_ID": API_ID,
		"API_HASH": API_HASH,
		"AMQP_URL": AMQP_URL,
	}

	for key, value in required.items():
		if not value:
			missing.append(key)

	if not TG_SOURCE_CHATS:
		missing.append("TG_SOURCE_CHATS")

	return missing