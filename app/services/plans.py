from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan import Plan


async def get_active_plans(session: AsyncSession) -> list[Plan]:
    """Возвращает все активные тарифы."""
    result = await session.execute(
        select(Plan)
        .where(Plan.is_active.is_(True))
        .order_by(Plan.duration_days)
    )
    return list(result.scalars().all())


async def get_plan_by_id(
    session: AsyncSession,
    plan_id: int,
) -> Plan | None:
    """Возвращает тариф по ID или None, если он не найден."""
    result = await session.execute(
        select(Plan).where(Plan.id == plan_id)
    )
    return result.scalar_one_or_none()


async def create_plan(
    session: AsyncSession,
    *,
    name: str,
    price_rub: int,
    duration_days: int,
    max_devices: int,
    traffic_limit_gb: int | None = None,
) -> Plan:
    """Создаёт тариф и сохраняет его в базе данных."""
    plan = Plan(
        name=name,
        price_rub=price_rub,
        duration_days=duration_days,
        max_devices=max_devices,
        traffic_limit_gb=traffic_limit_gb,
        is_active=True,
    )

    session.add(plan)
    await session.commit()
    await session.refresh(plan)

    return plan