import asyncio
import logging

from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from app.database import async_session_factory, close_db
from app.models.user import User


logger = logging.getLogger(__name__)


async def flush_users() -> None:
    """Удаляет все записи из таблицы users."""

    async with async_session_factory() as session:
        try:
            result = await session.execute(delete(User))
            deleted_count = result.rowcount or 0

            await session.commit()

            logger.info(
                "Таблица users очищена. Удалено записей: %s",
                deleted_count,
            )

        except IntegrityError:
            await session.rollback()
            logger.exception(
                "Не удалось очистить таблицу users: "
                "существуют связанные записи в других таблицах. "
                "Другие данные не удалялись."
            )
            raise

        except Exception:
            await session.rollback()
            logger.exception(
                "Ошибка при очистке таблицы users."
            )
            raise


async def main() -> None:
    try:
        await flush_users()
    finally:
        await close_db()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    asyncio.run(main())