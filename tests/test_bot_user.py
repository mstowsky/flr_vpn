from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.bot.handlers import user as bot_main


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
    """Для активной подписки показываются статус, дата окончания и остаток дней."""
    message = make_message(123456789)
    user = SimpleNamespace(id=1, telegram_id=message.from_user.id)
    session_context, session = make_session_context(user=user)

    expires_at = datetime(
        2026, 11, 1, 12, 0, tzinfo=timezone.utc
    )
    subscription_info = {
        "status": "active",
        "expires_at": expires_at,
        "remaining_days": 10,
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
        "Статус: активна\n"
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