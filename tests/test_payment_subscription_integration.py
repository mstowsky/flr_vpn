from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.payment import Payment
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User
from app.services.payments import (
    create_payment,
    process_successful_payment,
    update_payment_status,
)
from app.services.subscriptions import get_user_subscription


def as_utc(value: datetime) -> datetime:
    """Приводит дату к UTC, учитывая формат SQLite."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@pytest.fixture
async def user(session):
    """Создаёт пользователя для интеграционных тестов."""
    user = User(
        telegram_id=987654321,
        username="integration_test_user",
        first_name="Integration Test",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest.fixture
async def plan(session):
    """Создаёт активный тестовый тариф на 30 дней."""
    plan = Plan(
        name="Интеграционный тестовый тариф",
        price_rub=299,
        duration_days=30,
        max_devices=2,
        traffic_limit_gb=None,
        is_active=True,
    )
    session.add(plan)
    await session.commit()
    await session.refresh(plan)
    return plan


@pytest.mark.asyncio
async def test_successful_payment_creates_subscription(
    session,
    user,
    plan,
):
    """Успешная оплата создаёт действующую подписку."""
    payment = await create_payment(
        session,
        user_id=user.id,
        plan_id=plan.id,
    )

    processed_payment = await process_successful_payment(
        session,
        payment.id,
    )

    assert processed_payment is not None
    assert processed_payment.status == "succeeded"

    subscription = await get_user_subscription(
        session,
        user.id,
    )

    assert subscription is not None
    assert subscription.user_id == user.id
    assert subscription.plan_id == plan.id
    assert subscription.status == "active"


@pytest.mark.asyncio
async def test_repeated_processing_does_not_extend_subscription(
    session,
    user,
    plan,
):
    """Повторная обработка одного платежа не продлевает подписку."""
    payment = await create_payment(
        session,
        user_id=user.id,
        plan_id=plan.id,
    )

    await process_successful_payment(session, payment.id)

    subscription_before = await get_user_subscription(
        session,
        user.id,
    )
    assert subscription_before is not None
    expiry_before = as_utc(subscription_before.expires_at)

    await process_successful_payment(session, payment.id)

    subscription_after = await get_user_subscription(
        session,
        user.id,
    )

    assert subscription_after is not None
    assert as_utc(subscription_after.expires_at) == expiry_before

    result = await session.execute(
        select(Subscription).where(
            Subscription.user_id == user.id
        )
    )
    assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_second_successful_payment_extends_subscription(
    session,
    user,
    plan,
):
    """Вторая успешная оплата продлевает существующую подписку."""
    first_payment = await create_payment(
        session,
        user_id=user.id,
        plan_id=plan.id,
    )
    await process_successful_payment(session, first_payment.id)

    subscription_before = await get_user_subscription(
        session,
        user.id,
    )
    assert subscription_before is not None
    expiry_before = as_utc(subscription_before.expires_at)

    second_payment = await create_payment(
        session,
        user_id=user.id,
        plan_id=plan.id,
    )
    await process_successful_payment(session, second_payment.id)

    subscription_after = await get_user_subscription(
        session,
        user.id,
    )

    assert subscription_after is not None
    assert as_utc(subscription_after.expires_at) > expiry_before

    result = await session.execute(
        select(Subscription).where(
            Subscription.user_id == user.id
        )
    )
    assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_processing_missing_payment_returns_none(session):
    """Для несуществующего платежа возвращается None."""
    result = await process_successful_payment(
        session,
        payment_id=999999,
    )

    assert result is None


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["cancelled", "failed"])
async def test_unsuccessful_payment_does_not_create_subscription(
    session,
    user,
    plan,
    status,
):
    """Отменённый или неуспешный платёж не активирует подписку."""
    payment = await create_payment(
        session,
        user_id=user.id,
        plan_id=plan.id,
    )

    await update_payment_status(
        session,
        payment.id,
        status,
    )

    with pytest.raises(ValueError):
        await process_successful_payment(
            session,
            payment.id,
        )

    subscription = await get_user_subscription(
        session,
        user.id,
    )
    assert subscription is None


@pytest.mark.asyncio
async def test_subscription_error_rolls_back_payment_status(
    session,
    user,
    plan,
    monkeypatch,
):
    """Ошибка активации подписки не подтверждает платёж."""
    from app.services import subscriptions

    # Сохраняем ID до возможного rollback транзакции.
    user_id = user.id

    payment = await create_payment(
        session,
        user_id=user_id,
        plan_id=plan.id,
    )
    payment_id = payment.id

    async def fail_to_extend_subscription(*args, **kwargs):
        raise RuntimeError("Ошибка тестовой активации")

    monkeypatch.setattr(
        subscriptions,
        "extend_subscription",
        fail_to_extend_subscription,
    )

    with pytest.raises(
        RuntimeError,
        match="Ошибка тестовой активации",
    ):
        await process_successful_payment(
            session,
            payment_id,
        )

    # Платёж должен остаться ожидающим.
    result = await session.execute(
        select(Payment).where(Payment.id == payment_id)
    )
    stored_payment = result.scalar_one()

    assert stored_payment.status == "pending"

    # После rollback проверяем отсутствие подписки
    # по сохранённому ID, не обращаясь к объекту user.
    result = await session.execute(
        select(Subscription).where(
            Subscription.user_id == user_id
        )
    )
    assert result.scalars().all() == []