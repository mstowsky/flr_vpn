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
    update_payment_status,
    process_successful_payment)


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


@pytest.mark.asyncio
async def test_process_successful_payment_creates_subscription(
    session: AsyncSession,
) -> None:
    """Успешная оплата создаёт подписку и меняет статус платежа."""
    from datetime import datetime, timedelta, timezone

    from app.models.subscription import Subscription

    user = await create_test_user(session, telegram_id=20001)
    plan = await create_test_plan(session, price_rub=299)

    payment = await create_payment(
        session,
        user_id=user.id,
        plan_id=plan.id,
    )

    result = await process_successful_payment(session, payment.id)

    assert result is not None
    assert result.status == "succeeded"

    subscriptions = await session.execute(
        select(Subscription).where(
            Subscription.user_id == user.id
        )
    )
    subscription = subscriptions.scalar_one()

    assert subscription.status == "active"
    assert subscription.plan_id == plan.id
    assert subscription.expires_at > subscription.starts_at
    assert subscription.expires_at.replace(tzinfo=timezone.utc) == (
        subscription.starts_at.replace(tzinfo=timezone.utc)
        + timedelta(days=plan.duration_days)
    )


@pytest.mark.asyncio
async def test_process_successful_payment_is_idempotent(
    session: AsyncSession,
) -> None:
    """Повторная обработка платежа не продлевает подписку повторно."""
    from app.models.subscription import Subscription

    user = await create_test_user(session, telegram_id=20002)
    plan = await create_test_plan(session)

    payment = await create_payment(
        session,
        user_id=user.id,
        plan_id=plan.id,
    )

    await process_successful_payment(session, payment.id)

    subscriptions = await session.execute(
        select(Subscription).where(
            Subscription.user_id == user.id
        )
    )
    subscription = subscriptions.scalar_one()
    original_expiry = subscription.expires_at

    await process_successful_payment(session, payment.id)

    await session.refresh(subscription)

    assert subscription.expires_at == original_expiry

    count_result = await session.execute(
        select(func.count()).select_from(Subscription).where(
            Subscription.user_id == user.id
        )
    )
    assert count_result.scalar_one() == 1


@pytest.mark.asyncio
async def test_process_successful_payment_rejects_cancelled_payment(
    session: AsyncSession,
) -> None:
    """Отменённый платёж не активирует подписку."""
    from app.models.subscription import Subscription

    user = await create_test_user(session, telegram_id=20003)
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

    with pytest.raises(ValueError, match="Нельзя подтвердить платёж"):
        await process_successful_payment(session, payment.id)

    count_result = await session.execute(
        select(func.count()).select_from(Subscription).where(
            Subscription.user_id == user.id
        )
    )
    assert count_result.scalar_one() == 0


@pytest.mark.asyncio
async def test_process_successful_payment_returns_none_for_missing_payment(
    session: AsyncSession,
) -> None:
    """Для несуществующего платежа возвращается None."""
    result = await process_successful_payment(
        session,
        payment_id=999999,
    )

    assert result is None


@pytest.mark.asyncio
async def test_successful_payment_extends_existing_subscription(
    session: AsyncSession,
) -> None:
    """Повторная покупка продлевает существующую подписку."""
    from datetime import timedelta, timezone

    from app.models.subscription import Subscription

    user = await create_test_user(session, telegram_id=20004)
    plan = await create_test_plan(session)

    # Первая оплата создаёт подписку на 30 дней.
    first_payment = await create_payment(
        session,
        user_id=user.id,
        plan_id=plan.id,
    )
    await process_successful_payment(session, first_payment.id)

    result = await session.execute(
        select(Subscription).where(
            Subscription.user_id == user.id
        )
    )
    subscription = result.scalar_one()
    original_expiry = subscription.expires_at.replace(
        tzinfo=timezone.utc
    )
    original_id = subscription.id

    # Вторая оплата того же тарифа добавляет ещё 30 дней.
    second_payment = await create_payment(
        session,
        user_id=user.id,
        plan_id=plan.id,
    )
    await process_successful_payment(session, second_payment.id)

    await session.refresh(subscription)

    assert subscription.id == original_id
    assert subscription.expires_at.replace(
        tzinfo=timezone.utc
    ) == original_expiry + timedelta(days=30)

    count_result = await session.execute(
        select(func.count()).select_from(Subscription).where(
            Subscription.user_id == user.id
        )
    )
    assert count_result.scalar_one() == 1


@pytest.mark.asyncio
async def test_successful_payment_switches_subscription_plan(
    session: AsyncSession,
) -> None:
    """При оплате другого тарифа обновляется план и срок подписки."""
    from datetime import timedelta, timezone

    from app.models.subscription import Subscription

    user = await create_test_user(session, telegram_id=20005)
    first_plan = await create_test_plan(session)

    second_plan = Plan(
        name="Тариф на 3 месяца, 5 устройств",
        price_rub=899,
        duration_days=90,
        max_devices=5,
        traffic_limit_gb=None,
        is_active=True,
    )
    session.add(second_plan)
    await session.commit()
    await session.refresh(second_plan)

    first_payment = await create_payment(
        session,
        user_id=user.id,
        plan_id=first_plan.id,
    )
    await process_successful_payment(session, first_payment.id)

    result = await session.execute(
        select(Subscription).where(
            Subscription.user_id == user.id
        )
    )
    subscription = result.scalar_one()
    original_expiry = subscription.expires_at.replace(
        tzinfo=timezone.utc
    )
    original_id = subscription.id

    second_payment = await create_payment(
        session,
        user_id=user.id,
        plan_id=second_plan.id,
    )
    await process_successful_payment(session, second_payment.id)

    await session.refresh(subscription)

    assert subscription.id == original_id
    assert subscription.plan_id == second_plan.id
    assert subscription.expires_at.replace(
        tzinfo=timezone.utc
    ) == original_expiry + timedelta(days=90)

    count_result = await session.execute(
        select(func.count()).select_from(Subscription).where(
            Subscription.user_id == user.id
        )
    )
    assert count_result.scalar_one() == 1


@pytest.mark.asyncio
async def test_successful_payment_rolls_back_when_subscription_extension_fails(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """При ошибке продления подписки платёж не становится успешным."""
    from app.models.subscription import Subscription
    from app.services.payments import process_successful_payment

    user = await create_test_user(session, telegram_id=20006)
    user_id = user.id
    plan = await create_test_plan(session)

    payment = await create_payment(
        session,
        user_id=user.id,
        plan_id=plan.id,
    )

    async def failing_extend_subscription(*args, **kwargs):
        raise RuntimeError("Ошибка продления подписки")

    monkeypatch.setattr(
        "app.services.subscriptions.extend_subscription",
        failing_extend_subscription,
    )

    with pytest.raises(RuntimeError, match="Ошибка продления подписки"):
        await process_successful_payment(
            session,
            payment_id=payment.id,
        )

    await session.refresh(payment)

    assert payment.status == "pending"

    result = await session.execute(
        select(func.count())
        .select_from(Subscription)
        .where(Subscription.user_id == user_id)
    )
    assert result.scalar_one() == 0

    @pytest.mark.asyncio
    async def test_successful_payment_creates_new_period_after_expiry(
            session: AsyncSession,
    ) -> None:
        """После истечения подписки оплата создаёт новый период."""
        from datetime import datetime, timedelta, timezone

        from app.models.subscription import Subscription
        from app.services.payments import process_successful_payment

        user = await create_test_user(session, telegram_id=20007)
        user_id = user.id
        plan = await create_test_plan(session)

        now = datetime.now(timezone.utc)
        old_expiry = now - timedelta(days=10)

        old_subscription = Subscription(
            user_id=user_id,
            plan_id=plan.id,
            starts_at=(old_expiry - timedelta(days=30)).replace(tzinfo=None),
            expires_at=old_expiry.replace(tzinfo=None),
            status="active",
        )
        session.add(old_subscription)
        await session.commit()
        await session.refresh(old_subscription)

        old_subscription_id = old_subscription.id

        payment = await create_payment(
            session,
            user_id=user_id,
            plan_id=plan.id,
        )

        processed_payment = await process_successful_payment(
            session,
            payment_id=payment.id,
        )

        assert processed_payment is not None
        assert processed_payment.status == "succeeded"

        result = await session.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .order_by(Subscription.id)
        )
        subscriptions = result.scalars().all()

        assert len(subscriptions) == 2

        new_subscription = next(
            subscription
            for subscription in subscriptions
            if subscription.id != old_subscription_id
        )

        assert new_subscription.status == "active"
        assert new_subscription.plan_id == plan.id
        assert new_subscription.starts_at >= old_expiry.replace(
            tzinfo=None
        )
        assert new_subscription.expires_at > now.replace(
            tzinfo=None
        ) + timedelta(days=29)

        await session.refresh(old_subscription)
        assert old_subscription.id == old_subscription_id
        assert old_subscription.expires_at == old_expiry.replace(
            tzinfo=None
        )