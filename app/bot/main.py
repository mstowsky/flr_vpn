import logging

from aiogram import Bot, Dispatcher

from app.bot.handlers.admin import router as admin_router
from app.bot.handlers.user import router as users_router

logger = logging.getLogger(__name__)

dp = Dispatcher()

# Административные команды.
dp.include_router(admin_router)

# Пользовательские команды и обычные сообщения.
dp.include_router(users_router)


async def start_bot(bot: Bot) -> None:
    logger.info("Запуск Telegram-бота")
    await dp.start_polling(bot)