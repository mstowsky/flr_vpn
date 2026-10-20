import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models import Plan


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine,
        expire_on_commit=False,
    )

    async with session_factory() as test_session:
        yield test_session

    await engine.dispose()


@pytest.mark.asyncio
async def test_create_plan_with_valid_values(session):
    plan = Plan(
        name="Стандарт",
        price_rub=199,
        duration_days=30,
        max_devices=3,
        traffic_limit_gb=100,
    )

    session.add(plan)
    await session.commit()
    await session.refresh(plan)

    assert plan.id is not None
    assert plan.name == "Стандарт"
    assert plan.price_rub == 199
    assert plan.duration_days == 30
    assert plan.max_devices == 3
    assert plan.traffic_limit_gb == 100
    assert plan.is_active is True
    assert plan.created_at is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("price", [0, -1])
async def test_plan_rejects_zero_or_negative_price(session, price):
    plan = Plan(
        name="Тестовый",
        price_rub=price,
        duration_days=30,
        max_devices=3,
    )

    session.add(plan)

    with pytest.raises(IntegrityError):
        await session.commit()

    await session.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize("duration", [0, -1])
async def test_plan_rejects_zero_or_negative_duration(session, duration):
    plan = Plan(
        name="Тестовый",
        price_rub=199,
        duration_days=duration,
        max_devices=3,
    )

    session.add(plan)

    with pytest.raises(IntegrityError):
        await session.commit()

    await session.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize("devices", [0, -1])
async def test_plan_rejects_zero_or_negative_devices(session, devices):
    plan = Plan(
        name="Тестовый",
        price_rub=199,
        duration_days=30,
        max_devices=devices,
    )

    session.add(plan)

    with pytest.raises(IntegrityError):
        await session.commit()

    await session.rollback()


@pytest.mark.asyncio
async def test_plan_rejects_negative_traffic_limit(session):
    plan = Plan(
        name="Тестовый",
        price_rub=199,
        duration_days=30,
        max_devices=3,
        traffic_limit_gb=-1,
    )

    session.add(plan)

    with pytest.raises(IntegrityError):
        await session.commit()

    await session.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize("traffic_limit", [0, None])
async def test_plan_allows_zero_or_null_traffic_limit(session, traffic_limit):
    plan = Plan(
        name="Тестовый",
        price_rub=199,
        duration_days=30,
        max_devices=3,
        traffic_limit_gb=traffic_limit,
    )

    session.add(plan)
    await session.commit()
    await session.refresh(plan)

    assert plan.id is not None
    assert plan.traffic_limit_gb == traffic_limit