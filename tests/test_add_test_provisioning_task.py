import asyncio

from sqlalchemy import select

from app.database import async_session_factory, close_db
from app.models.user import User
from app.services.provisioning import create_provisioning_task


async def main() -> None:
    """Создаёт одну тестовую задачу для ручной проверки в Telegram."""

    telegram_id_input = 386203876

    try:
        telegram_id = int(telegram_id_input)
    except ValueError:
        print("Ошибка: Telegram ID должен быть целым числом.")
        return

    try:
        async with async_session_factory() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()

            if user is None:
                print(
                    f"Пользователь с Telegram ID {telegram_id} "
                    "не найден в базе данных."
                )
                print(
                    "Сначала открой бота и отправь ему /start, "
                    "затем запусти скрипт повторно."
                )
                return

            task = await create_provisioning_task(
                session,
                user_id=user.id,
                task_type="create",
            )

            print("\nТестовая задача успешно создана.")
            print(f"ID задачи: {task.id}")
            print(f"Telegram ID пользователя: {user.telegram_id}")
            print(f"Внутренний ID пользователя: {user.id}")
            print(f"Тип задачи: {task.task_type}")
            print(f"Статус: {task.status}")
            print("\nТеперь можно открыть Telegram и выполнить задачу.")

    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())