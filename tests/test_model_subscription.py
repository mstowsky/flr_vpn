from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User


async def create_user_and_plan(
    session: AsyncSession,
) -> tuple[User, Plan]:
    user = User(
        telegram_id=123456789,
        username="test_user",
        first_name="Test",
    )
    plan = Plan(
        name="Test plan",
        price_rub=300,
        duration_days=30,
        max_devices=3,
    )

    session.add_all([user, plan])
    await session.flush()

    return user, plan


async def create_subscription(
    session: AsyncSession,
    user: User,
    plan: Plan,
    **kwargs,
) -> Subscription:
    now = datetime.now(timezone.utc)

    subscription_data = {
        "user_id": user.id,
        "plan_id": plan.id,
        "starts_at": now,
        "expires_at": now + timedelta(days=30),
    }
    subscription_data.update(kwargs)

    subscription = Subscription(**subscription_data)
    session.add(subscription)
    await session.flush()

    return subscription


async def test_create_subscription_saves_to_database(
    session: AsyncSession,
) -> None:
    user, plan = await create_user_and_plan(session)

    subscription = await create_subscription(
        session,
        user,
        plan,
    )

    result = await session.execute(
        select(Subscription).where(
            Subscription.id == subscription.id
        )
    )
    saved_subscription = result.scalar_one()

    assert saved_subscription.id is not None
    assert saved_subscription.user_id == user.id
    assert saved_subscription.plan_id == plan.id
    assert saved_subscription.status == "active"
    assert saved_subscription.expires_at > saved_subscription.starts_at


async def test_subscription_uses_default_status(
    session: AsyncSession,
) -> None:
    user, plan = await create_user_and_plan(session)

    subscription = await create_subscription(
        session,
        user,
        plan,
    )

    assert subscription.status == "active"


async def test_subscription_timestamps_are_set(
    session: AsyncSession,
) -> None:
    user, plan = await create_user_and_plan(session)

    subscription = await create_subscription(
        session,
        user,
        plan,
    )

    assert isinstance(subscription.created_at, datetime)
    assert isinstance(subscription.updated_at, datetime)


async def test_subscription_references_existing_user_and_plan(
    session: AsyncSession,
) -> None:
    user, plan = await create_user_and_plan(session)

    subscription = await create_subscription(
        session,
        user,
        plan,
    )

    await session.commit()

    result = await session.execute(
        select(Subscription).where(
            Subscription.id == subscription.id
        )
    )
    saved_subscription = result.scalar_one()

    assert saved_subscription.user_id == user.id
    assert saved_subscription.plan_id == plan.id


@pytest.mark.parametrize(
    "field",
    ["user_id", "plan_id", "starts_at", "expires_at"],
)
async def test_subscription_requires_mandatory_fields(
    session: AsyncSession,
    field: str,
) -> None:
    user, plan = await create_user_and_plan(session)

    now = datetime.now(timezone.utc)
    subscription_data = {
        "user_id": user.id,
        "plan_id": plan.id,
        "starts_at": now,
        "expires_at": now + timedelta(days=30),
    }
    subscription_data[field] = None

    session.add(Subscription(**subscription_data))

    with pytest.raises(IntegrityError):
        await session.flush()

    await session.rollback()


@pytest.mark.parametrize(
    "field",
    ["user_id", "plan_id"],
)
async def test_subscription_rejects_nonexistent_foreign_key(
    session: AsyncSession,
    field: str,
) -> None:
    user, plan = await create_user_and_plan(session)

    now = datetime.now(timezone.utc)
    subscription_data = {
        "user_id": user.id,
        "plan_id": plan.id,
        "starts_at": now,
        "expires_at": now + timedelta(days=30),
    }
    subscription_data[field] = 999999

    session.add(Subscription(**subscription_data))

    with pytest.raises(IntegrityError):
        await session.flush()

    await session.rollback()


@pytest.mark.parametrize(
    "status",
    ["unknown", "pending", "succeeded", ""],
)
async def test_subscription_rejects_invalid_status(
    session: AsyncSession,
    status: str,
) -> None:
    user, plan = await create_user_and_plan(session)

    now = datetime.now(timezone.utc)

    session.add(
        Subscription(
            user_id=user.id,
            plan_id=plan.id,
            starts_at=now,
            expires_at=now + timedelta(days=30),
            status=status,
        )
    )

    with pytest.raises(IntegrityError):
        await session.flush()

    await session.rollback()


@pytest.mark.parametrize(
    "status",
    ["active", "expired", "cancelled"],
)
async def test_subscription_accepts_valid_statuses(
    session: AsyncSession,
    status: str,
) -> None:
    user, plan = await create_user_and_plan(session)

    subscription = await create_subscription(
        session,
        user,
        plan,
        status=status,
    )

    assert subscription.status == status


@pytest.mark.parametrize(
    "start_offset, end_offset",
    [
        (0, 0),
        (1, 0),
        (2, 1),
    ],
)
async def test_subscription_rejects_invalid_date_range(
    session: AsyncSession,
    start_offset: int,
    end_offset: int,
) -> None:
    user, plan = await create_user_and_plan(session)

    now = datetime.now(timezone.utc)

    session.add(
        Subscription(
            user_id=user.id,
            plan_id=plan.id,
            starts_at=now + timedelta(days=start_offset),
            expires_at=now + timedelta(days=end_offset),
        )
    )

    with pytest.raises(IntegrityError):
        await session.flush()

    await session.rollback()


async def test_subscription_updates_updated_at(
    session: AsyncSession,
) -> None:
    user, plan = await create_user_and_plan(session)

    old_timestamp = datetime(
        2020, 1, 1, tzinfo=timezone.utc
    )
    subscription = await create_subscription(
        session,
        user,
        plan,
        updated_at=old_timestamp,
    )

    subscription.status = "cancelled"
    await session.flush()

    assert subscription.updated_at > old_timestamp