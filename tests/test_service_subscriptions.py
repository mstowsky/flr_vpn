from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.plan import Plan
from app.models.provisioning_task import ProvisioningTask
from app.models.subscription import Subscription
from app.models.user import User
from app.services.subscriptions import (
    activate_trial_plan,
    create_subscription,
    expire_subscriptions,
    extend_subscription,
    get_user_subscription,
    get_user_subscription_info,
    subscription_deactivate,
    update_trial_plan,
)


def as_utc_naive(value: datetime) -> datetime:
    """Представляет UTC-дату в формате, возвращаемом SQLite."""
    return value.astimezone(UTC).replace(tzinfo=None)


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
    now = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)

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
    now = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)

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
    now = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)

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
    now = datetime.now(UTC)

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
    now = datetime.now(UTC)
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
    now = datetime.now(UTC)

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
    now = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)

    original = await create_subscription(
        session,
        user_id=user.id,
        plan_id=plan.id,
        now=now,
    )
    original_expiry = original.expires_at.replace(tzinfo=UTC)

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
    now = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)

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
    now = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)

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
    now = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)

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
    now = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)

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
    now = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)

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
    now = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)

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
    now = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)

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
        2026, 11, 20, 12, 0, tzinfo=UTC
    )
    assert info["remaining_days"] == 30


@pytest.mark.asyncio
async def test_get_user_subscription_info_rounds_up_remaining_days(
    session,
    user,
    plan,
):
    """Неполные сутки округляются вверх до одного дня."""
    now = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)

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
    now = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)

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
    now = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)

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


@pytest.mark.asyncio
async def test_activate_trial_period_creates_subscription_and_task(
    session,
    user,
):
    """Пробный период создаёт подписку и задачу выдачи доступа."""

    now = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)

    await update_trial_plan(session)

    subscription = await activate_trial_plan(
        session,
        user_id=user.id,
        now=now,
    )

    await session.refresh(user)

    assert subscription.id is not None
    assert subscription.user_id == user.id
    assert subscription.starts_at == as_utc_naive(now)
    assert subscription.expires_at == as_utc_naive(
        now + timedelta(days=3)
    )
    assert subscription.status == "active"
    assert user.has_used_trial is True

    plan_result = await session.execute(
        select(Plan).where(Plan.id == subscription.plan_id)
    )
    trial_plan = plan_result.scalar_one()

    assert trial_plan.name == "Пробный период"
    assert trial_plan.price_rub == 0
    assert trial_plan.duration_days == 3
    assert trial_plan.max_devices == 1
    assert trial_plan.traffic_limit_gb == 5
    assert trial_plan.is_active is True
    assert trial_plan.is_trial is True

    task_result = await session.execute(
        select(ProvisioningTask).where(
            ProvisioningTask.user_id == user.id
        )
    )
    tasks = task_result.scalars().all()

    assert len(tasks) == 1
    assert tasks[0].task_type == "create"
    assert tasks[0].status == "pending"
    assert tasks[0].subscription_id == subscription.id


@pytest.mark.asyncio
async def test_activate_trial_period_cannot_be_used_twice(
    session,
    user,
):
    """Повторная активация пробного периода запрещена."""
    await update_trial_plan(session)
    await activate_trial_plan(session, user_id=user.id)

    with pytest.raises(ValueError, match="уже использован"):
        await activate_trial_plan(session, user_id=user.id)


@pytest.mark.asyncio
async def test_activate_trial_period_rejects_active_subscription(
    session,
    user,
    plan,
):
    """Пробный период нельзя активировать при действующей подписке."""
    await create_subscription(
        session,
        user_id=user.id,
        plan_id=plan.id,
    )

    with pytest.raises(ValueError, match="действующей подписке"):
        await activate_trial_plan(session, user_id=user.id)

    await session.refresh(user)
    assert user.has_used_trial is False


@pytest.mark.asyncio
async def test_activate_trial_period_rejects_missing_user(session):
    """Для несуществующего пользователя пробный период не создаётся."""
    with pytest.raises(ValueError, match="не найден"):
        await activate_trial_plan(session, user_id=999999)


@pytest.mark.asyncio
async def test_update_trial_plan_updates_existing_plan(session):
    """Параметры существующего тарифа приводятся к константам."""

    trial_plan = Plan(
        name="Пробный период",
        price_rub=100,
        duration_days=7,
        max_devices=3,
        traffic_limit_gb=20,
        is_active=False,
    )
    session.add(trial_plan)
    await session.commit()

    updated_plan = await update_trial_plan(session)

    assert updated_plan.id == trial_plan.id
    assert updated_plan.name == "Пробный период"
    assert updated_plan.price_rub == 0
    assert updated_plan.duration_days == 3
    assert updated_plan.max_devices == 1
    assert updated_plan.traffic_limit_gb == 5
    assert updated_plan.is_active is True


@pytest.mark.asyncio
async def test_update_trial_plan_creates_missing_plan(session):
    """Если тариф отсутствует, он создаётся с нужными параметрами."""

    trial_plan = await update_trial_plan(session)

    assert trial_plan.id is not None
    assert trial_plan.name == "Пробный период"
    assert trial_plan.price_rub == 0
    assert trial_plan.duration_days == 3
    assert trial_plan.max_devices == 1
    assert trial_plan.traffic_limit_gb == 5
    assert trial_plan.is_active is True
    assert trial_plan.is_trial is True


@pytest.mark.asyncio
async def test_activate_trial_period_rejects_missing_plan(
    session,
    user,
):
    """Активация без настроенного тарифа завершается понятной ошибкой."""

    with pytest.raises(ValueError, match="не настроен"):
        await activate_trial_plan(
            session,
            user_id=user.id,
        )

    await session.refresh(user)
    assert user.has_used_trial is False


@pytest.mark.asyncio
async def test_activate_trial_period_rejects_inactive_plan(
    session,
    user,
):
    """Неактивный тариф нельзя использовать для пробного периода."""

    trial_plan = await update_trial_plan(session)
    trial_plan.is_active = False
    await session.commit()

    with pytest.raises(ValueError, match="неактивен"):
        await activate_trial_plan(
            session,
            user_id=user.id,
        )

    await session.refresh(user)
    assert user.has_used_trial is False


@pytest.mark.asyncio
async def test_deactivate_subscription_creates_task_and_keeps_subscription_active(
    session,
    user,
    plan,
):
    """Обычная деактивация создаёт задачу, но не меняет статус подписки."""

    now = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)

    subscription = await create_subscription(
        session,
        user_id=user.id,
        plan_id=plan.id,
        now=now,
    )

    original_expiry = subscription.expires_at

    task = await subscription_deactivate(
        session,
        subscription_id=subscription.id,
        now=now + timedelta(days=5),
    )

    await session.refresh(subscription)

    assert task.id is not None
    assert task.user_id == user.id
    assert task.subscription_id == subscription.id
    assert task.task_type == "disable"
    assert task.status == "pending"

    assert subscription.status == "active"
    assert subscription.expires_at == original_expiry


@pytest.mark.asyncio
async def test_deactivate_subscription_rejects_missing_subscription(
    session,
):
    """Деактивация несуществующей подписки вызывает ошибку."""

    now = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)

    with pytest.raises(ValueError, match="не найдена"):
        await subscription_deactivate(
            session,
            subscription_id=999999,
            now=now,
        )

    result = await session.execute(
        select(ProvisioningTask)
    )
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_deactivate_subscription_rejects_cancelled_subscription(
    session,
    user,
    plan,
):
    """Повторная деактивация отменённой подписки запрещена."""

    now = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)

    subscription = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        starts_at=as_utc_naive(now - timedelta(days=5)),
        expires_at=as_utc_naive(now + timedelta(days=25)),
        status="cancelled",
    )
    session.add(subscription)
    await session.commit()

    with pytest.raises(ValueError, match="не найдена"):
        await subscription_deactivate(
            session,
            subscription_id=subscription.id,
            now=now,
        )

    result = await session.execute(
        select(ProvisioningTask)
    )
    assert result.scalars().all() == []

    await session.refresh(subscription)
    assert subscription.status == "cancelled"


@pytest.mark.asyncio
async def test_deactivate_subscription_rejects_expired_subscription(
    session,
    user,
    plan,
):
    """Деактивация истёкшей подписки запрещена."""

    now = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)

    subscription = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        starts_at=as_utc_naive(now - timedelta(days=35)),
        expires_at=as_utc_naive(now - timedelta(days=5)),
        status="active",
    )
    session.add(subscription)
    await session.commit()

    with pytest.raises(ValueError, match="не найдена"):
        await subscription_deactivate(
            session,
            subscription_id=subscription.id,
            now=now,
        )

    result = await session.execute(
        select(ProvisioningTask)
    )
    assert result.scalars().all() == []

    await session.refresh(subscription)
    assert subscription.status == "active"


@pytest.mark.asyncio
async def test_deactivate_subscription_force_cancels_without_creating_task(
    session,
    user,
    plan,
):
    """force=True сразу отменяет подписку без создания задачи."""

    now = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)

    subscription = await create_subscription(
        session,
        user_id=user.id,
        plan_id=plan.id,
        now=now,
    )

    original_expiry = subscription.expires_at

    result = await subscription_deactivate(
        session,
        subscription_id=subscription.id,
        force=True,
        now=now + timedelta(days=5),
    )

    await session.refresh(subscription)

    assert result.id == subscription.id
    assert result.status == "cancelled"
    assert subscription.status == "cancelled"
    assert subscription.expires_at == original_expiry

    tasks_result = await session.execute(
        select(ProvisioningTask).where(
            ProvisioningTask.subscription_id == subscription.id
        )
    )

    assert tasks_result.scalars().all() == []


@pytest.mark.asyncio
async def test_deactivate_subscription_rejects_duplicate_pending_task(
    session,
    user,
    plan,
):
    """Нельзя создать две ожидающие задачи отключения одной подписки."""

    now = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)

    subscription = await create_subscription(
        session,
        user_id=user.id,
        plan_id=plan.id,
        now=now,
    )

    await subscription_deactivate(
        session,
        subscription_id=subscription.id,
        now=now,
    )

    with pytest.raises(ValueError, match="уже существует"):
        await subscription_deactivate(
            session,
            subscription_id=subscription.id,
            now=now,
        )

    await session.refresh(subscription)

    assert subscription.status == "active"

    tasks_result = await session.execute(
        select(ProvisioningTask).where(
            ProvisioningTask.subscription_id == subscription.id
        )
    )

    tasks = tasks_result.scalars().all()

    assert len(tasks) == 1
    assert tasks[0].task_type == "disable"
    assert tasks[0].status == "pending"