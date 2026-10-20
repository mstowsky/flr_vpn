import asyncio
import logging

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession

from app.bot.main import start_bot
from app.config import BOT_TOKEN


async def main() -> None:
    session = AiohttpSession(
        proxy="http://127.0.0.1:10808"
    )
    bot = Bot(token=BOT_TOKEN, session=session)

    try:
        await start_bot(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    asyncio.run(main())
