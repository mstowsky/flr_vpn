import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from sqlalchemy import select

from app.bot.keyboards.user import (
    get_user_keyboard,
    SUBSCRIPTION_BUTTON_TEXT,
    TRIAL_BUTTON_TEXT,
)

from app.config import DISPLAY_TIMEZONE
from app.database import async_session_factory
from app.models.user import User
from app.services.subscriptions import (
    activate_trial_period,
    get_user_subscription_info,
)
from app.services.users import get_or_create_user

logger = logging.getLogger(__name__)

router = Router()


@router.message(CommandStart())
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

    await message.answer(
        text,
        reply_markup=get_user_keyboard(),
    )


@router.message(F.text == TRIAL_BUTTON_TEXT)
@router.message(Command("trial"))
async def trial_command(message: Message) -> None:
    telegram_user = message.from_user

    if telegram_user is None:
        await message.answer(
            "Не удалось определить пользователя Telegram."
        )
        return

    async with async_session_factory() as session:
        user, _ = await get_or_create_user(
            session,
            telegram_id=telegram_user.id,
            username=telegram_user.username,
            first_name=telegram_user.first_name,
        )

        try:
            subscription = await activate_trial_period(
                session,
                user_id=user.id,
            )
        except ValueError as exc:
            await message.answer(str(exc))
            return

    logger.info(
        "Активирован пробный период: user_id=%s, subscription_id=%s",
        user.id,
        subscription.id,
    )

    await message.answer(
        "Пробный период активирован! 🎉\n\n"
        "Срок: 3 дня\n"
        "Устройства: 1\n"
        "Трафик: 5 ГБ\n\n"
        "Задача на создание VPN-доступа добавлена в очередь. "
        "Доступ будет подготовлен вручную. "
        "После настройки ты получишь дальнейшие инструкции."
    )


@router.message(F.text == SUBSCRIPTION_BUTTON_TEXT)
@router.message(Command("subscription"))
async def subscription_command(message: Message) -> None:
    telegram_user = message.from_user

    if telegram_user is None:
        await message.answer(
            "Не удалось определить пользователя Telegram."
        )
        return

    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(
                User.telegram_id == telegram_user.id
            )
        )
        user = result.scalar_one_or_none()

        if user is None:
            await message.answer(
                "Сначала зарегистрируйся командой /start."
            )
            return

        info = await get_user_subscription_info(
            session,
            user.id,
        )

        if info is None:
            await message.answer(
                "У тебя пока нет действующей подписки.\n\n"
                "Чтобы получить бесплатный пробный период, "
                "используй команду /trial."
            )
            return

    expires_at = info["expires_at"]
    remaining_days = info["remaining_days"]

    if not isinstance(expires_at, datetime):
        raise TypeError(
            "Некорректный формат даты окончания подписки."
        )

    local_expiry = expires_at.astimezone(DISPLAY_TIMEZONE)

    await message.answer(
        "📋 Моя подписка\n\n"
        "Статус: активна\n"
        f"Действует до: {local_expiry:%d.%m.%Y %H:%M}\n"
        f"Осталось дней: {remaining_days}"
    )


@router.message()
async def handle_message(message: Message) -> None:
    logger.info(
        "Получено сообщение от пользователя %s",
        message.from_user.id if message.from_user else "unknown",
    )

    await message.answer(
        "Я пока умею отвечать на команду /start."
    )