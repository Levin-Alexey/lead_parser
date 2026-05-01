import re
from typing import Pattern

# Core intent patterns for automation/AI bot service requests in Russian and English.
POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\b(нужен|ищу|требуется|закажу|хочу)\b.{0,40}\b(бот|telegram\s*бот|тг\s*бот)\b",
    r"\b(сделать|разработать|написать|создать)\b.{0,40}\b(бот|чат[-\s]?бот|ai\s*бот)\b",
    r"\b(нужен|ищу|требуется|закажу|хочу)\b.{0,40}\b(ai|ии|нейросеть|llm)\b",
    r"\b(нужен|ищу|требуется|закажу|хочу)\b.{0,50}\b(n8n|интеграци\w*|автоматизаци\w*)\b",
    r"\b(заказ|разработка)\b.{0,40}\b(бота|ботов|ai\s*проекта|автоматизации)\b",
    r"\bneed|looking\s*for|want\b.{0,50}\b(ai\s*bot|telegram\s*bot|n8n|automation)\b",
)

NEGATIVE_PATTERNS: tuple[str, ...] = (
    r"\bваканси\w*\b",
    r"\bрезюме\b",
    r"\bищу\s+работу\b",
    r"\bпродам\b",
    r"\bкуплю\b",
)


class LeadPrefilter:
    def __init__(self) -> None:
        self._positive: list[Pattern[str]] = [
            re.compile(pattern, re.IGNORECASE | re.DOTALL) for pattern in POSITIVE_PATTERNS
        ]
        self._negative: list[Pattern[str]] = [
            re.compile(pattern, re.IGNORECASE | re.DOTALL) for pattern in NEGATIVE_PATTERNS
        ]

    def is_candidate(self, text: str) -> bool:
        normalized = " ".join((text or "").split())
        if len(normalized) < 10:
            return False

        if any(rx.search(normalized) for rx in self._negative):
            return False

        return any(rx.search(normalized) for rx in self._positive)
