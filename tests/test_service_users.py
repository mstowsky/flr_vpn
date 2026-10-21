import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.users import get_or_create_user


@pytest.mark.asyncio
async def test_create_new_user(session: AsyncSession) -> None:
    user, is_new = await get_or_create_user(
        session,
        telegram_id=100001,
        username="test_user",
        first_name="Test",
    )

    assert is_new is True
    assert user.id is not None
    assert user.telegram_id == 100001
    assert user.username == "test_user"
    assert user.first_name == "Test"


@pytest.mark.asyncio
async def test_repeated_call_does_not_create_duplicate(
    session: AsyncSession,
) -> None:
    first_user, first_is_new = await get_or_create_user(
        session,
        telegram_id=100002,
        username="test_user",
        first_name="Test",
    )

    second_user, second_is_new = await get_or_create_user(
        session,
        telegram_id=100002,
        username="test_user",
        first_name="Test",
    )

    result = await session.execute(
        select(func.count()).select_from(User)
    )
    user_count = result.scalar_one()

    assert first_is_new is True
    assert second_is_new is False
    assert first_user.id == second_user.id
    assert user_count == 1


@pytest.mark.asyncio
async def test_existing_user_profile_is_updated(
    session: AsyncSession,
) -> None:
    await get_or_create_user(
        session,
        telegram_id=100003,
        username="old_username",
        first_name="Old name",
    )

    user, is_new = await get_or_create_user(
        session,
        telegram_id=100003,
        username="new_username",
        first_name="New name",
    )

    assert is_new is False
    assert user.username == "new_username"
    assert user.first_name == "New name"

    result = await session.execute(
        select(User).where(User.telegram_id == 100003)
    )
    saved_user = result.scalar_one()

    assert saved_user.username == "new_username"
    assert saved_user.first_name == "New name"


@pytest.mark.asyncio
async def test_different_telegram_ids_create_different_users(
    session: AsyncSession,
) -> None:
    first_user, _ = await get_or_create_user(
        session,
        telegram_id=100004,
        username="first_user",
        first_name="First",
    )

    second_user, _ = await get_or_create_user(
        session,
        telegram_id=100005,
        username="second_user",
        first_name="Second",
    )

    assert first_user.id != second_user.id
    assert first_user.telegram_id != second_user.telegram_id

    result = await session.execute(
        select(func.count()).select_from(User)
    )
    assert result.scalar_one() == 2


@pytest.mark.asyncio
async def test_create_user_without_username(
    session: AsyncSession,
) -> None:
    user, is_new = await get_or_create_user(
        session,
        telegram_id=100006,
        username=None,
        first_name="User Without Username",
    )

    assert is_new is True
    assert user.id is not None
    assert user.username is None
    assert user.first_name == "User Without Username"


@pytest.mark.asyncio
async def test_existing_user_username_can_be_cleared(
    session: AsyncSession,
) -> None:
    await get_or_create_user(
        session,
        telegram_id=100007,
        username="old_username",
        first_name="Test User",
    )

    user, is_new = await get_or_create_user(
        session,
        telegram_id=100007,
        username=None,
        first_name="Test User",
    )

    assert is_new is False
    assert user.username is None

    result = await session.execute(
        select(User).where(User.telegram_id == 100007)
    )
    saved_user = result.scalar_one()

    assert saved_user.username is None