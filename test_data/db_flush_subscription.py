import asyncio
import logging

from sqlalchemy import delete

from app.database import async_session_factory, close_db
from app.models.subscription import Subscription


logger = logging.getLogger(__name__)


async def flush_subscriptions() -> None:
    """Удаляет все записи из таблицы subscriptions."""

    async with async_session_factory() as session:
        try:
            result = await session.execute(delete(Subscription))
            deleted_count = result.rowcount or 0

            await session.commit()

            logger.info(
                "Таблица subscriptions очищена. "
                "Удалено записей: %s",
                deleted_count,
            )

        except Exception:
            await session.rollback()
            logger.exception(
                "Ошибка при очистке таблицы subscriptions."
            )
            raise


async def main() -> None:
    try:
        await flush_subscriptions()
    finally:
        await close_db()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    asyncio.run(main())