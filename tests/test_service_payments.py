import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment
from app.models.plan import Plan
from app.models.user import User
from app.services.payments import (
    create_payment,
    get_payment_by_id,
    get_user_payments,
    update_payment_status)


async def create_test_user(
    session: AsyncSession,
    telegram_id: int,
) -> User:
    """Создаёт пользователя для теста."""
    user = User(
        telegram_id=telegram_id,
        username=f"user_{telegram_id}",
        first_name="Test",
    )
    session.add(user)
    await session.flush()
    return user


async def create_test_plan(
    session: AsyncSession,
    *,
    name: str = "Тестовый тариф",
    price_rub: int = 199,
    is_active: bool = True,
) -> Plan:
    """Создаёт тариф для теста."""
    plan = Plan(
        name=name,
        price_rub=price_rub,
        duration_days=30,
        max_devices=3,
        traffic_limit_gb=None,
        is_active=is_active,
    )
    session.add(plan)
    await session.flush()
    return plan


@pytest.mark.asyncio
async def test_create_payment_for_active_plan(session: AsyncSession) -> None:
    """Заказ создаётся для активного тарифа с правильной суммой."""
    user = await create_test_user(session, telegram_id=10001)
    plan = await create_test_plan(
        session,
        price_rub=299,
        is_active=True,
    )

    payment = await create_payment(
        session,
        user_id=user.id,
        plan_id=plan.id,
    )

    assert payment.id is not None
    assert payment.user_id == user.id
    assert payment.plan_id == plan.id
    assert payment.amount_rub == 299
    assert payment.currency == "RUB"
    assert payment.status == "pending"
    assert payment.provider == "fake"


@pytest.mark.asyncio
async def test_create_payment_for_nonexistent_plan(
    session: AsyncSession,
) -> None:
    """При отсутствии тарифа выбрасывается ValueError."""
    user = await create_test_user(session, telegram_id=10002)

    with pytest.raises(ValueError, match="Активный тариф"):
        await create_payment(
            session,
            user_id=user.id,
            plan_id=99999,
        )

    result = await session.execute(
        select(func.count()).select_from(Payment)
    )
    assert result.scalar_one() == 0


@pytest.mark.asyncio
async def test_create_payment_for_inactive_plan(
    session: AsyncSession,
) -> None:
    """Заказ нельзя создать для неактивного тарифа."""
    user = await create_test_user(session, telegram_id=10003)
    plan = await create_test_plan(
        session,
        is_active=False,
    )

    with pytest.raises(ValueError, match="Активный тариф"):
        await create_payment(
            session,
            user_id=user.id,
            plan_id=plan.id,
        )

    result = await session.execute(
        select(func.count()).select_from(Payment)
    )
    assert result.scalar_one() == 0


@pytest.mark.asyncio
async def test_get_payment_by_id_returns_existing_payment(
    session: AsyncSession,
) -> None:
    """По существующему ID возвращается нужный заказ."""
    user = await create_test_user(session, telegram_id=10004)
    plan = await create_test_plan(session)

    created_payment = await create_payment(
        session,
        user_id=user.id,
        plan_id=plan.id,
    )

    payment = await get_payment_by_id(
        session,
        created_payment.id,
    )

    assert payment is not None
    assert payment.id == created_payment.id
    assert payment.user_id == user.id
    assert payment.plan_id == plan.id


@pytest.mark.asyncio
async def test_get_payment_by_id_returns_none_for_missing_payment(
    session: AsyncSession,
) -> None:
    """Для несуществующего ID возвращается None."""
    payment = await get_payment_by_id(
        session,
        payment_id=99999,
    )

    assert payment is None


@pytest.mark.asyncio
async def test_get_user_payments_returns_only_user_payments_newest_first(
    session: AsyncSession,
) -> None:
    """История содержит только заказы пользователя в обратном порядке."""
    first_user = await create_test_user(
        session,
        telegram_id=10005,
    )
    second_user = await create_test_user(
        session,
        telegram_id=10006,
    )

    first_plan = await create_test_plan(
        session,
        name="Тариф 1",
        price_rub=199,
    )
    second_plan = await create_test_plan(
        session,
        name="Тариф 2",
        price_rub=299,
    )
    other_plan = await create_test_plan(
        session,
        name="Тариф другого пользователя",
        price_rub=399,
    )

    first_payment = await create_payment(
        session,
        user_id=first_user.id,
        plan_id=first_plan.id,
    )
    second_payment = await create_payment(
        session,
        user_id=first_user.id,
        plan_id=second_plan.id,
    )
    other_payment = await create_payment(
        session,
        user_id=second_user.id,
        plan_id=other_plan.id,
    )

    payments = await get_user_payments(
        session,
        user_id=first_user.id,
    )

    assert len(payments) == 2
    assert [payment.id for payment in payments] == [
        second_payment.id,
        first_payment.id,
    ]
    assert all(
        payment.user_id == first_user.id
        for payment in payments
    )
    assert other_payment.id not in [
        payment.id for payment in payments
    ]


@pytest.mark.parametrize(
    "new_status",
    ["succeeded", "cancelled", "failed"],
)
async def test_update_payment_status_from_pending(
    session,
    new_status,
):
    user = await create_test_user(session, telegram_id=10007)
    plan = await create_test_plan(session)

    payment = await create_payment(
        session,
        user_id=user.id,
        plan_id=plan.id,
    )

    updated_payment = await update_payment_status(
        session,
        payment.id,
        new_status,
    )

    assert updated_payment is not None
    assert updated_payment.id == payment.id
    assert updated_payment.status == new_status


async def test_update_payment_status_returns_none_for_missing_payment(
    session,
):
    result = await update_payment_status(
        session,
        payment_id=999999,
        new_status="succeeded",
    )

    assert result is None


async def test_update_payment_status_rejects_unknown_status(
    session,
):
    with pytest.raises(ValueError, match="Недопустимый статус"):
        await update_payment_status(
            session,
            payment_id=999999,
            new_status="unknown",
        )


async def test_update_payment_status_is_idempotent(
    session,
):
    user = await create_test_user(session, telegram_id=10008)
    plan = await create_test_plan(session)

    payment = await create_payment(
        session,
        user_id=user.id,
        plan_id=plan.id,
    )

    first_result = await update_payment_status(
        session,
        payment.id,
        "succeeded",
    )
    second_result = await update_payment_status(
        session,
        payment.id,
        "succeeded",
    )

    assert first_result.status == "succeeded"
    assert second_result.status == "succeeded"
    assert second_result.id == payment.id


async def test_update_payment_status_rejects_terminal_transition(
    session,
):
    user = await create_test_user(session, telegram_id=10009)
    plan = await create_test_plan(session)

    payment = await create_payment(
        session,
        user_id=user.id,
        plan_id=plan.id,
    )

    await update_payment_status(
        session,
        payment.id,
        "cancelled",
    )

    with pytest.raises(ValueError, match="Нельзя изменить статус"):
        await update_payment_status(
            session,
            payment.id,
            "succeeded",
        )

    await session.refresh(payment)
    assert payment.status == "cancelled"