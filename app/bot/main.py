import logging

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message

dp = Dispatcher()


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привет! Это flr_vpn.\n\n"
        "Бот находится в разработке."
    )


@dp.message()
async def handle_message(message: Message) -> None:
    await message.answer(
        "Я пока умею отвечать на команду /start."
    )


async def start_bot(bot: Bot) -> None:
    logging.info("Telegram-бот запускается")

    await dp.start_polling(bot)