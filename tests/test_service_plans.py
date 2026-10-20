from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database import Base
from app.models.plan import Plan
from app.services.plans import (
    create_plan,
    get_active_plans,
    get_plan_by_id,
)


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as db_session:
        yield db_session

    await engine.dispose()


@pytest.mark.asyncio
async def test_get_active_plans_returns_only_active_plans(
    session: AsyncSession,
) -> None:
    active_plan = Plan(
        name="Активный тариф",
        price_rub=199,
        duration_days=30,
        max_devices=2,
        is_active=True,
    )
    inactive_plan = Plan(
        name="Неактивный тариф",
        price_rub=499,
        duration_days=90,
        max_devices=3,
        is_active=False,
    )

    session.add_all([active_plan, inactive_plan])
    await session.commit()

    plans = await get_active_plans(session)

    assert len(plans) == 1
    assert plans[0].name == "Активный тариф"
    assert all(plan.is_active for plan in plans)


@pytest.mark.asyncio
async def test_get_plan_by_id_returns_existing_plan(
    session: AsyncSession,
) -> None:
    plan = Plan(
        name="Тестовый тариф",
        price_rub=199,
        duration_days=30,
        max_devices=2,
        is_active=True,
    )
    session.add(plan)
    await session.commit()
    await session.refresh(plan)

    result = await get_plan_by_id(session, plan.id)

    assert result is not None
    assert result.id == plan.id
    assert result.name == "Тестовый тариф"


@pytest.mark.asyncio
async def test_get_plan_by_id_returns_none_for_missing_id(
    session: AsyncSession,
) -> None:
    result = await get_plan_by_id(session, 999999)

    assert result is None


@pytest.mark.asyncio
async def test_create_plan_saves_plan_to_database(
    session: AsyncSession,
) -> None:
    plan = await create_plan(
        session,
        name="Новый тариф",
        price_rub=299,
        duration_days=30,
        max_devices=3,
        traffic_limit_gb=0,
    )

    assert plan.id is not None
    assert plan.name == "Новый тариф"
    assert plan.price_rub == 299
    assert plan.duration_days == 30
    assert plan.max_devices == 3
    assert plan.traffic_limit_gb == 0
    assert plan.is_active is True

    result = await session.execute(
        select(Plan).where(Plan.id == plan.id)
    )
    saved_plan = result.scalar_one()

    assert saved_plan.name == "Новый тариф"