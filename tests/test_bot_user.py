from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import ReplyKeyboardMarkup

from app.bot.handlers import user as bot_main
from app.bot.keyboards.user import (
    BUY_BUTTON_TEXT,
    SUBSCRIPTION_BUTTON_TEXT,
    SUPPORT_BUTTON_TEXT,
    TRIAL_BUTTON_TEXT,
    get_user_keyboard,
)


def make_message(telegram_id: int):
    """Создаёт имитацию сообщения от пользователя Telegram."""
    return SimpleNamespace(
        from_user=SimpleNamespace(id=telegram_id),
        answer=AsyncMock(),
    )


def make_session_context(user=None):
    """Создаёт имитацию асинхронной сессии SQLAlchemy."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = user

    session = MagicMock()
    session.execute = AsyncMock(return_value=result)

    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=False)

    return context, session


@pytest.mark.asyncio
async def test_subscription_command_requires_start():
    """Незарегистрированному пользователю предлагают выполнить /start."""
    message = make_message(123456789)
    session_context, _ = make_session_context(user=None)

    with patch.object(
        bot_main,
        "async_session_factory",
        return_value=session_context,
    ):
        await bot_main.subscription_command(message)

    message.answer.assert_awaited_once_with(
        "Сначала зарегистрируйся командой /start."
    )


@pytest.mark.asyncio
async def test_subscription_command_without_active_subscription():
    """Пользователю без активной подписки предлагают /trial."""
    message = make_message(123456789)
    user = SimpleNamespace(id=1, telegram_id=message.from_user.id)
    session_context, session = make_session_context(user=user)

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user

    pending_result = MagicMock()
    pending_result.scalar_one_or_none.return_value = None

    session.execute = AsyncMock(
        side_effect=[user_result, pending_result]
    )

    with (
        patch.object(
            bot_main,
            "async_session_factory",
            return_value=session_context,
        ),
        patch.object(
            bot_main,
            "get_user_subscription_info",
            new_callable=AsyncMock,
            return_value=None,
        ) as get_subscription_info,
    ):
        await bot_main.subscription_command(message)

    get_subscription_info.assert_awaited_once_with(session, user.id)

    message.answer.assert_awaited_once_with(
        "У тебя пока нет действующей подписки.\n\n"
        "Чтобы получить бесплатный пробный период, "
        "используй команду /trial."
    )



@pytest.mark.asyncio
async def test_subscription_command_shows_active_subscription():
    """Для настроенного доступа показываются название, статус и срок подписки."""
    message = make_message(123456789)
    user = SimpleNamespace(id=1, telegram_id=message.from_user.id)
    session_context, session = make_session_context(user=user)

    expires_at = datetime(
        2026, 11, 1, 12, 0, tzinfo=UTC
    )
    subscription_info = {
        "status": "active",
        "plan_name": "Пробный период",
        "expires_at": expires_at,
        "remaining_days": 10,
        "provisioning_status": "completed",
    }

    with (
        patch.object(
            bot_main,
            "async_session_factory",
            return_value=session_context,
        ),
        patch.object(
            bot_main,
            "get_user_subscription_info",
            new_callable=AsyncMock,
            return_value=subscription_info,
        ) as get_subscription_info,
    ):
        await bot_main.subscription_command(message)

    get_subscription_info.assert_awaited_once_with(session, user.id)

    local_expiry = expires_at.astimezone(bot_main.DISPLAY_TIMEZONE)
    expected_message = (
        "📋 Моя подписка\n\n"
        "Название: Пробный период\n"
        "Статус: доступ настроен\n"
        f"Действует до: {local_expiry:%d.%m.%Y %H:%M}\n"
        "Осталось дней: 10"
    )

    message.answer.assert_awaited_once_with(expected_message)


@pytest.mark.asyncio
async def test_subscription_command_without_telegram_user():
    """Если Telegram не передал отправителя, команда корректно завершает работу."""
    message = SimpleNamespace(
        from_user=None,
        answer=AsyncMock(),
    )

    await bot_main.subscription_command(message)

    message.answer.assert_awaited_once_with(
        "Не удалось определить пользователя Telegram."
    )


@pytest.mark.asyncio
async def test_subscription_command_shows_pending_provisioning():
    """Для ожидающей задачи бот сообщает, что VPN-доступ ещё настраивается."""
    message = make_message(123456789)
    user = SimpleNamespace(id=1, telegram_id=message.from_user.id)
    session_context, session = make_session_context(user=user)

    expires_at = datetime(
        2026, 11, 1, 12, 0, tzinfo=UTC
    )
    subscription_info = {
        "status": "active",
        "plan_name": "Пробный период",
        "expires_at": expires_at,
        "remaining_days": 10,
        "provisioning_status": "pending",
    }

    with (
        patch.object(
            bot_main,
            "async_session_factory",
            return_value=session_context,
        ),
        patch.object(
            bot_main,
            "get_user_subscription_info",
            new_callable=AsyncMock,
            return_value=subscription_info,
        ) as get_subscription_info,
    ):
        await bot_main.subscription_command(message)

    get_subscription_info.assert_awaited_once_with(session, user.id)

    local_expiry = expires_at.astimezone(bot_main.DISPLAY_TIMEZONE)
    expected_message = (
        "📋 Моя подписка\n\n"
        "Название: Пробный период\n"
        "Статус: ожидает настройки VPN-доступа\n"
        f"Действует до: {local_expiry:%d.%m.%Y %H:%M}\n"
        "Осталось дней: 10"
    )

    message.answer.assert_awaited_once_with(expected_message)


def test_user_keyboard_contains_expected_buttons():
    keyboard = get_user_keyboard()

    assert isinstance(keyboard, ReplyKeyboardMarkup)

    button_texts = [
        button.text
        for row in keyboard.keyboard
        for button in row
    ]

    assert button_texts == [
        SUBSCRIPTION_BUTTON_TEXT,
        TRIAL_BUTTON_TEXT,
        BUY_BUTTON_TEXT,
        SUPPORT_BUTTON_TEXT,
    ]


@pytest.mark.asyncio
async def test_buy_command_shows_active_plans_from_menu_button():
    """Нажатие кнопки выбора тарифа показывает доступные тарифы."""
    message = make_message(123456789)
    user = SimpleNamespace(id=1, telegram_id=message.from_user.id)

    plans = [make_plan()]

    session_context, session = make_session_context(user=user)

    with (
        patch.object(
            bot_main,
            "async_session_factory",
            return_value=session_context,
        ),
        patch.object(
            bot_main,
            "get_active_plans",
            new_callable=AsyncMock,
            return_value=plans,
        ) as get_active_plans,
    ):
        await bot_main.buy_command(message)

    get_active_plans.assert_awaited_once_with(session)

    response = message.answer.await_args

    assert "Доступные тарифы" in response.args[0]
    assert response.kwargs["reply_markup"] is not None


def test_user_keyboard_is_resizable():
    keyboard = get_user_keyboard()

    assert keyboard.resize_keyboard is True


def make_plan(
    plan_id: int = 1,
    name: str = "Стандарт",
    price_rub: int = 300,
    duration_days: int = 30,
    max_devices: int = 2,
    traffic_limit_gb: int | None = 100,
):
    """Создаёт имитацию тарифа."""
    return SimpleNamespace(
        id=plan_id,
        name=name,
        price_rub=price_rub,
        duration_days=duration_days,
        max_devices=max_devices,
        traffic_limit_gb=traffic_limit_gb,
    )


def make_command(args: str | None = None):
    """Создаёт имитацию аргументов Telegram-команды."""
    return SimpleNamespace(args=args)


@pytest.mark.asyncio
async def test_buy_command_shows_active_plans():
    """Команда /buy без аргументов показывает список доступных тарифов."""
    message = make_message(123456789)
    user = SimpleNamespace(id=1, telegram_id=message.from_user.id)

    plans = [
        make_plan(
            plan_id=1,
            name="Базовый",
            price_rub=200,
            duration_days=30,
            max_devices=1,
            traffic_limit_gb=50,
        ),
        make_plan(
            plan_id=2,
            name="Премиум",
            price_rub=500,
            duration_days=90,
            max_devices=3,
            traffic_limit_gb=None,
        ),
    ]

    session_context, session = make_session_context(user=user)

    with (
        patch.object(
            bot_main,
            "async_session_factory",
            return_value=session_context,
        ),
        patch.object(
            bot_main,
            "get_active_plans",
            new_callable=AsyncMock,
            return_value=plans,
        ) as get_active_plans,
        patch.object(
            bot_main,
            "create_payment",
            new_callable=AsyncMock,
        ) as create_payment,
    ):
        await bot_main.buy_command(message, make_command())

    get_active_plans.assert_awaited_once_with(session)
    create_payment.assert_not_awaited()

    response = message.answer.await_args.args[0]

    assert "Доступные тарифы" in response
    assert "Базовый" in response
    assert "200 ₽" in response
    assert "30 дней" in response
    assert "Устройства: 1" in response
    assert "Трафик: 50 ГБ" in response

    assert "Премиум" in response
    assert "500 ₽" in response
    assert "90 дней" in response
    assert "Устройства: 3" in response
    assert "Трафик: без ограничения" in response

    assert "/buy 2" in response


@pytest.mark.asyncio
async def test_buy_command_without_active_plans():
    """Если активных тарифов нет, бот сообщает об этом пользователю."""
    message = make_message(123456789)
    user = SimpleNamespace(id=1, telegram_id=message.from_user.id)

    session_context, session = make_session_context(user=user)

    with (
        patch.object(
            bot_main,
            "async_session_factory",
            return_value=session_context,
        ),
        patch.object(
            bot_main,
            "get_active_plans",
            new_callable=AsyncMock,
            return_value=[],
        ) as get_active_plans,
        patch.object(
            bot_main,
            "create_payment",
            new_callable=AsyncMock,
        ) as create_payment,
    ):
        await bot_main.buy_command(message, make_command())

    get_active_plans.assert_awaited_once_with(session)
    create_payment.assert_not_awaited()

    message.answer.assert_awaited_once_with(
        "Сейчас нет доступных тарифов. "
        "Попробуй обратиться позже."
    )


@pytest.mark.asyncio
async def test_buy_command_creates_payment():
    """Команда /buy с ID тарифа создаёт заказ для выбранного тарифа."""
    message = make_message(123456789)
    user = SimpleNamespace(id=10, telegram_id=message.from_user.id)
    plan = make_plan(plan_id=2)

    payment = SimpleNamespace(
        id=100,
        amount_rub=300,
    )

    session_context, session = make_session_context(user=user)

    with (
        patch.object(
            bot_main,
            "async_session_factory",
            return_value=session_context,
        ),
        patch.object(
            bot_main,
            "get_active_plans",
            new_callable=AsyncMock,
            return_value=[plan],
        ),
        patch.object(
            bot_main,
            "create_payment",
            new_callable=AsyncMock,
            return_value=payment,
        ) as create_payment,
    ):
        await bot_main.buy_command(message, make_command("2"))

    create_payment.assert_awaited_once_with(
        session,
        user_id=user.id,
        plan_id=plan.id,
    )


@pytest.mark.asyncio
async def test_buy_command_confirms_payment_creation():
    """После создания заказа бот показывает его номер, тариф, срок и сумму."""
    message = make_message(123456789)
    user = SimpleNamespace(id=10, telegram_id=message.from_user.id)

    plan = make_plan(
        plan_id=2,
        name="Премиум",
        price_rub=500,
        duration_days=90,
    )

    payment = SimpleNamespace(
        id=100,
        amount_rub=500,
    )

    session_context, _ = make_session_context(user=user)

    with (
        patch.object(
            bot_main,
            "async_session_factory",
            return_value=session_context,
        ),
        patch.object(
            bot_main,
            "get_active_plans",
            new_callable=AsyncMock,
            return_value=[plan],
        ),
        patch.object(
            bot_main,
            "create_payment",
            new_callable=AsyncMock,
            return_value=payment,
        ),
    ):
        await bot_main.buy_command(message, make_command("2"))

    message.answer.assert_awaited_once_with(
        "✅ Заказ успешно создан!\n\n"
        "Номер заказа: #100\n"
        "Тариф: Премиум\n"
        "Срок: 90 дней\n"
        "Сумма: 500 ₽\n"
        "Статус: ожидает оплаты.\n\n"
        "Информация об оплате будет доступна после "
        "подключения платёжного провайдера."
    )


@pytest.mark.asyncio
async def test_buy_command_rejects_invalid_plan_id():
    """Если ID тарифа не является числом, бот сообщает об ошибке."""
    message = make_message(123456789)
    user = SimpleNamespace(id=1, telegram_id=message.from_user.id)

    session_context, _ = make_session_context(user=user)

    with (
        patch.object(
            bot_main,
            "async_session_factory",
            return_value=session_context,
        ),
        patch.object(
            bot_main,
            "get_active_plans",
            new_callable=AsyncMock,
            return_value=[make_plan()],
        ),
        patch.object(
            bot_main,
            "create_payment",
            new_callable=AsyncMock,
        ) as create_payment,
    ):
        await bot_main.buy_command(message, make_command("abc"))

    create_payment.assert_not_awaited()

    message.answer.assert_awaited_once_with(
        "Укажи корректный ID тарифа.\n"
        "Например: /buy 2"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("plan_id", ["0", "-1"])
async def test_buy_command_rejects_non_positive_plan_id(plan_id):
    """ID тарифа должен быть положительным числом."""
    message = make_message(123456789)
    user = SimpleNamespace(id=1, telegram_id=message.from_user.id)

    session_context, _ = make_session_context(user=user)

    with (
        patch.object(
            bot_main,
            "async_session_factory",
            return_value=session_context,
        ),
        patch.object(
            bot_main,
            "get_active_plans",
            new_callable=AsyncMock,
            return_value=[make_plan()],
        ),
        patch.object(
            bot_main,
            "create_payment",
            new_callable=AsyncMock,
        ) as create_payment,
    ):
        await bot_main.buy_command(message, make_command(plan_id))

    create_payment.assert_not_awaited()

    message.answer.assert_awaited_once_with(
        "ID тарифа должен быть положительным числом."
    )


@pytest.mark.asyncio
async def test_buy_command_rejects_missing_plan():
    """Если тариф с указанным ID отсутствует, заказ не создаётся."""
    message = make_message(123456789)
    user = SimpleNamespace(id=1, telegram_id=message.from_user.id)

    session_context, _ = make_session_context(user=user)

    with (
        patch.object(
            bot_main,
            "async_session_factory",
            return_value=session_context,
        ),
        patch.object(
            bot_main,
            "get_active_plans",
            new_callable=AsyncMock,
            return_value=[make_plan(plan_id=1)],
        ),
        patch.object(
            bot_main,
            "create_payment",
            new_callable=AsyncMock,
        ) as create_payment,
    ):
        await bot_main.buy_command(message, make_command("999"))

    create_payment.assert_not_awaited()

    message.answer.assert_awaited_once_with(
        "Тариф не найден или больше недоступен.\n"
        "Посмотреть доступные тарифы: /buy"
    )


@pytest.mark.asyncio
async def test_buy_command_rejects_inactive_plan():
    """Тариф, отсутствующий среди активных, нельзя выбрать для заказа."""
    message = make_message(123456789)
    user = SimpleNamespace(id=1, telegram_id=message.from_user.id)

    # В список активных тарифов тариф с ID 2 не попадает.
    session_context, _ = make_session_context(user=user)

    with (
        patch.object(
            bot_main,
            "async_session_factory",
            return_value=session_context,
        ),
        patch.object(
            bot_main,
            "get_active_plans",
            new_callable=AsyncMock,
            return_value=[make_plan(plan_id=1)],
        ),
        patch.object(
            bot_main,
            "create_payment",
            new_callable=AsyncMock,
        ) as create_payment,
    ):
        await bot_main.buy_command(message, make_command("2"))

    create_payment.assert_not_awaited()

    message.answer.assert_awaited_once_with(
        "Тариф не найден или больше недоступен.\n"
        "Посмотреть доступные тарифы: /buy"
    )


@pytest.mark.asyncio
async def test_buy_command_requires_start():
    """Незарегистрированному пользователю предлагают выполнить /start."""
    message = make_message(123456789)
    session_context, _ = make_session_context(user=None)

    with (
        patch.object(
            bot_main,
            "async_session_factory",
            return_value=session_context,
        ),
        patch.object(
            bot_main,
            "get_active_plans",
            new_callable=AsyncMock,
        ) as get_active_plans,
        patch.object(
            bot_main,
            "create_payment",
            new_callable=AsyncMock,
        ) as create_payment,
    ):
        await bot_main.buy_command(message, make_command())

    get_active_plans.assert_not_awaited()
    create_payment.assert_not_awaited()

    message.answer.assert_awaited_once_with(
        "Сначала зарегистрируйся командой /start."
    )


@pytest.mark.asyncio
async def test_buy_command_without_telegram_user():
    """Если отправитель не определён, команда корректно завершается."""
    message = SimpleNamespace(
        from_user=None,
        answer=AsyncMock(),
    )

    with (
        patch.object(
            bot_main,
            "get_active_plans",
            new_callable=AsyncMock,
        ) as get_active_plans,
        patch.object(
            bot_main,
            "create_payment",
            new_callable=AsyncMock,
        ) as create_payment,
    ):
        await bot_main.buy_command(message, make_command())

    get_active_plans.assert_not_awaited()
    create_payment.assert_not_awaited()

    message.answer.assert_awaited_once_with(
        "Не удалось определить пользователя Telegram."
    )


@pytest.mark.asyncio
async def test_buy_command_handles_payment_creation_error():
    """Если сервис не может создать заказ, бот показывает причину ошибки."""
    message = make_message(123456789)
    user = SimpleNamespace(id=1, telegram_id=message.from_user.id)
    plan = make_plan(plan_id=2)

    session_context, session = make_session_context(user=user)

    with (
        patch.object(
            bot_main,
            "async_session_factory",
            return_value=session_context,
        ),
        patch.object(
            bot_main,
            "get_active_plans",
            new_callable=AsyncMock,
            return_value=[plan],
        ),
        patch.object(
            bot_main,
            "create_payment",
            new_callable=AsyncMock,
            side_effect=ValueError("Активный тариф с ID 2 не найден."),
        ) as create_payment,
    ):
        await bot_main.buy_command(message, make_command("2"))

    create_payment.assert_awaited_once_with(
        session,
        user_id=user.id,
        plan_id=plan.id,
    )

    message.answer.assert_awaited_once_with(
        "Активный тариф с ID 2 не найден."
    )


@pytest.mark.asyncio
async def test_subscription_command_shows_pending_payment():
    """Если подписки нет, но есть неоплаченная заявка,
    показывается название выбранного тарифа.
    """
    message = make_message(123456789)
    user = SimpleNamespace(
        id=1,
        telegram_id=message.from_user.id,
    )

    session_context, session = make_session_context(user=user)

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user

    pending_result = MagicMock()
    pending_result.scalar_one_or_none.return_value = "1 год"

    session.execute = AsyncMock(
        side_effect=[user_result, pending_result]
    )

    with (
        patch.object(
            bot_main,
            "async_session_factory",
            return_value=session_context,
        ),
        patch.object(
            bot_main,
            "get_user_subscription_info",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        await bot_main.subscription_command(message)

    message.answer.assert_awaited_once_with(
        "У тебя пока нет действующей подписки.\n\n"
        "📋 В системе имеется заявка на подключение "
        "подписки «1 год».\n\n"
        "После подтверждения оплаты подписка будет "
        "активирована, а задача на настройку VPN-доступа "
        "появится в очереди."
    )