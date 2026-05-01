import requests

# Для этого теста нужно установить: pip install requests[socks]

proxies = {
    'http': 'socks5h://busineslevin:nHfKSPaUxb@31.169.79.226:59101',
    'https': 'socks5h://busineslevin:nHfKSPaUxb@31.169.79.226:59101'
}

print("⏳ Пробуем достучаться до Telegram через твой прокси...")
try:
    # Идем на официальный API Телеграма
    response = requests.get('https://api.telegram.org', proxies=proxies, timeout=10)
    print(f"✅ Прокси работает для Telegram! Статус: {response.status_code}")
except Exception as e:
    print(f"❌ Прокси НЕ работает для Telegram. Ошибка: {e}")