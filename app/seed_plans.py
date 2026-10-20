import asyncio
import logging

from sqlalchemy import select

from app.database import async_session_factory, close_db
from app.models.plan import Plan


logger = logging.getLogger(__name__)

SEED_PLANS = [
    {
        "name": "1 месяц",
        "price_rub": 199,
        "duration_days": 30,
        "max_devices": 2,
        "traffic_limit_gb": None,
    },
    {
        "name": "3 месяца",
        "price_rub": 499,
        "duration_days": 90,
        "max_devices": 3,
        "traffic_limit_gb": None,
    },
    {
        "name": "1 год",
        "price_rub": 1799,
        "duration_days": 365,
        "max_devices": 5,
        "traffic_limit_gb": None,
    },
]


async def seed_plans() -> None:
    created = 0
    skipped = 0

    async with async_session_factory() as session:
        for plan_data in SEED_PLANS:
            result = await session.execute(
                select(Plan).where(Plan.name == plan_data["name"])
            )
            existing_plan = result.scalar_one_or_none()

            if existing_plan is not None:
                logger.info(
                    "Тариф '%s' уже существует — пропускаем",
                    plan_data["name"],
                )
                skipped += 1
                continue

            plan = Plan(**plan_data, is_active=True)
            session.add(plan)

            logger.info(
                "Добавлен тариф '%s': %s руб., %s дней",
                plan.name,
                plan.price_rub,
                plan.duration_days,
            )
            created += 1

        await session.commit()

    logger.info(
        "Заполнение тарифов завершено. Создано: %s, пропущено: %s",
        created,
        skipped,
    )


async def main() -> None:
    try:
        await seed_plans()
    finally:
        await close_db()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    asyncio.run(main())