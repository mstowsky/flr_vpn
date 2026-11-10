import os
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

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

ENABLE_TEST_COMMANDS = (
    os.getenv("ENABLE_TEST_COMMANDS", "false").lower() == "true"
)


def _get_bool_setting(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    normalized = value.strip().lower()

    if normalized in {"true", "1", "yes"}:
        return True

    if normalized in {"false", "0", "no"}:
        return False

    raise RuntimeError(
        f"{name} должен иметь значение True или False."
    )


def _get_non_negative_int_setting(
    name: str,
    default: int,
    *,
    allow_empty: bool = False,
) -> int:
    value = os.getenv(name)

    if value is None or not value.strip():
        if allow_empty:
            return 0
        return default

    try:
        result = int(value)
    except ValueError as exc:
        raise RuntimeError(
            f"{name} должен быть целым числом."
        ) from exc

    if result < 0:
        raise RuntimeError(
            f"{name} не может быть отрицательным."
        )

    return result


LOG_SYSTEM_ENABLED = _get_bool_setting(
    "LOG_SYSTEM_ENABLED",
    True,
)

LOG_SYSTEM_MAX_SIZE_MB = _get_non_negative_int_setting(
    "LOG_SYSTEM_MAX_SIZE_MB",
    0,
    allow_empty=True,
)

LOG_USER_ENABLED = _get_bool_setting(
    "LOG_USER_ENABLED",
    True,
)

LOG_USER_MAX_SIZE_MB = _get_non_negative_int_setting(
    "LOG_USER_MAX_SIZE_MB",
    0,
    allow_empty=True,
)

LOG_CLEANUP_INTERVAL_MINUTES = _get_non_negative_int_setting(
    "LOG_CLEANUP_INTERVAL_MINUTES",
    30,
)

if LOG_CLEANUP_INTERVAL_MINUTES == 0:
    raise RuntimeError(
        "LOG_CLEANUP_INTERVAL_MINUTES должен быть больше нуля."
    )