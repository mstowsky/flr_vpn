from datetime import datetime, timedelta, timezone

import pytest

from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User
from app.services.subscriptions import (
    create_subscription,
    extend_subscription,
    get_user_subscription,
)


def as_utc_naive(value: datetime) -> datetime:
    """Представляет UTC-дату в формате, возвращаемом SQLite."""
    return value.astimezone(timezone.utc).replace(tzinfo=None)


@pytest.fixture
async def user(db_session):
    """Создаёт пользователя для тестов подписок."""
    user = User(
        telegram_id=123456789,
        username="test_user",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def plan(db_session):
    """Создаёт активный тариф на 30 дней."""
    plan = Plan(
        name="Тестовый тариф",
        price=199,
        duration_days=30,
        is_active=True,
    )
    db_session.add(plan)
    await db_session.commit()
    await db_session.refresh(plan)
    return plan


@pytest.fixture
async def inactive_plan(db_session):
    """Создаёт неактивный тариф."""
    plan = Plan(
        name="Неактивный тариф",
        price=199,
        duration_days=30,
        is_active=False,
    )
    db_session.add(plan)
    await db_session.commit()
    await db_session.refresh(plan)
    return plan


@pytest.mark.asyncio
async def test_create_subscription_for_active_plan(
    db_session,
    user,
    plan,
):
    """Создание подписки на активный тариф."""
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)

    subscription = await create_subscription(
        db_session,
        user_id=user.id,
        plan_id=plan.id,
        now=now,
    )

    assert subscription.id is not None
    assert subscription.user_id == user.id
    assert subscription.plan_id == plan.id
    assert subscription.starts_at == as_utc_naive(now)
    assert subscription.expires_at == as_utc_naive(
        now + timedelta(days=30)
    )
    assert subscription.status == "active"


@pytest.mark.asyncio
async def test_create_subscription_for_inactive_plan(
    db_session,
    user,
    inactive_plan,
):
    """Создание подписки на неактивный тариф вызывает ошибку."""
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="не найден"):
        await create_subscription(
            db_session,
            user_id=user.id,
            plan_id=inactive_plan.id,
            now=now,
        )


@pytest.mark.asyncio
async def test_create_subscription_for_missing_plan(
    db_session,
    user,
):
    """Создание подписки на несуществующий тариф вызывает ошибку."""
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="не найден"):
        await create_subscription(
            db_session,
            user_id=user.id,
            plan_id=999999,
            now=now,
        )


@pytest.mark.asyncio
async def test_get_user_subscription_returns_active_subscription(
    db_session,
    user,
    plan,
):
    """Возвращается действующая подписка пользователя."""
    now = datetime.now(timezone.utc)

    subscription = await create_subscription(
        db_session,
        user_id=user.id,
        plan_id=plan.id,
        now=now,
    )

    result = await get_user_subscription(db_session, user.id)

    assert result is not None
    assert result.id == subscription.id


@pytest.mark.asyncio
async def test_get_user_subscription_returns_none_if_missing(
    db_session,
    user,
):
    """Если у пользователя нет подписки, возвращается None."""
    result = await get_user_subscription(db_session, user.id)

    assert result is None


@pytest.mark.asyncio
async def test_get_user_subscription_ignores_expired_subscription(
    db_session,
    user,
    plan,
):
    """Истёкшая по дате подписка не считается действующей."""
    now = datetime.now(timezone.utc)
    expired_at = now - timedelta(days=1)

    subscription = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        starts_at=as_utc_naive(now - timedelta(days=31)),
        expires_at=as_utc_naive(expired_at),
        status="active",
    )
    db_session.add(subscription)
    await db_session.commit()

    result = await get_user_subscription(db_session, user.id)

    assert result is None


@pytest.mark.asyncio
async def test_get_user_subscription_ignores_cancelled_subscription(
    db_session,
    user,
    plan,
):
    """Отменённая подписка не считается действующей."""
    now = datetime.now(timezone.utc)

    subscription = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        starts_at=as_utc_naive(now - timedelta(days=1)),
        expires_at=as_utc_naive(now + timedelta(days=29)),
        status="cancelled",
    )
    db_session.add(subscription)
    await db_session.commit()

    result = await get_user_subscription(db_session, user.id)

    assert result is None


@pytest.mark.asyncio
async def test_extend_subscription_from_current_expiry(
    db_session,
    user,
    plan,
):
    """Действующая подписка продлевается от текущей даты окончания."""
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)

    original = await create_subscription(
        db_session,
        user_id=user.id,
        plan_id=plan.id,
        now=now,
    )
    original_expiry = original.expires_at.replace(tzinfo=timezone.utc)

    extended = await extend_subscription(
        db_session,
        user_id=user.id,
        plan_id=plan.id,
        now=now + timedelta(days=5),
    )

    assert extended.id == original.id
    assert extended.expires_at == as_utc_naive(
        original_expiry + timedelta(days=30)
    )
    assert extended.status == "active"


@pytest.mark.asyncio
async def test_extend_expired_subscription_starts_new_period(
    db_session,
    user,
    plan,
):
    """Для истёкшей подписки создаётся новый период, старый сохраняется."""
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)

    original = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        starts_at=as_utc_naive(now - timedelta(days=40)),
        expires_at=as_utc_naive(now - timedelta(days=10)),
        status="active",
    )
    db_session.add(original)
    await db_session.commit()
    await db_session.refresh(original)

    extended = await extend_subscription(
        db_session,
        user_id=user.id,
        plan_id=plan.id,
        now=now,
    )

    assert extended.id != original.id
    assert extended.user_id == user.id
    assert extended.plan_id == plan.id
    assert extended.starts_at == as_utc_naive(now)
    assert extended.expires_at == as_utc_naive(
        now + timedelta(days=30)
    )
    assert extended.status == "active"

    await db_session.refresh(original)
    assert original.expires_at == as_utc_naive(
        now - timedelta(days=10)
    )


@pytest.mark.asyncio
async def test_extend_subscription_creates_subscription_if_missing(
    db_session,
    user,
    plan,
):
    """Продление без существующей подписки создаёт новую."""
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)

    subscription = await extend_subscription(
        db_session,
        user_id=user.id,
        plan_id=plan.id,
        now=now,
    )

    assert subscription.id is not None
    assert subscription.user_id == user.id
    assert subscription.plan_id == plan.id
    assert subscription.starts_at == as_utc_naive(now)
    assert subscription.expires_at == as_utc_naive(
        now + timedelta(days=30)
    )
    assert subscription.status == "active"


@pytest.mark.asyncio
async def test_extend_subscription_for_inactive_plan(
    db_session,
    user,
    inactive_plan,
):
    """Продление на неактивный тариф вызывает ошибку."""
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="не найден"):
        await extend_subscription