import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN не найден. Проверь файл .env в корне проекта."
    )

_admin_telegram_id = os.getenv("ADMIN_TELEGRAM_ID")

if not _admin_telegram_id:
    raise RuntimeError(
        "ADMIN_TELEGRAM_ID не найден. "
        "Укажи Telegram ID администратора в файле .env."
    )

try:
    ADMIN_TELEGRAM_ID = int(_admin_telegram_id)
except ValueError as exc:
    raise RuntimeError(
        "ADMIN_TELEGRAM_ID должен быть целым числом."
    ) from exc

if ADMIN_TELEGRAM_ID <= 0:
    raise RuntimeError(
        "ADMIN_TELEGRAM_ID должен быть положительным числом."
    )