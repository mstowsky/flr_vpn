import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
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
from app.services.payments import create_payment
from app.services.plans import get_active_plans
from app.services.subscriptions import (
    activate_trial_plan,
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
            subscription = await activate_trial_plan(
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


    plan_name = info["plan_name"]
    expires_at = info["expires_at"]
    remaining_days = info["remaining_days"]
    provisioning_status = info["provisioning_status"]

    if not isinstance(expires_at, datetime):
        raise TypeError(
            "Некорректный формат даты окончания подписки."
        )

    local_expiry = expires_at.astimezone(DISPLAY_TIMEZONE)

    if provisioning_status == "pending":
        status_text = "ожидает настройки VPN-доступа"
    elif provisioning_status == "completed":
        status_text = "доступ настроен"
    elif provisioning_status == "failed":
        status_text = "требуется повторная настройка VPN-доступа"
    else:
        status_text = "статус выдачи доступа не подтверждён"

    await message.answer(
        "📋 Моя подписка\n\n"
        f"Название: {plan_name}\n"
        f"Статус: {status_text}\n"
        f"Действует до: {local_expiry:%d.%m.%Y %H:%M}\n"
        f"Осталось дней: {remaining_days}"
    )


@router.message(Command("buy"))
async def buy_command(
    message: Message,
    command: CommandObject,
) -> None:
    telegram_user = message.from_user

    if telegram_user is None:
        await message.answer(
            "Не удалось определить пользователя Telegram."
        )
        return

    async with async_session_factory() as session:
        # Проверяем регистрацию пользователя.
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

        # Получаем доступные тарифы.
        plans = await get_active_plans(session)

        if not plans:
            await message.answer(
                "Сейчас нет доступных тарифов. "
                "Попробуй обратиться позже."
            )
            return

        # Если ID тарифа не указан — показываем список.
        if not command.args:
            lines = ["📋 Доступные тарифы:\n"]

            for plan in plans:
                traffic = (
                    f"{plan.traffic_limit_gb} ГБ"
                    if plan.traffic_limit_gb
                    else "без ограничения"
                )

                lines.append(
                    f"**{plan.id}. {plan.name}**\n"
                    f"Цена: {plan.price_rub} ₽\n"
                    f"Срок: {plan.duration_days} дней\n"
                    f"Устройства: {plan.max_devices}\n"
                    f"Трафик: {traffic}\n"
                )

            lines.append(
                "Для выбора тарифа отправь команду:\n"
                "/buy ID\n\n"
                "Например: /buy 2"
            )

            await message.answer("\n".join(lines))
            return

        # Проверяем корректность ID.
        try:
            plan_id = int(command.args.strip())
        except ValueError:
            await message.answer(
                "Укажи корректный ID тарифа.\n"
                "Например: /buy 2"
            )
            return

        if plan_id <= 0:
            await message.answer(
                "ID тарифа должен быть положительным числом."
            )
            return

        # Ищем тариф среди активных.
        plan = next(
            (item for item in plans if item.id == plan_id),
            None,
        )

        if plan is None:
            await message.answer(
                "Тариф не найден или больше недоступен.\n"
                "Посмотреть доступные тарифы: /buy"
            )
            return

        # Создаём заказ.
        try:
            payment = await create_payment(
                session,
                user_id=user.id,
                plan_id=plan.id,
            )
        except ValueError as exc:
            await message.answer(str(exc))
            return

    logger.info(
        "Создан заказ: payment_id=%s, user_id=%s, plan_id=%s",
        payment.id,
        user.id,
        plan.id,
    )

    await message.answer(
        "✅ Заказ успешно создан!\n\n"
        f"Номер заказа: #{payment.id}\n"
        f"Тариф: {plan.name}\n"
        f"Срок: {plan.duration_days} дней\n"
        f"Сумма: {payment.amount_rub} ₽\n"
        "Статус: ожидает оплаты.\n\n"
        "Информация об оплате будет доступна после "
        "подключения платёжного провайдера."
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