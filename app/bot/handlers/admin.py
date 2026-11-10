import logging
from datetime import UTC

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.config import ADMIN_TELEGRAM_ID, DISPLAY_TIMEZONE, ENABLE_TEST_COMMANDS
from app.database import async_session_factory
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User
from app.services.payments import process_successful_payment
from app.services.provisioning import (
    complete_provisioning_task,
    fail_provisioning_task,
    get_pending_provisioning_tasks,
    retry_provisioning_task,
)
from app.services.subscriptions import subscription_deactivate

router = Router()
logger = logging.getLogger(__name__)


def get_task_keyboard(task_id: int) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру управления задачей."""

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить",
                    callback_data=f"task:complete:{task_id}",
                ),
                InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data=f"task:fail:{task_id}",
                ),
            ]
        ]
    )


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
                tzinfo=UTC
            ).astimezone(DISPLAY_TIMEZONE)

            task_text = (
                f"Задача id: {task.id}\n"
                f"Тип: {task_types.get(task.task_type, task.task_type)}\n"
                f"Статус: {task.status}\n"
                f"{user_info}\n"
                f"Название подписки: {subscription_name}\n"
                f"Подписка ID: {task.subscription_id or 'не указана'}\n"
                f"Создана: {created_at:%d.%m.%Y %H:%M}"
            )

            await message.answer(
                task_text,
                reply_markup=get_task_keyboard(task.id),
            )


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

    notification_data = None

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

        # Уведомляем клиента при создании, продлении и деактивации подписки.
        if (
                task.task_type in {"create", "extend", "disable"}
                and task.subscription_id is not None
        ):
            user = await session.get(User, task.user_id)
            subscription = await session.get(
                Subscription,
                task.subscription_id,
            )

            if user is not None and subscription is not None:
                plan = await session.get(
                    Plan,
                    subscription.plan_id,
                )

                if plan is not None:
                    notification_data = {
                        "telegram_id": user.telegram_id,
                        "plan_name": plan.name,
                    }

    # Отправляем уведомление после успешного
    # сохранения выполненной задачи.
    if notification_data is not None:
        try:
            await message.bot.send_message(
                chat_id=notification_data["telegram_id"],
                text=(
                    (
                        "❌ Ваша подписка "
                        f"«{notification_data['plan_name']}» "
                        "деактивирована."
                    )
                    if task.task_type == "disable"
                    else (
                        "✅ Ваша подписка "
                        f"«{notification_data['plan_name']}» "
                        "активирована."
                    )
                ),
            )
        except TelegramAPIError:
            logger.exception(
                "Не удалось отправить уведомление "
                "пользователю %s после выполнения задачи",
                notification_data["telegram_id"],
            )

    await message.answer(
        f"Задача #{task.id} отмечена выполненной."
    )


@router.callback_query(F.data.startswith("task:complete:"))
async def task_complete_callback(callback: CallbackQuery) -> None:
    """Выполняет задачу через inline-кнопку."""

    if callback.from_user.id != ADMIN_TELEGRAM_ID:
        await callback.answer(
            "У вас нет доступа к этому действию.",
            show_alert=True,
        )
        return

    try:
        task_id = int(callback.data.rsplit(":", 1)[1])
    except (ValueError, AttributeError):
        await callback.answer(
            "Некорректный ID задачи.",
            show_alert=True,
        )
        return

    notification_data = None

    async with async_session_factory() as session:
        try:
            task = await complete_provisioning_task(
                session,
                task_id=task_id,
                result_message=(
                    "Выполнено администратором "
                    f"Telegram ID {callback.from_user.id}"
                ),
            )
        except ValueError as exc:
            await callback.answer(
                str(exc),
                show_alert=True,
            )
            return

        if (
            task.task_type in {"create", "extend", "disable"}
            and task.subscription_id is not None
        ):
            user = await session.get(User, task.user_id)

            subscription = await session.get(
                Subscription,
                task.subscription_id,
            )

            if user is not None and subscription is not None:
                plan = await session.get(
                    Plan,
                    subscription.plan_id,
                )

                if plan is not None:
                    notification_data = {
                        "telegram_id": user.telegram_id,
                        "plan_name": plan.name,
                    }

    # Уведомляем клиента после сохранения результата.
    if notification_data is not None:
        try:
            await callback.bot.send_message(
                chat_id=notification_data["telegram_id"],
                text=(
                    (
                        "❌ Ваша подписка "
                        f"«{notification_data['plan_name']}» "
                        "деактивирована."
                    )
                    if task.task_type == "disable"
                    else (
                        "✅ Ваша подписка "
                        f"«{notification_data['plan_name']}» "
                        "активирована."
                    )
                ),
            )
        except TelegramAPIError:
            logger.exception(
                "Не удалось отправить уведомление "
                "пользователю %s после выполнения задачи",
                notification_data["telegram_id"],
            )

    await callback.answer("Задача выполнена!")

    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            f"{callback.message.text}\n\n"
            "✅ Задача отмечена выполненной.",
            reply_markup=None,
        )


@router.callback_query(F.data.startswith("task:fail:"))
async def task_fail_callback(callback: CallbackQuery) -> None:
    """Отмечает задачу неудачной через inline-кнопку."""

    if callback.from_user.id != ADMIN_TELEGRAM_ID:
        await callback.answer(
            "У вас нет доступа к этому действию.",
            show_alert=True,
        )
        return

    try:
        task_id = int(callback.data.rsplit(":", 1)[1])
    except (ValueError, AttributeError):
        await callback.answer(
            "Некорректный ID задачи.",
            show_alert=True,
        )
        return

    reason = "Причина не указана"

    async with async_session_factory() as session:
        try:
            task = await fail_provisioning_task(
                session,
                task_id=task_id,
                result_message=(
                    f"Ошибка: {reason}. "
                    "Администратор Telegram ID "
                    f"{callback.from_user.id}"
                ),
            )
        except ValueError as exc:
            await callback.answer(
                str(exc),
                show_alert=True,
            )
            return

    await callback.answer("Задача отменена.")

    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            f"{callback.message.text}\n\n"
            "❌ Задача отмечена как неудачная.\n"
            f"Причина: {reason}\n"
            f"Для повторной попытки используй /retry {task.id}",
            reply_markup=None,
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

    reason = (
        parts[1].strip()
        if len(parts) >= 2 and parts[1].strip()
        else "Причина не указана"
    )

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


@router.message(Command("test_pay"))
async def test_pay_command(
    message: Message,
    command: CommandObject,
) -> None:
    if not ENABLE_TEST_COMMANDS:
        await message.answer(
            "Тестовые команды отключены."
        )
        return

    if message.from_user is None:
        return

    if not _is_admin(message):
        await _deny_access(message)
        return

    if not command.args:
        await message.answer(
            "Укажи ID заказа.\n"
            "Пример: /test_pay 2"
        )
        return

    try:
        payment_id = int(command.args.strip())
    except ValueError:
        await message.answer(
            "ID заказа должен быть целым числом.\n"
            "Пример: /test_pay 2"
        )
        return

    if payment_id <= 0:
        await message.answer(
            "ID заказа должен быть положительным числом."
        )
        return

    async with async_session_factory() as session:
        try:
            payment = await process_successful_payment(
                session,
                payment_id=payment_id,
            )
        except ValueError as exc:
            await message.answer(str(exc))
            return

    if payment is None:
        await message.answer(
            f"Заказ #{payment_id} не найден."
        )
        return

    await message.answer(
        f"✅ Тестовая оплата заказа #{payment.id} подтверждена.\n\n"
        "Подписка активирована.\n"
        "Задача на подключение VPN создана.\n\n"
        "Проверь очередь командой /tasks."
    )


@router.message(Command("test_subs_deactivate"))
async def test_subs_deactivate_command(
    message: Message,
    command: CommandObject,
) -> None:
    if not ENABLE_TEST_COMMANDS:
        await message.answer(
            "Тестовые команды отключены."
        )
        return

    if message.from_user is None:
        return

    if not _is_admin(message):
        await _deny_access(message)
        return

    if not command.args:
        await message.answer(
            "Укажи ID подписки.\n"
            "Пример: /test_subs_deactivate 12"
        )
        return

    try:
        subscription_id = int(command.args.strip())
    except ValueError:
        await message.answer(
            "ID подписки должен быть целым числом.\n"
            "Пример: /test_subs_deactivate 12"
        )
        return

    if subscription_id <= 0:
        await message.answer(
            "ID подписки должен быть положительным числом."
        )
        return

    async with async_session_factory() as session:
        try:
            subscription = await subscription_deactivate(
                session,
                subscription_id=subscription_id,
                force=True,
            )
        except ValueError as exc:
            await message.answer(str(exc))
            return

    await message.answer(
        f"✅ Подписка #{subscription.id} деактивирована.\n"
        "Статус изменён на cancelled.\n"
        "Задача на отключение VPN не создавалась."
    )


@router.message(Command("subscription_deactivate"))
async def subscription_deactivate_command(
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
            "Укажи ID подписки.\n"
            "Пример: /subscription_deactivate 12"
        )
        return

    try:
        subscription_id = int(command.args.strip())
    except ValueError:
        await message.answer(
            "ID подписки должен быть целым числом.\n"
            "Пример: /subscription_deactivate 12"
        )
        return

    if subscription_id <= 0:
        await message.answer(
            "ID подписки должен быть положительным числом."
        )
        return

    async with async_session_factory() as session:
        try:
            task = await subscription_deactivate(
                session,
                subscription_id=subscription_id,
            )
        except ValueError as exc:
            await message.answer(str(exc))
            return

    await message.answer(
        f"✅ Создана задача #{task.id} "
        f"на деактивацию подписки #{subscription_id}.\n\n"
        "Подписка пока остаётся активной.\n"
        "После отключения клиента в H UI "
        f"выполни /complete {task.id}."
    )