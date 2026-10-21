from datetime import datetime, timedelta, timezone

import pytest

from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User
from app.services.subscriptions import (
    create_subscription,
    get_user_subscription,
    get_user_subscription_info,
    expire_subscriptions,
    extend_subscription,
)


def as_utc_naive(value: datetime) -> datetime:
    """Представляет UTC-дату в формате, возвращаемом SQLite."""
    return value.astimezone(timezone.utc).replace(tzinfo=None)


@pytest.fixture
async def user(session):
    """Создаёт пользователя для тестов подписок."""
    user = User(
        telegram_id=123456789,
        username="test_user",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest.fixture
async def plan(session):
    """Создаёт активный тариф на 30 дней."""
    plan = Plan(
        name="Тестовый тариф",
        price_rub=199,
        duration_days=30,
        max_devices=3,
        traffic_limit_gb=None,
        is_active=True,
    )
    session.add(plan)
    await session.commit()
    await session.refresh(plan)
    return plan


@pytest.fixture
async def inactive_plan(session):
    """Создаёт неактивный тариф."""
    plan = Plan(
        name="Неактивный тариф",
        price_rub=199,
        duration_days=30,
        max_devices=3,
        traffic_limit_gb=None,
        is_active=False,
    )
    session.add(plan)
    await session.commit()
    await session.refresh(plan)
    return plan


@pytest.mark.asyncio
async def test_create_subscription_for_active_plan(
    session,
    user,
    plan,
):
    """Создание подписки на активный тариф."""
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)

    subscription = await create_subscription(
        session,
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
    session,
    user,
    inactive_plan,
):
    """Создание подписки на неактивный тариф вызывает ошибку."""
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="не найден"):
        await create_subscription(
            session,
            user_id=user.id,
            plan_id=inactive_plan.id,
            now=now,
        )


@pytest.mark.asyncio
async def test_create_subscription_for_missing_plan(
    session,
    user,
):
    """Создание подписки на несуществующий тариф вызывает ошибку."""
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="не найден"):
        await create_subscription(
            session,
            user_id=user.id,
            plan_id=999999,
            now=now,
        )


@pytest.mark.asyncio
async def test_get_user_subscription_returns_active_subscription(
    session,
    user,
    plan,
):
    """Возвращается действующая подписка пользователя."""
    now = datetime.now(timezone.utc)

    subscription = await create_subscription(
        session,
        user_id=user.id,
        plan_id=plan.id,
        now=now,
    )

    result = await get_user_subscription(session, user.id)

    assert result is not None
    assert result.id == subscription.id


@pytest.mark.asyncio
async def test_get_user_subscription_returns_none_if_missing(
    session,
    user,
):
    """Если у пользователя нет подписки, возвращается None."""
    result = await get_user_subscription(session, user.id)

    assert result is None


@pytest.mark.asyncio
async def test_get_user_subscription_ignores_expired_subscription(
    session,
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
    session.add(subscription)
    await session.commit()

    result = await get_user_subscription(session, user.id)

    assert result is None


@pytest.mark.asyncio
async def test_get_user_subscription_ignores_cancelled_subscription(
    session,
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
    session.add(subscription)
    await session.commit()

    result = await get_user_subscription(session, user.id)

    assert result is None


@pytest.mark.asyncio
async def test_extend_subscription_from_current_expiry(
    session,
    user,
    plan,
):
    """Действующая подписка продлевается от текущей даты окончания."""
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)

    original = await create_subscription(
        session,
        user_id=user.id,
        plan_id=plan.id,
        now=now,
    )
    original_expiry = original.expires_at.replace(tzinfo=timezone.utc)

    extended = await extend_subscription(
        session,
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
    session,
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
    session.add(original)
    await session.commit()
    await session.refresh(original)

    extended = await extend_subscription(
        session,
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

    await session.refresh(original)
    assert original.expires_at == as_utc_naive(
        now - timedelta(days=10)
    )


@pytest.mark.asyncio
async def test_extend_subscription_creates_subscription_if_missing(
    session,
    user,
    plan,
):
    """Продление без существующей подписки создаёт новую."""
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)

    subscription = await extend_subscription(
        session,
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
    session,
    user,
    inactive_plan,
):
    """Продление на неактивный тариф вызывает ошибку."""
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="не найден"):
        await extend_subscription(
            session,
            user_id=user.id,
            plan_id=inactive_plan.id,
            now=now,
        )


@pytest.mark.asyncio
async def test_expire_subscriptions_updates_expired_records(
    session,
    user,
    plan,
):
    """Истёкшая подписка переводится в статус expired."""
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)

    subscription = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        starts_at=as_utc_naive(now - timedelta(days=31)),
        expires_at=as_utc_naive(now),
        status="active",
    )
    session.add(subscription)
    await session.commit()
    await session.refresh(subscription)

    count = await expire_subscriptions(session, now=now)

    await session.refresh(subscription)

    assert count == 1
    assert subscription.status == "expired"
    assert subscription.updated_at == as_utc_naive(now)


@pytest.mark.asyncio
async def test_expire_subscriptions_keeps_active_records(
    session,
    user,
    plan,
):
    """Подписка с будущим сроком действия остаётся активной."""
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)

    subscription = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        starts_at=as_utc_naive(now),
        expires_at=as_utc_naive(now + timedelta(days=30)),
        status="active",
    )
    session.add(subscription)
    await session.commit()

    count = await expire_subscriptions(session, now=now)

    await session.refresh(subscription)

    assert count == 0
    assert subscription.status == "active"


@pytest.mark.asyncio
async def test_expire_subscriptions_ignores_non_active_records(
    session,
    user,
    plan,
):
    """Отменённые подписки не изменяются."""
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)

    subscription = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        starts_at=as_utc_naive(now - timedelta(days=1)),
        expires_at=as_utc_naive(now),
        status="cancelled",
    )
    session.add(subscription)
    await session.commit()

    count = await expire_subscriptions(session, now=now)

    await session.refresh(subscription)

    assert count == 0
    assert subscription.status == "cancelled"


@pytest.mark.asyncio
async def test_get_user_subscription_info_returns_details(
    session,
    user,
    plan,
):
    """Информация о действующей подписке содержит нужные поля."""
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)

    subscription = await create_subscription(
        session,
        user_id=user.id,
        plan_id=plan.id,
        now=now,
    )

    info = await get_user_subscription_info(
        session,
        user.id,
        now=now,
    )

    assert info is not None
    assert info["status"] == "active"
    assert info["expires_at"] == datetime(
        2026, 11, 20, 12, 0, tzinfo=timezone.utc
    )
    assert info["remaining_days"] == 30


@pytest.mark.asyncio
async def test_get_user_subscription_info_rounds_up_remaining_days(
    session,
    user,
    plan,
):
    """Неполные сутки округляются вверх до одного дня."""
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)

    await create_subscription(
        session,
        user_id=user.id,
        plan_id=plan.id,
        now=now,
    )

    check_time = now + timedelta(days=29, hours=1)

    info = await get_user_subscription_info(
        session,
        user.id,
        now=check_time,
    )

    assert info is not None
    assert info["remaining_days"] == 1


@pytest.mark.asyncio
async def test_get_user_subscription_info_returns_none_if_missing(
    session,
    user,
):
    """Без действующей подписки возвращается None."""
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)

    info = await get_user_subscription_info(
        session,
        user.id,
        now=now,
    )

    assert info is None


@pytest.mark.asyncio
async def test_get_user_subscription_info_returns_none_if_expired(
    session,
    user,
    plan,
):
    """Подписка с истёкшим сроком не возвращается."""
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)

    await create_subscription(
        session,
        user_id=user.id,
        plan_id=plan.id,
        now=now - timedelta(days=31),
    )

    info = await get_user_subscription_info(
        session,
        user.id,
        now=now,
    )

    assert info is None