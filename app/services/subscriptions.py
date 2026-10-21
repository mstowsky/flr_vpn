from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan import Plan
from app.models.subscription import Subscription


def _as_utc(value: datetime) -> datetime:
    """Приводит дату к UTC, учитывая SQLite без timezone."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def get_user_subscription(
    session: AsyncSession,
    user_id: int,
    *,
    now: datetime | None = None,
) -> Subscription | None:
    """Возвращает последнюю действующую подписку пользователя."""

    current_time = _as_utc(now or datetime.now(timezone.utc))

    result = await session.execute(
        select(Subscription)
        .where(
            Subscription.user_id == user_id,
            Subscription.status == "active",
            Subscription.expires_at > current_time,
        )
        .order_by(
            Subscription.expires_at.desc(),
            Subscription.id.desc(),
        )
    )

    return result.scalars().first()


async def create_subscription(
    session: AsyncSession,
    *,
    user_id: int,
    plan_id: int,
    now: datetime | None = None,
    commit: bool = True,
) -> Subscription:
    """Создаёт подписку на активный тариф."""

    current_time = _as_utc(
        now or datetime.now(timezone.utc)
    )

    result = await session.execute(
        select(Plan).where(
            Plan.id == plan_id,
            Plan.is_active.is_(True),
        )
    )
    plan = result.scalar_one_or_none()

    if plan is None:
        raise ValueError(
            f"Активный тариф с ID {plan_id} не найден."
        )

    subscription = Subscription(
        user_id=user_id,
        plan_id=plan.id,
        starts_at=current_time,
        expires_at=current_time + timedelta(
            days=plan.duration_days
        ),
        status="active",
    )

    session.add(subscription)
    if commit:
        await session.commit()
        await session.refresh(subscription)

    return subscription


async def extend_subscription(
    session: AsyncSession,
    *,
    user_id: int,
    plan_id: int,
    now: datetime | None = None,
    commit: bool = True,
) -> Subscription:
    """Продлевает действующую подписку или создаёт новый период."""

    current_time = _as_utc(
        now or datetime.now(timezone.utc)
    )

    result = await session.execute(
        select(Plan).where(
            Plan.id == plan_id,
            Plan.is_active.is_(True),
        )
    )
    plan = result.scalar_one_or_none()

    if plan is None:
        raise ValueError(
            f"Активный тариф с ID {plan_id} не найден."
        )

    subscription = await get_user_subscription(
        session,
        user_id,
        now=current_time,
    )

    if subscription is None:
        return await create_subscription(
            session,
            user_id=user_id,
            plan_id=plan_id,
            now=current_time,
            commit=commit,
        )

    current_expiry = _as_utc(subscription.expires_at)

    subscription.expires_at = max(
        current_time,
        current_expiry,
    ) + timedelta(days=plan.duration_days)

    subscription.plan_id = plan.id
    subscription.updated_at = current_time

    if commit:
        await session.commit()
        await session.refresh(subscription)

    return subscription


async def expire_subscriptions(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> int:
    """Переводит истёкшие активные подписки в статус expired."""

    current_time = _as_utc(
        now or datetime.now(timezone.utc)
    )

    result = await session.execute(
        select(Subscription).where(
            Subscription.status == "active",
            Subscription.expires_at <= current_time,
        )
    )

    subscriptions = result.scalars().all()

    for subscription in subscriptions:
        subscription.status = "expired"
        subscription.updated_at = current_time

    if subscriptions:
        await session.commit()

    return len(subscriptions)


async def get_user_subscription_info(
    session: AsyncSession,
    user_id: int,
    *,
    now: datetime | None = None,
) -> dict[str, str | datetime | int] | None:
    """
    Возвращает информацию о действующей подписке пользователя.

    Оставшиеся дни округляются вверх.
    Если действующей подписки нет, возвращает None.
    """

    current_time = _as_utc(now or datetime.now(timezone.utc))

    subscription = await get_user_subscription(
        session,
        user_id,
        now=current_time,
    )

    if subscription is None:
        return None

    expires_at = _as_utc(subscription.expires_at)
    remaining_seconds = (expires_at - current_time).total_seconds()

    # Даже если осталось меньше суток, показываем 1 день.
    remaining_days = max(
        1,
        int((remaining_seconds + 86_399) // 86_400),
    )

    return {
        "status": subscription.status,
        "expires_at": expires_at,
        "remaining_days": remaining_days,
    }