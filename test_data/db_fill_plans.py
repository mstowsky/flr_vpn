import asyncio
import logging

from sqlalchemy import delete

from app.database import async_session_factory, close_db
from app.models.plan import Plan
from app.services.subscriptions import (
    TRIAL_DURATION_DAYS,
    TRIAL_MAX_DEVICES,
    TRIAL_PLAN_NAME,
    TRIAL_PRICE_RUB,
    TRIAL_TRAFFIC_LIMIT_GB,
)


logger = logging.getLogger(__name__)

SEED_PLANS = [
    {
        "name": "1 месяц",
        "price_rub": 199,
        "duration_days": 30,
        "max_devices": 2,
        "traffic_limit_gb": None,
        "is_trial": False,
    },
    {
        "name": "3 месяца",
        "price_rub": 499,
        "duration_days": 90,
        "max_devices": 3,
        "traffic_limit_gb": None,
        "is_trial": False,
    },
    {
        "name": "1 год",
        "price_rub": 1799,
        "duration_days": 365,
        "max_devices": 5,
        "traffic_limit_gb": None,
        "is_trial": False,
    },
    {
        "name": TRIAL_PLAN_NAME,
        "price_rub": TRIAL_PRICE_RUB,
        "duration_days": TRIAL_DURATION_DAYS,
        "max_devices": TRIAL_MAX_DEVICES,
        "traffic_limit_gb": TRIAL_TRAFFIC_LIMIT_GB,
        "is_trial": True,
    },
]


async def seed_plans() -> None:
    async with async_session_factory() as session:
        try:
            # Удаляем все существующие тарифы.
            result = await session.execute(
                delete(Plan)
            )
            logger.info(
                "Удалены существующие тарифы: %s",
                result.rowcount,
            )

            # Создаём тарифы заново.
            for plan_data in SEED_PLANS:
                plan = Plan(
                    **plan_data,
                    is_active=True,
                )
                session.add(plan)

                logger.info(
                    "Добавлен тариф '%s': %s руб., %s дней, "
                    "устройств: %s, лимит трафика: %s ГБ, "
                    "пробный: %s",
                    plan.name,
                    plan.price_rub,
                    plan.duration_days,
                    plan.max_devices,
                    plan.traffic_limit_gb,
                    plan.is_trial,
                )

            # Удаление и создание тарифов фиксируются одной транзакцией.
            await session.commit()

        except Exception:
            await session.rollback()
            logger.exception(
                "Ошибка при пересоздании тарифов."
            )
            raise

    logger.info(
        "Заполнение тарифов завершено. Создано: %s",
        len(SEED_PLANS),
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