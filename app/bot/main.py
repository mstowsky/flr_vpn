import logging

from datetime import timezone

from aiogram import Bot, Dispatcher
from aiogram.filters import Command, CommandStart
from aiogram.filters.command import CommandObject
from aiogram.types import Message

from app.config import ADMIN_TELEGRAM_ID, DISPLAY_TIMEZONE
from app.services.provisioning import (
    complete_provisioning_task,
    fail_provisioning_task,
    get_pending_provisioning_tasks,
    retry_provisioning_task,
)
from app.database import async_session_factory
from app.models.user import User
from app.services.subscriptions import activate_trial_period
from app.services.users import get_or_create_user

logger = logging.getLogger(__name__)

dp = Dispatcher()


@dp.message(Command("admin"))
async def admin_command(message: Message) -> None:
    if message.from_user is None:
        return

    if message.from_user.id != ADMIN_TELEGRAM_ID:
        await message.answer("У вас нет доступа к этой команде.")
        return

    await message.answer(
        "Панель администратора\n\n"
        "Доступ подтверждён. Интерфейс обработки задач "
        "будет добавлен следующим шагом."
    )


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


@dp.message(Command("trial"))
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


@dp.message(Command("tasks"))
async def tasks_command(message: Message) -> None:
    if message.from_user is None:
        return

    if message.from_user.id != ADMIN_TELEGRAM_ID:
        await message.answer("У вас нет доступа к этой команде.")
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
                user_info = (
                    f"Telegram ID: {user.telegram_id}\n"
                    f"Имя: {user.first_name or 'не указано'}\n"
                    f"Username: @{user.username}"
                    if user.username
                    else (
                        f"Telegram ID: {user.telegram_id}\n"
                        f"Имя: {user.first_name or 'не указано'}\n"
                        "Username: не указан"
                    )
                )

            task_types = {
                "create": "Создание доступа",
                "extend": "Продление доступа",
                "disable": "Отключение доступа",
            }

            lines.append(
                f"Задача id: {task.id}\n"
                f"Тип: {task_types.get(task.task_type, task.task_type)}\n"
                f"Статус: {task.status}\n"
                f"{user_info}\n"
                f"Подписка ID: {task.subscription_id or 'не указана'}\n"
                f"Создана: {task.created_at.replace(tzinfo=timezone.utc).astimezone(DISPLAY_TIMEZONE):%d.%m.%Y %H:%M}\n"
            )

    response = "\n".join(lines)

    # Telegram ограничивает длину одного сообщения.
    # Разбиваем длинную очередь на части.
    max_length = 3500
    for start in range(0, len(response), max_length):
        await message.answer(response[start:start + max_length])


@dp.message(Command("complete"))
async def complete_command(
        message: Message,
        command: CommandObject,
) -> None:
    if message.from_user is None:
        return

    if message.from_user.id != ADMIN_TELEGRAM_ID:
        await message.answer("У вас нет доступа к этой команде.")
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
        await message.answer("ID задачи должен быть положительным числом.")
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


@dp.message(Command("fail"))
async def fail_command(
    message: Message,
    command: CommandObject,
) -> None:
    if message.from_user is None:
        return

    if message.from_user.id != ADMIN_TELEGRAM_ID:
        await message.answer("У вас нет доступа к этой команде.")
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
                    f"Администратор Telegram ID "
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


@dp.message(Command("retry"))
async def retry_command(
    message: Message,
    command: CommandObject,
) -> None:
    if message.from_user is None:
        return

    if message.from_user.id != ADMIN_TELEGRAM_ID:
        await message.answer("У вас нет доступа к этой команде.")
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