from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.bot import main as bot_main


def make_message(telegram_id: int):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=telegram_id),
        answer=AsyncMock(),
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