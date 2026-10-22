import asyncio

from sqlalchemy import text

from app.database import DATABASE_URL, engine


async def flush_database() -> None:
    """Удаляет все записи из таблиц прикладной базы данных."""

    print(f"База данных: {DATABASE_URL}")
    print(
        "\nВНИМАНИЕ! Все данные будут удалены. "
        "Восстановить их без резервной копии нельзя."
    )

    confirmation = input(
        "\nДля подтверждения введи DELETE: "
    )

    if confirmation != "DELETE":
        print("Очистка отменена.")
        return

    async with engine.begin() as connection:
        # Получаем все таблицы текущей SQLite-базы.
        result = await connection.execute(
            text(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                """
            )
        )

        tables = [row[0] for row in result.fetchall()]

        # Отключаем проверку внешних ключей для очистки
        # таблиц независимо от порядка связей.
        await connection.execute(
            text("PRAGMA defer_foreign_keys = ON")
        )

        for table in tables:
            # Имена таблиц получены из sqlite_master.
            # Кавычки защищают их при использовании в SQL.
            quoted_table = '"' + table.replace('"', '""') + '"'
            await connection.execute(
                text(f"DELETE FROM {quoted_table}")
            )

        print(f"\nОчищено таблиц: {len(tables)}")
        for table in tables:
            print(f"  - {table}")

    print("\nОчистка базы данных завершена.")


if __name__ == "__main__":
    try:
        asyncio.run(flush_database())
    finally:
        asyncio.run(engine.dispose())