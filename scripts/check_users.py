
import asyncio

from sqlalchemy import select

from app.database import async_session_factory, close_db
from app.models.user import User


async def main() -> None:
    test_telegram_id = -999999999

    try:
        async with async_session_factory() as session:
            user = await session.scalar(
                select(User).where(
                    User.telegram_id == test_telegram_id
                )
            )

            if user is None:
                user = User(
                    telegram_id=test_telegram_id,
                    username="test_user",
                    first_name="Test",
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
                print("Пользователь создан.")

            print(f"id: {user.id}")
            print(f"telegram_id: {user.telegram_id}")
            print(f"username: {user.username}")
            print(f"first_name: {user.first_name}")
            print(f"created_at: {user.created_at}")

    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
