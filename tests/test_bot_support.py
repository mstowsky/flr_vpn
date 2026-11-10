from unittest.mock import AsyncMock

import pytest

from app.bot.handlers.user import (
    support_cancel,
    support_message_waiting,
    support_start,
)
from app.bot.keyboards.user import (
    get_support_cancel_keyboard,
    get_user_keyboard,
)
from app.bot.states.support import SupportStates


@pytest.mark.asyncio
async def test_support_start_sets_waiting_state():
    message = type(
        "MessageMock",
        (),
        {"answer": AsyncMock()},
    )()

    state = AsyncMock()

    await support_start(message, state)

    state.set_state.assert_awaited_once_with(
        SupportStates.waiting_for_message
    )

    response = message.answer.await_args

    assert "Опиши свою проблему" in response.args[0]
    assert response.kwargs["reply_markup"] == (
        get_support_cancel_keyboard()
    )


@pytest.mark.asyncio
async def test_support_cancel_clears_state():
    message = type(
        "MessageMock",
        (),
        {"answer": AsyncMock()},
    )()

    state = AsyncMock()

    await support_cancel(message, state)

    state.clear.assert_awaited_once()

    response = message.answer.await_args

    assert "отменено" in response.args[0]
    assert response.kwargs["reply_markup"] == get_user_keyboard()


@pytest.mark.asyncio
async def test_support_message_waiting_keeps_waiting_keyboard():
    message = type(
        "MessageMock",
        (),
        {"answer": AsyncMock()},
    )()

    await support_message_waiting(message)

    response = message.answer.await_args

    assert "Режим поддержки активен" in response.args[0]
    assert response.kwargs["reply_markup"] == (
        get_support_cancel_keyboard()
    )