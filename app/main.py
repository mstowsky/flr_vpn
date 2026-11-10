
import asyncio
import logging

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession

from app.bot.main import start_bot
from app.config import BOT_TOKEN
from app.database import close_db
from app.logging_config import (
    cleanup_log_files,
    configure_logging,
    run_log_cleanup,
)


logger = logging.getLogger(__name__)


async def main() -> None:
    session = AiohttpSession(
        proxy="http://127.0.0.1:10808"
    )
    bot = Bot(token=BOT_TOKEN, session=session)

    cleanup_task = None

    try:
        # Проверяем размер журналов при запуске.
        cleanup_log_files()

        # Запускаем периодическую очистку.
        cleanup_task = asyncio.create_task(
            run_log_cleanup()
        )

        await start_bot(bot)

    finally:
        if cleanup_task is not None:
            cleanup_task.cancel()

            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass

        try:
            await bot.session.close()
        finally:
            await close_db()


if __name__ == "__main__":
    configure_logging()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Получен Ctrl+C, бот остановлен")