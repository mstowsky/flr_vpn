from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.bot.handlers import admin as bot_main


def make_message(telegram_id: int):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=telegram_id),
        answer=AsyncMock(),
        bot=SimpleNamespace(
            send_message=AsyncMock(),
        ),
    )


@pytest.mark.asyncio
async def test_admin_command_allows_admin():
    message = make_message(bot_main.ADMIN_TELEGRAM_ID)

    await bot_main.admin_command(message)

    message.answer.assert_awaited_once()
    assert "Доступ подтверждён" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_admin_command_rejects_non_admin():
    message = make_message(bot_main.ADMIN_TELEGRAM_ID + 1)

    await bot_main.admin_command(message)

    message.answer.assert_awaited_once_with(
        "У вас нет доступа к этой команде."
    )


@pytest.mark.asyncio
async def test_tasks_command_rejects_non_admin():
    message = make_message(bot_main.ADMIN_TELEGRAM_ID + 1)

    await bot_main.tasks_command(message)

    message.answer.assert_awaited_once_with(
        "У вас нет доступа к этой команде."
    )


@pytest.mark.asyncio
async def test_tasks_command_reports_empty_queue(monkeypatch):
    message = make_message(bot_main.ADMIN_TELEGRAM_ID)

    session = MagicMock()
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=session)
    session_context.__aexit__ = AsyncMock(return_value=False)

    monkeypatch.setattr(
        bot_main,
        "async_session_factory",
        MagicMock(return_value=session_context),
    )
    monkeypatch.setattr(
        bot_main,
        "get_pending_provisioning_tasks",
        AsyncMock(return_value=[]),
    )

    await bot_main.tasks_command(message)

    message.answer.assert_awaited_once_with(
        "Очередь задач пуста. Ожидающих задач нет."
    )


@pytest.mark.asyncio
async def test_complete_command_rejects_non_admin():
    message = make_message(bot_main.ADMIN_TELEGRAM_ID + 1)
    command = SimpleNamespace(args="1")

    await bot_main.complete_command(message, command)

    message.answer.assert_awaited_once_with(
        "У вас нет доступа к этой команде."
    )


@pytest.mark.asyncio
async def test_complete_command_requires_task_id():
    message = make_message(bot_main.ADMIN_TELEGRAM_ID)
    command = SimpleNamespace(args=None)

    await bot_main.complete_command(message, command)

    message.answer.assert_awaited_once()
    assert "Укажи ID задачи" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_complete_command_rejects_invalid_task_id():
    message = make_message(bot_main.ADMIN_TELEGRAM_ID)
    command = SimpleNamespace(args="abc")

    await bot_main.complete_command(message, command)

    message.answer.assert_awaited_once()
    assert "целым числом" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_complete_command_reports_service_error(monkeypatch):
    message = make_message(bot_main.ADMIN_TELEGRAM_ID)
    command = SimpleNamespace(args="999")

    session = MagicMock()
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=session)
    session_context.__aexit__ = AsyncMock(return_value=False)

    monkeypatch.setattr(
        bot_main,
        "async_session_factory",
        MagicMock(return_value=session_context),
    )
    monkeypatch.setattr(
        bot_main,
        "complete_provisioning_task",
        AsyncMock(side_effect=ValueError("Задача с ID 999 не найдена")),
    )

    await bot_main.complete_command(message, command)

    message.answer.assert_awaited_once_with(
        "Задача с ID 999 не найдена"
    )


@pytest.mark.asyncio
async def test_fail_command_rejects_non_admin(monkeypatch):
    message = make_message(bot_main.ADMIN_TELEGRAM_ID + 1)
    command = SimpleNamespace(args="1 Ошибка")

    service = AsyncMock()
    monkeypatch.setattr(bot_main, "fail_provisioning_task", service)

    await bot_main.fail_command(message, command)

    message.answer.assert_awaited_once_with(
        "У вас нет доступа к этой команде."
    )
    service.assert_not_awaited()


@pytest.mark.asyncio
async def test_fail_command_requires_reason():
    message = make_message(bot_main.ADMIN_TELEGRAM_ID)
    command = SimpleNamespace(args="12")

    await bot_main.fail_command(message, command)

    message.answer.assert_awaited_once()
    assert "причину ошибки" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_fail_command_rejects_invalid_task_id():
    message = make_message(bot_main.ADMIN_TELEGRAM_ID)
    command = SimpleNamespace(args="abc Ошибка")

    await bot_main.fail_command(message, command)

    message.answer.assert_awaited_once()
    assert "целым числом" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_fail_command_reports_service_error(monkeypatch):
    message = make_message(bot_main.ADMIN_TELEGRAM_ID)
    command = SimpleNamespace(args="999 Ошибка")

    session = MagicMock()
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=session)
    session_context.__aexit__ = AsyncMock(return_value=False)

    monkeypatch.setattr(
        bot_main,
        "async_session_factory",
        MagicMock(return_value=session_context),
    )
    monkeypatch.setattr(
        bot_main,
        "fail_provisioning_task",
        AsyncMock(side_effect=ValueError("Задача не найдена")),
    )

    await bot_main.fail_command(message, command)

    message.answer.assert_awaited_once_with("Задача не найдена")


@pytest.mark.asyncio
async def test_retry_command_rejects_non_admin(monkeypatch):
    message = make_message(bot_main.ADMIN_TELEGRAM_ID + 1)
    command = SimpleNamespace(args="12")

    service = AsyncMock()
    monkeypatch.setattr(bot_main, "retry_provisioning_task", service)

    await bot_main.retry_command(message, command)

    message.answer.assert_awaited_once_with(
        "У вас нет доступа к этой команде."
    )
    service.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_command_requires_task_id():
    message = make_message(bot_main.ADMIN_TELEGRAM_ID)
    command = SimpleNamespace(args=None)

    await bot_main.retry_command(message, command)

    message.answer.assert_awaited_once()
    assert "Укажи ID" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_retry_command_rejects_invalid_task_id():
    message = make_message(bot_main.ADMIN_TELEGRAM_ID)
    command = SimpleNamespace(args="abc")

    await bot_main.retry_command(message, command)

    message.answer.assert_awaited_once()
    assert "целым числом" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_retry_command_reports_service_error(monkeypatch):
    message = make_message(bot_main.ADMIN_TELEGRAM_ID)
    command = SimpleNamespace(args="12")

    session = MagicMock()
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=session)
    session_context.__aexit__ = AsyncMock(return_value=False)

    monkeypatch.setattr(
        bot_main,
        "async_session_factory",
        MagicMock(return_value=session_context),
    )
    monkeypatch.setattr(
        bot_main,
        "retry_provisioning_task",
        AsyncMock(side_effect=ValueError("Повторить можно только неудачную задачу")),
    )

    await bot_main.retry_command(message, command)

    message.answer.assert_awaited_once_with(
        "Повторить можно только неудачную задачу"
    )


@pytest.mark.asyncio
async def test_retry_command_success(monkeypatch):
    message = make_message(bot_main.ADMIN_TELEGRAM_ID)
    command = SimpleNamespace(args="12")
    task = SimpleNamespace(id=12)

    session = MagicMock()
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=session)
    session_context.__aexit__ = AsyncMock(return_value=False)

    monkeypatch.setattr(
        bot_main,
        "async_session_factory",
        MagicMock(return_value=session_context),
    )
    service = AsyncMock(return_value=task)
    monkeypatch.setattr(bot_main, "retry_provisioning_task", service)

    await bot_main.retry_command(message, command)

    service.assert_awaited_once_with(session, task_id=12)
    message.answer.assert_awaited_once_with(
        "Задача #12 возвращена в очередь.\n"
        "Проверь очередь командой /tasks."
    )


def make_session_context():
    session = MagicMock()

    session.get = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.flush = AsyncMock()

    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(
        return_value=session
    )
    session_context.__aexit__ = AsyncMock(
        return_value=False
    )

    return session, session_context


@pytest.mark.asyncio
async def test_test_pay_command_is_disabled_when_test_commands_are_disabled(
    monkeypatch,
):
    message = make_message(bot_main.ADMIN_TELEGRAM_ID)
    command = SimpleNamespace(args="12")
    service = AsyncMock()

    monkeypatch.setattr(bot_main, "ENABLE_TEST_COMMANDS", False)
    monkeypatch.setattr(bot_main, "process_successful_payment", service)

    await bot_main.test_pay_command(message, command)

    message.answer.assert_awaited_once_with(
        "Тестовые команды отключены."
    )
    service.assert_not_awaited()


@pytest.mark.asyncio
async def test_test_pay_command_rejects_non_admin(monkeypatch):
    message = make_message(bot_main.ADMIN_TELEGRAM_ID + 1)
    command = SimpleNamespace(args="12")
    service = AsyncMock()

    monkeypatch.setattr(bot_main, "ENABLE_TEST_COMMANDS", True)
    monkeypatch.setattr(bot_main, "process_successful_payment", service)

    await bot_main.test_pay_command(message, command)

    message.answer.assert_awaited_once_with(
        "У вас нет доступа к этой команде."
    )
    service.assert_not_awaited()


@pytest.mark.asyncio
async def test_test_pay_command_requires_payment_id(monkeypatch):
    message = make_message(bot_main.ADMIN_TELEGRAM_ID)
    command = SimpleNamespace(args=None)

    monkeypatch.setattr(bot_main, "ENABLE_TEST_COMMANDS", True)

    await bot_main.test_pay_command(message, command)

    message.answer.assert_awaited_once()
    assert "Укажи ID заказа" in message.answer.await_args.args[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("payment_id", ["abc", "1.5"])
async def test_test_pay_command_rejects_invalid_payment_id(
    monkeypatch,
    payment_id,
):
    message = make_message(bot_main.ADMIN_TELEGRAM_ID)
    command = SimpleNamespace(args=payment_id)

    monkeypatch.setattr(bot_main, "ENABLE_TEST_COMMANDS", True)

    await bot_main.test_pay_command(message, command)

    message.answer.assert_awaited_once()
    assert "целым числом" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_test_pay_command_reports_missing_payment(monkeypatch):
    message = make_message(bot_main.ADMIN_TELEGRAM_ID)
    command = SimpleNamespace(args="999")
    session, session_context = make_session_context()

    monkeypatch.setattr(bot_main, "ENABLE_TEST_COMMANDS", True)
    monkeypatch.setattr(
        bot_main,
        "async_session_factory",
        MagicMock(return_value=session_context),
    )
    service = AsyncMock(return_value=None)
    monkeypatch.setattr(
        bot_main,
        "process_successful_payment",
        service,
    )

    await bot_main.test_pay_command(message, command)

    service.assert_awaited_once_with(session, payment_id=999)
    message.answer.assert_awaited_once_with(
        "Заказ #999 не найден."
    )


@pytest.mark.asyncio
async def test_test_pay_command_reports_payment_processing_error(
    monkeypatch,
):
    message = make_message(bot_main.ADMIN_TELEGRAM_ID)
    command = SimpleNamespace(args="12")
    session, session_context = make_session_context()

    monkeypatch.setattr(bot_main, "ENABLE_TEST_COMMANDS", True)
    monkeypatch.setattr(
        bot_main,
        "async_session_factory",
        MagicMock(return_value=session_context),
    )
    service = AsyncMock(
        side_effect=ValueError("Нельзя подтвердить отменённый заказ.")
    )
    monkeypatch.setattr(
        bot_main,
        "process_successful_payment",
        service,
    )

    await bot_main.test_pay_command(message, command)

    service.assert_awaited_once_with(session, payment_id=12)
    message.answer.assert_awaited_once_with(
        "Нельзя подтвердить отменённый заказ."
    )


@pytest.mark.asyncio
async def test_test_pay_command_success(monkeypatch):
    message = make_message(bot_main.ADMIN_TELEGRAM_ID)
    command = SimpleNamespace(args="12")
    session, session_context = make_session_context()
    payment = SimpleNamespace(id=12)

    monkeypatch.setattr(bot_main, "ENABLE_TEST_COMMANDS", True)
    monkeypatch.setattr(
        bot_main,
        "async_session_factory",
        MagicMock(return_value=session_context),
    )
    service = AsyncMock(return_value=payment)
    monkeypatch.setattr(
        bot_main,
        "process_successful_payment",
        service,
    )

    await bot_main.test_pay_command(message, command)

    service.assert_awaited_once_with(session, payment_id=12)
    message.answer.assert_awaited_once_with(
        "✅ Тестовая оплата заказа #12 подтверждена.\n\n"
        "Подписка активирована.\n"
        "Задача на подключение VPN создана.\n\n"
        "Проверь очередь командой /tasks."
    )



@pytest.mark.asyncio
async def test_complete_command_sends_activation_notification_to_user(
    monkeypatch,
):
    message = make_message(bot_main.ADMIN_TELEGRAM_ID)
    command = SimpleNamespace(args="12")

    task = SimpleNamespace(
        id=12,
        task_type="create",
        user_id=5,
        subscription_id=7,
    )

    user = SimpleNamespace(telegram_id=123456789)
    subscription = SimpleNamespace(plan_id=2)
    plan = SimpleNamespace(name="1 месяц 2 устройства")

    session, session_context = make_session_context()
    session.get = AsyncMock(
        side_effect=[user, subscription, plan]
    )

    monkeypatch.setattr(
        bot_main,
        "async_session_factory",
        MagicMock(return_value=session_context),
    )
    monkeypatch.setattr(
        bot_main,
        "complete_provisioning_task",
        AsyncMock(return_value=task),
    )

    await bot_main.complete_command(message, command)

    message.bot.send_message.assert_awaited_once_with(
        chat_id=123456789,
        text=(
            "✅ Ваша подписка "
            "«1 месяц 2 устройства» активирована."
        ),
    )

    message.answer.assert_awaited_once_with(
        "Задача #12 отмечена выполненной."
    )


@pytest.mark.asyncio
async def test_complete_command_sends_deactivation_notification_to_user(
    monkeypatch,
):
    message = make_message(bot_main.ADMIN_TELEGRAM_ID)
    command = SimpleNamespace(args="12")

    task = SimpleNamespace(
        id=12,
        task_type="disable",
        user_id=5,
        subscription_id=7,
    )

    user = SimpleNamespace(telegram_id=123456789)
    subscription = SimpleNamespace(plan_id=2)
    plan = SimpleNamespace(name="1 месяц 2 устройства")

    session, session_context = make_session_context()
    session.get = AsyncMock(
        side_effect=[user, subscription, plan]
    )

    monkeypatch.setattr(
        bot_main,
        "async_session_factory",
        MagicMock(return_value=session_context),
    )
    monkeypatch.setattr(
        bot_main,
        "complete_provisioning_task",
        AsyncMock(return_value=task),
    )

    await bot_main.complete_command(message, command)

    message.bot.send_message.assert_awaited_once_with(
        chat_id=123456789,
        text=(
            "❌ Ваша подписка "
            "«1 месяц 2 устройства» "
            "деактивирована."
        ),
    )

    message.answer.assert_awaited_once_with(
        "Задача #12 отмечена выполненной."
    )


@pytest.mark.asyncio
async def test_test_subs_deactivate_command_is_disabled(
    monkeypatch,
):
    message = make_message(bot_main.ADMIN_TELEGRAM_ID)
    command = SimpleNamespace(args="12")

    service = AsyncMock()

    monkeypatch.setattr(bot_main, "ENABLE_TEST_COMMANDS", False)
    monkeypatch.setattr(
        bot_main,
        "subscription_deactivate",
        service,
    )

    await bot_main.test_subs_deactivate_command(
        message,
        command,
    )

    message.answer.assert_awaited_once_with(
        "Тестовые команды отключены."
    )
    service.assert_not_awaited()


@pytest.mark.asyncio
async def test_test_subs_deactivate_command_rejects_non_admin(
    monkeypatch,
):
    message = make_message(bot_main.ADMIN_TELEGRAM_ID + 1)
    command = SimpleNamespace(args="12")

    service = AsyncMock()

    monkeypatch.setattr(bot_main, "ENABLE_TEST_COMMANDS", True)
    monkeypatch.setattr(
        bot_main,
        "subscription_deactivate",
        service,
    )

    await bot_main.test_subs_deactivate_command(
        message,
        command,
    )

    message.answer.assert_awaited_once_with(
        "У вас нет доступа к этой команде."
    )
    service.assert_not_awaited()


@pytest.mark.asyncio
async def test_test_subs_deactivate_command_requires_subscription_id(
    monkeypatch,
):
    message = make_message(bot_main.ADMIN_TELEGRAM_ID)
    command = SimpleNamespace(args=None)

    monkeypatch.setattr(bot_main, "ENABLE_TEST_COMMANDS", True)

    await bot_main.test_subs_deactivate_command(
        message,
        command,
    )

    assert "Укажи ID подписки" in message.answer.await_args.args[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("subscription_id", ["abc", "1.5", "0", "-1"])
async def test_test_subs_deactivate_command_rejects_invalid_id(
    monkeypatch,
    subscription_id,
):
    message = make_message(bot_main.ADMIN_TELEGRAM_ID)
    command = SimpleNamespace(args=subscription_id)

    monkeypatch.setattr(bot_main, "ENABLE_TEST_COMMANDS", True)

    await bot_main.test_subs_deactivate_command(
        message,
        command,
    )

    assert message.answer.await_count == 1


@pytest.mark.asyncio
async def test_test_subs_deactivate_command_reports_service_error(
    monkeypatch,
):
    message = make_message(bot_main.ADMIN_TELEGRAM_ID)
    command = SimpleNamespace(args="12")

    session, session_context = make_session_context()

    monkeypatch.setattr(bot_main, "ENABLE_TEST_COMMANDS", True)
    monkeypatch.setattr(
        bot_main,
        "async_session_factory",
        MagicMock(return_value=session_context),
    )

    service = AsyncMock(
        side_effect=ValueError("Действующая подписка с ID 12 не найдена.")
    )
    monkeypatch.setattr(
        bot_main,
        "subscription_deactivate",
        service,
    )

    await bot_main.test_subs_deactivate_command(
        message,
        command,
    )

    service.assert_awaited_once_with(
        session,
        subscription_id=12,
        force=True,
    )

    message.answer.assert_awaited_once_with(
        "Действующая подписка с ID 12 не найдена."
    )


@pytest.mark.asyncio
async def test_test_subs_deactivate_command_success(
    monkeypatch,
):
    message = make_message(bot_main.ADMIN_TELEGRAM_ID)
    command = SimpleNamespace(args="12")

    subscription = SimpleNamespace(id=12)
    session, session_context = make_session_context()

    monkeypatch.setattr(bot_main, "ENABLE_TEST_COMMANDS", True)
    monkeypatch.setattr(
        bot_main,
        "async_session_factory",
        MagicMock(return_value=session_context),
    )

    service = AsyncMock(return_value=subscription)
    monkeypatch.setattr(
        bot_main,
        "subscription_deactivate",
        service,
    )

    await bot_main.test_subs_deactivate_command(
        message,
        command,
    )

    service.assert_awaited_once_with(
        session,
        subscription_id=12,
        force=True,
    )

    message.answer.assert_awaited_once_with(
        "✅ Подписка #12 деактивирована.\n"
        "Статус изменён на cancelled.\n"
        "Задача на отключение VPN не создавалась."
    )


@pytest.mark.asyncio
async def test_subscription_deactivate_command_rejects_non_admin(
    monkeypatch,
):
    message = make_message(bot_main.ADMIN_TELEGRAM_ID + 1)
    command = SimpleNamespace(args="12")

    service = AsyncMock()
    monkeypatch.setattr(
        bot_main,
        "subscription_deactivate",
        service,
    )

    await bot_main.subscription_deactivate_command(
        message,
        command,
    )

    message.answer.assert_awaited_once_with(
        "У вас нет доступа к этой команде."
    )
    service.assert_not_awaited()


@pytest.mark.asyncio
async def test_subscription_deactivate_command_requires_subscription_id():
    message = make_message(bot_main.ADMIN_TELEGRAM_ID)
    command = SimpleNamespace(args=None)

    await bot_main.subscription_deactivate_command(
        message,
        command,
    )

    assert "Укажи ID подписки" in message.answer.await_args.args[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("subscription_id", ["abc", "1.5", "0", "-1"])
async def test_subscription_deactivate_command_rejects_invalid_id(
    subscription_id,
):
    message = make_message(bot_main.ADMIN_TELEGRAM_ID)
    command = SimpleNamespace(args=subscription_id)

    await bot_main.subscription_deactivate_command(
        message,
        command,
    )

    assert message.answer.await_count == 1


@pytest.mark.asyncio
async def test_subscription_deactivate_command_reports_service_error(
    monkeypatch,
):
    message = make_message(bot_main.ADMIN_TELEGRAM_ID)
    command = SimpleNamespace(args="12")

    session, session_context = make_session_context()

    monkeypatch.setattr(
        bot_main,
        "async_session_factory",
        MagicMock(return_value=session_context),
    )

    service = AsyncMock(
        side_effect=ValueError("Действующая подписка с ID 12 не найдена.")
    )
    monkeypatch.setattr(
        bot_main,
        "subscription_deactivate",
        service,
    )

    await bot_main.subscription_deactivate_command(
        message,
        command,
    )

    service.assert_awaited_once_with(
        session,
        subscription_id=12,
    )

    message.answer.assert_awaited_once_with(
        "Действующая подписка с ID 12 не найдена."
    )


@pytest.mark.asyncio
async def test_subscription_deactivate_command_success(
    monkeypatch,
):
    message = make_message(bot_main.ADMIN_TELEGRAM_ID)
    command = SimpleNamespace(args="12")

    task = SimpleNamespace(id=25)
    session, session_context = make_session_context()

    monkeypatch.setattr(
        bot_main,
        "async_session_factory",
        MagicMock(return_value=session_context),
    )

    service = AsyncMock(return_value=task)
    monkeypatch.setattr(
        bot_main,
        "subscription_deactivate",
        service,
    )

    await bot_main.subscription_deactivate_command(
        message,
        command,
    )

    service.assert_awaited_once_with(
        session,
        subscription_id=12,
    )

    message.answer.assert_awaited_once_with(
        "✅ Создана задача #25 "
        "на деактивацию подписки #12.\n\n"
        "Подписка пока остаётся активной.\n"
        "После отключения клиента в H UI "
        "выполни /complete 25."
    )