import logging

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message

logger = logging.getLogger(__name__)

dp = Dispatcher()


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    logger.info(
        "Получена команда /start от пользователя %s",
        message.from_user.id if message.from_user else "unknown",
    )

    await message.answer(
        "Привет! Это flr_vpn.\n\n"
        "Бот находится в разработке."
    )


@dp.message()
async def handle_message(message: Message) -> None:
    logger.info(
        "Получено сообщение от пользователя %s: %r",
        message.from_user.id if message.from_user else "unknown",
        message.text,
    )

    await message.answer(
        "Я пока умею отвечать на команду /start."
    )


async def start_bot(bot: Bot) -> None:
    logger.info("Запуск Telegram-бота")

    await dp.start_polling(bot)