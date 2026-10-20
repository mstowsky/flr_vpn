from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories import users as users_repository


async def get_or_create_user(
    session: AsyncSession,
    *,
    telegram_id: int,
    username: str | None,
    first_name: str | None,
) -> tuple[User, bool]:
    user = await users_repository.get_by_telegram_id(
        session,
        telegram_id,
    )

    if user is not None:
        user.username = username
        user.first_name = first_name

        await session.commit()
        await session.refresh(user)

        return user, False

    try:
        user = await users_repository.create(
            session,
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
        )
        await session.commit()
        await session.refresh(user)

        return user, True

    except IntegrityError:
        # Возможно, другая операция уже создала пользователя
        # с таким telegram_id.
        await session.rollback()

        user = await users_repository.get_by_telegram_id(
            session,
            telegram_id,
        )

        if user is None:
            raise

        user.username = username
        user.first_name = first_name

        await session.commit()
        await session.refresh(user)

        return user, False