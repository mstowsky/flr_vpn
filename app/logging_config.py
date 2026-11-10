
import asyncio
import logging
import shutil
import threading

from datetime import datetime, time, timedelta
from pathlib import Path

from app.config import (
    DISPLAY_TIMEZONE,
    LOG_CLEANUP_INTERVAL_MINUTES,
    LOG_SYSTEM_ENABLED,
    LOG_SYSTEM_MAX_SIZE_MB,
    LOG_USER_ENABLED,
    LOG_USER_MAX_SIZE_MB,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent

SYSTEM_LOG_DIR = PROJECT_ROOT / "logs" / "system"
USER_LOG_DIR = PROJECT_ROOT / "logs" / "messages"

SYSTEM_LOG_FILE = SYSTEM_LOG_DIR / "system.log"
USER_LOG_FILE = USER_LOG_DIR / "messages.log"

SYSTEM_LOGGER_NAME = "system"
USER_LOGGER_NAME = "user_messages"

MB = 1024 * 1024


class LocalTimeFormatter(logging.Formatter):
    """Форматирует время в DISPLAY_TIMEZONE."""

    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(
            record.created,
            DISPLAY_TIMEZONE,
        )

        if datefmt:
            return dt.strftime(datefmt)

        return dt.isoformat(sep=" ", timespec="milliseconds")


class DailyLogHandler(logging.Handler):
    """Записывает логи в файл с ежедневной ротацией."""

    def __init__(
        self,
        filename: Path,
        timezone,
    ):
        super().__init__()

        self.filename = filename
        self.timezone = timezone
        self.filename.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.stream = None

        today = datetime.now(timezone).date()

        # Если после предыдущего запуска остался файл
        # за прошлую дату, архивируем его.
        if self.filename.exists():
            modified_at = datetime.fromtimestamp(
                self.filename.stat().st_mtime,
                timezone,
            ).date()

            if modified_at != today:
                self._archive_active_file(modified_at)

        self.current_date = today
        self.stream = self.filename.open(
            "a",
            encoding="utf-8",
        )

    def _archive_active_file(self, archive_date):
        if not self.filename.exists():
            return

        archive_path = self.filename.with_name(
            f"{self.filename.name}.{archive_date.isoformat()}"
        )

        if archive_path.exists():
            # Если архив с такой датой уже существует,
            # дописываем в него содержимое активного файла.
            with (
                self.filename.open("rb") as source,
                archive_path.open("ab") as destination,
            ):
                shutil.copyfileobj(source, destination)

            self.filename.unlink()
        else:
            self.filename.rename(archive_path)

    def emit(self, record):
        try:
            with self.lock:
                record_date = datetime.fromtimestamp(
                    record.created,
                    self.timezone,
                ).date()

                if record_date != self.current_date:
                    self.stream.close()
                    self.stream = None

                    self._archive_active_file(
                        self.current_date
                    )

                    self.current_date = record_date

                    self.stream = self.filename.open(
                        "a",
                        encoding="utf-8",
                    )

                message = self.format(record)

                self.stream.write(message + "\n")
                self.stream.flush()

        except Exception:
            self.handleError(record)

    def close(self):
        with self.lock:
            if self.stream is not None:
                self.stream.close()
                self.stream = None

        super().close()


def _create_formatter():
    return LocalTimeFormatter(
        "%(asctime)s | %(levelname)s | "
        "%(name)s | %(message)s"
    )


def configure_logging():
    """Настраивает системный и пользовательский журналы."""

    formatter = _create_formatter()

    # Системный журнал.
    system_logger = logging.getLogger()

    system_logger.setLevel(logging.INFO)
    system_logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    system_logger.addHandler(console_handler)

    if LOG_SYSTEM_ENABLED:
        system_handler = DailyLogHandler(
            SYSTEM_LOG_FILE,
            DISPLAY_TIMEZONE,
        )
        system_handler.setFormatter(formatter)
        system_logger.addHandler(system_handler)

    # Журнал сообщений пользователей.
    user_logger = logging.getLogger(USER_LOGGER_NAME)

    user_logger.setLevel(logging.INFO)
    user_logger.handlers.clear()
    user_logger.propagate = False

    if LOG_USER_ENABLED:
        user_handler = DailyLogHandler(
            USER_LOG_FILE,
            DISPLAY_TIMEZONE,
        )
        user_handler.setFormatter(formatter)
        user_logger.addHandler(user_handler)


def _cleanup_directory(
    directory: Path,
    active_file: Path,
    max_size_mb: int,
):
    """Удаляет самые старые архивы при превышении лимита."""

    if max_size_mb == 0 or not directory.exists():
        return

    files = [
        path
        for path in directory.iterdir()
        if path.is_file()
    ]

    total_size = sum(
        path.stat().st_size
        for path in files
    )

    max_size = max_size_mb * MB

    if total_size <= max_size:
        return

    # Активный файл не удаляем.
    archives = [
        path
        for path in files
        if path != active_file
    ]

    archives.sort(
        key=lambda path: path.stat().st_mtime
    )

    for archive in archives:
        if total_size <= max_size:
            break

        archive_size = archive.stat().st_size

        try:
            archive.unlink()
            total_size -= archive_size

        except OSError:
            logging.getLogger(__name__).exception(
                "Не удалось удалить архив логов: %s",
                archive,
            )

    if total_size > max_size:
        logging.getLogger(__name__).warning(
            "Размер логов в %s превышает лимит. "
            "Удаление архивов не позволило достичь ограничения.",
            directory,
        )


def cleanup_log_files():
    """Проверяет и ограничивает размер журналов."""

    _cleanup_directory(
        SYSTEM_LOG_DIR,
        SYSTEM_LOG_FILE,
        LOG_SYSTEM_MAX_SIZE_MB,
    )

    _cleanup_directory(
        USER_LOG_DIR,
        USER_LOG_FILE,
        LOG_USER_MAX_SIZE_MB,
    )


async def run_log_cleanup():
    """Периодически проверяет размеры журналов."""

    interval = LOG_CLEANUP_INTERVAL_MINUTES * 60

    while True:
        await asyncio.sleep(interval)

        cleanup_log_files()

        logging.getLogger(__name__).info(
            "Проверка размера журналов завершена."
        )
