import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from app.bot.keyboards.user import (
    BUY_BUTTON_TEXT,
    CANCEL_SUPPORT_BUTTON_TEXT,
    SUBSCRIPTION_BUTTON_TEXT,
    SUPPORT_BUTTON_TEXT,
    TRIAL_BUTTON_TEXT,
    get_buy_keyboard,
    get_support_cancel_keyboard,
    get_user_keyboard,
)
from app.bot.states.support import SupportStates
from app.config import DISPLAY_TIMEZONE
from app.database import async_session_factory
from app.models.payment import Payment
from app.models.plan import Plan
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
async def cmd_start(
    message: Message,
    state: FSMContext,
) -> None:
    telegram_user = message.from_user

    await state.clear()

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



@router.message(F.text == SUPPORT_BUTTON_TEXT)
async def support_start(
    message: Message,
    state: FSMContext,
) -> None:
    """Включает режим ожидания сообщения для поддержки."""

    await state.set_state(
        SupportStates.waiting_for_message
    )

    await message.answer(
        "🆘 Опиши свою проблему или задай вопрос.\n\n"
        "Напиши сообщение, и мы поможем тебе.\n\n"
        "Чтобы отменить обращение, нажми кнопку «Отмена» "
        "или отправь команду /cancel.",
        reply_markup=get_support_cancel_keyboard(),
    )


@router.message(
    SupportStates.waiting_for_message,
    Command("cancel"),
)
@router.message(
    SupportStates.waiting_for_message,
    F.text == CANCEL_SUPPORT_BUTTON_TEXT,
)
async def support_cancel(
    message: Message,
    state: FSMContext,
) -> None:
    """Отменяет режим ожидания сообщения для поддержки."""

    await state.clear()

    await message.answer(
        "Создание обращения отменено.",
        reply_markup=get_user_keyboard(),
    )


@router.message(SupportStates.waiting_for_message)
async def support_message_waiting(
    message: Message,
) -> None:
    """Временно обрабатывает сообщение в режиме поддержки."""

    await message.answer(
        "Режим поддержки активен.\n\n"
        "Передача сообщений администратору будет "
        "подключена на следующем этапе.\n\n"
        "Чтобы выйти, нажми «Отмена» или отправь /cancel.",
        reply_markup=get_support_cancel_keyboard(),
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
            # Ищем последнюю неоплаченную заявку пользователя.
            pending_plan_result = await session.execute(
                select(Plan.name)
                .join(
                    Payment,
                    Payment.plan_id == Plan.id,
                )
                .where(
                    Payment.user_id == user.id,
                    Payment.status == "pending",
                )
                .order_by(
                    Payment.created_at.desc(),
                    Payment.id.desc(),
                )
                .limit(1)
            )

            pending_plan_name = (
                pending_plan_result.scalar_one_or_none()
            )

            if pending_plan_name is not None:
                await message.answer(
                    "У тебя пока нет действующей подписки.\n\n"
                    "📋 В системе имеется заявка на подключение "
                    f"подписки «{pending_plan_name}».\n\n"
                    "После подтверждения оплаты подписка будет "
                    "активирована, а задача на настройку VPN-доступа "
                    "появится в очереди."
                )
            else:
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


@router.message(F.text == BUY_BUTTON_TEXT)
@router.message(Command("buy"))
async def buy_command(
    message: Message,
    command: CommandObject | None = None,
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
        if command is None or not command.args:
            lines = ["📋 Доступные тарифы:\n"]

            for plan in plans:
                traffic = (
                    f"{plan.traffic_limit_gb} ГБ"
                    if plan.traffic_limit_gb
                    else "без ограничения"
                )

                lines.append(
                    f"*{plan.name} (ID={plan.id})*\n"
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

            await message.answer(
                "\n".join(lines),
                reply_markup=get_buy_keyboard(plans),
                parse_mode=ParseMode.MARKDOWN,
            )
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


@router.callback_query(F.data.startswith("buy:"))
async def buy_plan_callback(callback: CallbackQuery) -> None:
    """Создаёт заказ после выбора тарифа через inline-клавиатуру."""

    telegram_user = callback.from_user

    if telegram_user is None:
        await callback.answer(
            "Не удалось определить пользователя Telegram.",
            show_alert=True,
        )
        return

    # Получаем ID тарифа из callback_data.
    try:
        plan_id = int(callback.data.partition(":")[2])
    except (ValueError, AttributeError):
        await callback.answer(
            "Некорректный выбор тарифа.",
            show_alert=True,
        )
        return

    if plan_id <= 0:
        await callback.answer(
            "Некорректный ID тарифа.",
            show_alert=True,
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
            await callback.answer(
                "Сначала зарегистрируйся командой /start.",
                show_alert=True,
            )
            return

        # Проверяем, что тариф всё ещё активен.
        plans = await get_active_plans(session)

        plan = next(
            (item for item in plans if item.id == plan_id),
            None,
        )

        if plan is None:
            await callback.answer(
                "Тариф больше недоступен. "
                "Обнови список командой /buy.",
                show_alert=True,
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
            await callback.answer(
                str(exc),
                show_alert=True,
            )
            return

    logger.info(
        "Создан заказ через клавиатуру: "
        "payment_id=%s, user_id=%s, plan_id=%s",
        payment.id,
        user.id,
        plan.id,
    )

    await callback.answer("Заказ успешно создан!")

    # Убираем клавиатуру после выбора тарифа.
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(
            reply_markup=None,
        )

        await callback.message.answer(
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