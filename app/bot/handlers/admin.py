from datetime import timezone

from aiogram import Router
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.types import Message

from app.config import ADMIN_TELEGRAM_ID, DISPLAY_TIMEZONE
from app.database import async_session_factory
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User
from app.services.provisioning import (
    complete_provisioning_task,
    fail_provisioning_task,
    get_pending_provisioning_tasks,
    retry_provisioning_task,
)

router = Router()


def _is_admin(message: Message) -> bool:
    return (
        message.from_user is not None
        and message.from_user.id == ADMIN_TELEGRAM_ID
    )


async def _deny_access(message: Message) -> None:
    await message.answer("У вас нет доступа к этой команде.")


@router.message(Command("admin"))
async def admin_command(message: Message) -> None:
    if message.from_user is None:
        return

    if not _is_admin(message):
        await _deny_access(message)
        return

    await message.answer(
        "Панель администратора\n\n"
        "Доступ подтверждён. Интерфейс обработки задач "
        "будет добавлен следующим шагом."
    )


@router.message(Command("tasks"))
async def tasks_command(message: Message) -> None:
    if message.from_user is None:
        return

    if not _is_admin(message):
        await _deny_access(message)
        return

    async with async_session_factory() as session:
        tasks = await get_pending_provisioning_tasks(session)

        if not tasks:
            await message.answer(
                "Очередь задач пуста. Ожидающих задач нет."
            )
            return

        lines = ["📋 Ожидающие задачи VPN-доступа:\n"]

        for task in tasks:
            user = await session.get(User, task.user_id)

            if user is None:
                user_info = f"ID пользователя в БД: {task.user_id}"
            else:
                username = (
                    f"@{user.username}"
                    if user.username
                    else "не указан"
                )
                user_info = (
                    f"Telegram ID: {user.telegram_id}\n"
                    f"Имя: {user.first_name or 'не указано'}\n"
                    f"Username: {username}"
                )

            subscription_name = "не указана"

            if task.subscription_id is not None:
                subscription = await session.get(
                    Subscription,
                    task.subscription_id,
                )

                if subscription is not None:
                    plan = await session.get(
                        Plan,
                        subscription.plan_id,
                    )

                    if plan is not None:
                        subscription_name = plan.name

            task_types = {
                "create": "Создание доступа",
                "extend": "Продление доступа",
                "disable": "Отключение доступа",
            }

            created_at = task.created_at.replace(
                tzinfo=timezone.utc
            ).astimezone(DISPLAY_TIMEZONE)

            lines.append(
                f"Задача id: {task.id}\n"
                f"Тип: {task_types.get(task.task_type, task.task_type)}\n"
                f"Статус: {task.status}\n"
                f"{user_info}\n"
                f"Название подписки: {subscription_name}\n"
                f"Подписка ID: {task.subscription_id or 'не указана'}\n"
                f"Создана: {created_at:%d.%m.%Y %H:%M}\n"
            )

    response = "\n".join(lines)

    # Не превышаем ограничение длины сообщения Telegram.
    max_length = 3500

    for start in range(0, len(response), max_length):
        await message.answer(response[start:start + max_length])


@router.message(Command("complete"))
async def complete_command(
    message: Message,
    command: CommandObject,
) -> None:
    if message.from_user is None:
        return

    if not _is_admin(message):
        await _deny_access(message)
        return

    if not command.args:
        await message.answer(
            "Укажи ID задачи.\n"
            "Пример: /complete 12"
        )
        return

    try:
        task_id = int(command.args.strip())
    except ValueError:
        await message.answer(
            "ID задачи должен быть целым числом.\n"
            "Пример: /complete 12"
        )
        return

    if task_id <= 0:
        await message.answer(
            "ID задачи должен быть положительным числом."
        )
        return

    async with async_session_factory() as session:
        try:
            task = await complete_provisioning_task(
                session,
                task_id=task_id,
                result_message=(
                    "Выполнено администратором "
                    f"Telegram ID {message.from_user.id}"
                ),
            )
        except ValueError as exc:
            await message.answer(str(exc))
            return

    await message.answer(
        f"Задача #{task.id} отмечена выполненной."
    )


@router.message(Command("fail"))
async def fail_command(
    message: Message,
    command: CommandObject,
) -> None:
    if message.from_user is None:
        return

    if not _is_admin(message):
        await _deny_access(message)
        return

    if not command.args:
        await message.answer(
            "Укажи ID задачи и причину ошибки.\n"
            "Пример: /fail 12 Не удалось найти клиента в H UI"
        )
        return

    parts = command.args.strip().split(maxsplit=1)

    try:
        task_id = int(parts[0])
    except ValueError:
        await message.answer(
            "ID задачи должен быть целым числом.\n"
            "Пример: /fail 12 Не удалось найти клиента"
        )
        return

    if task_id <= 0:
        await message.answer(
            "ID задачи должен быть положительным числом."
        )
        return

    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "Укажи причину ошибки.\n"
            "Пример: /fail 12 Не удалось найти клиента в H UI"
        )
        return

    reason = parts[1].strip()

    async with async_session_factory() as session:
        try:
            task = await fail_provisioning_task(
                session,
                task_id=task_id,
                result_message=(
                    f"Ошибка: {reason}. "
                    "Администратор Telegram ID "
                    f"{message.from_user.id}"
                ),
            )
        except ValueError as exc:
            await message.answer(str(exc))
            return

    await message.answer(
        f"Задача #{task.id} отмечена как неудачная.\n"
        f"Причина: {reason}\n"
        f"Для повторной попытки используй /retry {task.id}"
    )


@router.message(Command("retry"))
async def retry_command(
    message: Message,
    command: CommandObject,
) -> None:
    if message.from_user is None:
        return

    if not _is_admin(message):
        await _deny_access(message)
        return

    if not command.args:
        await message.answer(
            "Укажи ID неудачной задачи.\n"
            "Пример: /retry 12"
        )
        return

    try:
        task_id = int(command.args.strip())
    except ValueError:
        await message.answer(
            "ID задачи должен быть целым числом.\n"
            "Пример: /retry 12"
        )
        return

    if task_id <= 0:
        await message.answer(
            "ID задачи должен быть положительным числом."
        )
        return

    async with async_session_factory() as session:
        try:
            task = await retry_provisioning_task(
                session,
                task_id=task_id,
            )
        except ValueError as exc:
            await message.answer(str(exc))
            return

    await message.answer(
        f"Задача #{task.id} возвращена в очередь.\n"
        "Проверь очередь командой /tasks."
    )