"""
Мониторинг страницы предстоящих турниров на llb.su.

Скрипт скачивает страницу, вырезает из неё блок с таблицей турниров
(между заголовком "Регион" и началом боковой колонки "новости"),
сравнивает с тем, что было сохранено при прошлом запуске, и если
содержимое изменилось — отправляет сообщение в Telegram.

Состояние (хэш + кусок текста) хранится в файле state.json,
который коммитится обратно в репозиторий после каждого запуска
(см. .github/workflows/monitor.yml).
"""

import os
import json
import hashlib
import requests
from bs4 import BeautifulSoup

URL = "https://www.llb.su/node/2873189/next"
STATE_FILE = "state.json"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Притворяемся обычным браузером, чтобы сайт не отдавал другой контент/блокировку
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

# Эти строки служат границами интересующего нас блока на странице.
# Если разметка сайта сильно изменится и границы не найдутся,
# скрипт подстрахуется и возьмёт весь текст страницы (см. fetch_section).
START_MARKER = "Регион"
END_MARKER = "новости"


def fetch_section() -> str:
    response = requests.get(URL, headers=HEADERS, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    full_text = soup.get_text(separator="\n")

    start_idx = full_text.find(START_MARKER)
    end_idx = full_text.find(END_MARKER, start_idx) if start_idx != -1 else -1

    if start_idx != -1 and end_idx != -1:
        section = full_text[start_idx:end_idx]
    else:
        # Подстраховка: если разметка изменилась и маркеры не нашлись —
        # лучше следить за всей страницей, чем сломаться молча.
        section = full_text

    # Убираем пустые строки и лишние пробелы, чтобы хэш не "плавал"
    # из-за невидимых отличий в вёрстке.
    lines = [line.strip() for line in section.splitlines() if line.strip()]
    return "\n".join(lines)


def load_previous_state():
    if not os.path.exists(STATE_FILE):
        return None
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(content_hash: str, snippet: str) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {"hash": content_hash, "snippet": snippet[:1000]},
            f,
            ensure_ascii=False,
            indent=2,
        )


def send_telegram_message(text: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID не заданы — уведомление не отправлено.")
        print(text)
        return

    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(
            api_url,
            data={"chat_id": TELEGRAM_CHAT_ID, "text": text},
            timeout=15,
        )
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"Не удалось отправить сообщение в Telegram: {exc}")


def main() -> None:
    section = fetch_section()
    content_hash = hashlib.sha256(section.encode("utf-8")).hexdigest()

    previous = load_previous_state()

    if previous is None:
        # Первый запуск — просто сохраняем точку отсчёта, без уведомления,
        # иначе вы получите "изменение" сразу при первом запуске.
        save_state(content_hash, section)
        print("Первый запуск: состояние сохранено, уведомление не отправляется.")
        return

    if previous.get("hash") != content_hash:
        message = (
            "🔔 На странице турниров появились изменения!\n\n"
            f"{URL}\n\n"
            f"{section[:500]}"
        )
        send_telegram_message(message)
        save_state(content_hash, section)
        print("Обнаружено изменение, уведомление отправлено.")
    else:
        print("Изменений нет.")


if __name__ == "__main__":
    main()
