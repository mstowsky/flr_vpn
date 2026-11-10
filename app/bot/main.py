
import logging

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.types import Message

from app.bot.handlers.admin import router as admin_router
from app.bot.handlers.user import router as users_router


logger = logging.getLogger(__name__)
messages_logger = logging.getLogger("user_messages")

dp = Dispatcher()


class IncomingMessageLoggingMiddleware(BaseMiddleware):
    """Регистрирует все входящие сообщения Telegram."""

    async def __call__(self, handler, event, data):
        if not isinstance(event, Message):
            return await handler(event, data)

        user = event.from_user

        if user is not None:
            username = (
                f"@{user.username}"
                if user.username
                else "не указан"
            )

            content = (
                event.text
                or event.caption
                or f"[{event.content_type}]"
            )

            messages_logger.info(
                "Входящее сообщение | "
                "telegram_id=%s | "
                "username=%s | "
                "first_name=%s | "
                "chat_id=%s | "
                "message_id=%s | "
                "content_type=%s | "
                "text=%r",
                user.id,
                username,
                user.first_name,
                event.chat.id,
                event.message_id,
                event.content_type,
                content,
            )

        return await handler(event, data)


# Регистрируем middleware для всех сообщений.
dp.message.outer_middleware(
    IncomingMessageLoggingMiddleware()
)

# Административные команды.
dp.include_router(admin_router)

# Пользовательские команды и обычные сообщения.
dp.include_router(users_router)


async def start_bot(bot: Bot) -> None:
    logger.info("Запуск Telegram-бота")
    await dp.start_polling(bot)
