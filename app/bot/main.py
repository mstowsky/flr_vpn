
import logging

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.database import async_session_factory
from app.services.users import get_or_create_user

logger = logging.getLogger(__name__)

dp = Dispatcher()


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    telegram_user = message.from_user

    if telegram_user is None:
        await message.answer(
            "Не удалось определить пользователя Telegram."
        )
        return

    async with async_session_factory() as session:
        user, is_new = await get_or_create_user(
            session,
            telegram_id=telegram_user.id,
            username=telegram_user.username,
            first_name=telegram_user.first_name,
        )

    logger.info(
        "Обработан /start: user_id=%s, telegram_id=%s, is_new=%s",
        user.id,
        user.telegram_id,
        is_new,
    )

    if is_new:
        text = (
            f"Привет, {telegram_user.first_name}! 👋\n\n"
            "Добро пожаловать в flr_vpn.\n"
            "Ты успешно зарегистрирован."
        )
    else:
        text = (
            f"С возвращением, {telegram_user.first_name}! 👋\n\n"
            "Твоя учётная запись найдена."
        )

    await message.answer(text)


@dp.message()
async def handle_message(message: Message) -> None:
    logger.info(
        "Получено сообщение от пользователя %s",
        message.from_user.id if message.from_user else "unknown",
    )

    await message.answer(
        "Я пока умею отвечать на команду /start."
    )


async def start_bot(bot: Bot) -> None:
    logger.info("Запуск Telegram-бота")
    await dp.start_polling(bot)