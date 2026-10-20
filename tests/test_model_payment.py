from datetime import datetime

import pytest
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment
from app.models.plan import Plan
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


async def create_payment(
    session: AsyncSession,
    user: User,
    plan: Plan,
    **kwargs,
) -> Payment:
    payment = Payment(
        user_id=user.id,
        plan_id=plan.id,
        amount_rub=plan.price_rub,
        **kwargs,
    )
    session.add(payment)
    await session.flush()

    return payment


async def test_create_payment_saves_payment_to_database(
    session: AsyncSession,
) -> None:
    user, plan = await create_user_and_plan(session)

    payment = await create_payment(
        session,
        user,
        plan,
        currency="RUB",
        status="succeeded",
        provider="fake",
        provider_payment_id="test-payment-001",
    )

    result = await session.execute(
        select(Payment).where(Payment.id == payment.id)
    )
    saved_payment = result.scalar_one()

    assert saved_payment.user_id == user.id
    assert saved_payment.plan_id == plan.id
    assert saved_payment.amount_rub == 300
    assert saved_payment.currency == "RUB"
    assert saved_payment.status == "succeeded"
    assert saved_payment.provider == "fake"
    assert saved_payment.provider_payment_id == "test-payment-001"


async def test_payment_uses_default_values(
    session: AsyncSession,
) -> None:
    user, plan = await create_user_and_plan(session)

    payment = await create_payment(session, user, plan)

    assert payment.currency == "RUB"
    assert payment.status == "pending"
    assert payment.provider == "fake"
    assert payment.provider_payment_id is None


async def test_payment_timestamps_are_set(
    session: AsyncSession,
) -> None:
    user, plan = await create_user_and_plan(session)

    payment = await create_payment(session, user, plan)

    assert isinstance(payment.created_at, datetime)
    assert isinstance(payment.updated_at, datetime)


async def test_payment_references_existing_user_and_plan(
    session: AsyncSession,
) -> None:
    user, plan = await create_user_and_plan(session)

    payment = await create_payment(session, user, plan)

    assert payment.user_id == user.id
    assert payment.plan_id == plan.id

    await session.commit()

    result = await session.execute(
        select(Payment).where(Payment.id == payment.id)
    )
    saved_payment = result.scalar_one()

    assert saved_payment.user_id == user.id
    assert saved_payment.plan_id == plan.id


@pytest.mark.parametrize("field", ["user_id", "plan_id"])
async def test_payment_requires_user_and_plan(
    session: AsyncSession,
    field: str,
) -> None:
    user, plan = await create_user_and_plan(session)

    payment_data = {
        "user_id": user.id,
        "plan_id": plan.id,
        "amount_rub": plan.price_rub,
    }
    payment_data[field] = None

    session.add(Payment(**payment_data))

    with pytest.raises(IntegrityError):
        await session.flush()

    await session.rollback()


@pytest.mark.parametrize("field", ["user_id", "plan_id"])
async def test_payment_rejects_nonexistent_foreign_key(
    session: AsyncSession,
    field: str,
) -> None:
    user, plan = await create_user_and_plan(session)

    payment_data = {
        "user_id": user.id,
        "plan_id": plan.id,
        "amount_rub": plan.price_rub,
    }
    payment_data[field] = 999999

    session.add(Payment(**payment_data))

    with pytest.raises(IntegrityError):
        await session.flush()

    await session.rollback()


@pytest.mark.parametrize("amount", [0, -100])
async def test_payment_rejects_non_positive_amount(
    session: AsyncSession,
    amount: int,
) -> None:
    user, plan = await create_user_and_plan(session)

    session.add(
        Payment(
            user_id=user.id,
            plan_id=plan.id,
            amount_rub=amount,
        )
    )

    with pytest.raises(IntegrityError):
        await session.flush()

    await session.rollback()


async def test_payment_rejects_invalid_status(
    session: AsyncSession,
) -> None:
    user, plan = await create_user_and_plan(session)

    session.add(
        Payment(
            user_id=user.id,
            plan_id=plan.id,
            amount_rub=plan.price_rub,
            status="unknown",
        )
    )

    with pytest.raises(IntegrityError):
        await session.flush()

    await session.rollback()


async def test_payment_provider_payment_id_must_be_unique(
    session: AsyncSession,
) -> None:
    user, plan = await create_user_and_plan(session)

    await create_payment(
        session,
        user,
        plan,
        provider_payment_id="duplicate-payment-id",
    )

    session.add(
        Payment(
            user_id=user.id,
            plan_id=plan.id,
            amount_rub=plan.price_rub,
            provider_payment_id="duplicate-payment-id",
        )
    )

    with pytest.raises(IntegrityError):
        await session.flush()

    await session.rollback()


async def test_payment_allows_null_provider_payment_id(
    session: AsyncSession,
) -> None:
    user, plan = await create_user_and_plan(session)

    await create_payment(session, user, plan)
    await create_payment(session, user, plan)

    await session.commit()

    result = await session.execute(
        select(func.count())
        .select_from(Payment)
        .where(Payment.provider_payment_id.is_(None))
    )

    assert result.scalar_one() == 2