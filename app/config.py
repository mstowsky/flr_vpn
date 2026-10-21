import os

from dotenv import load_dotenv
from zoneinfo import ZoneInfo

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

_display_timezone = os.getenv("DISPLAY_TIMEZONE")

if not _display_timezone:
    raise RuntimeError(
        "DISPLAY_TIMEZONE не найден. "
        "Укажи часовой пояс в файле .env."
    )

try:
    DISPLAY_TIMEZONE = ZoneInfo(_display_timezone)
except (KeyError, ValueError) as exc:
    raise RuntimeError(
        "DISPLAY_TIMEZONE содержит некорректный часовой пояс."
    ) from exc

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