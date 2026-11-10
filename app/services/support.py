from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.support_message import SupportMessage
from app.models.support_ticket import SupportTicket
from app.repositories import support as support_repository


async def get_or_create_open_ticket(
    session: AsyncSession,
    *,
    user_id: int,
) -> SupportTicket:
    """Возвращает открытое обращение или создаёт новое."""

    ticket = await support_repository.get_open_ticket_by_user_id(
        session,
        user_id,
    )

    if ticket is not None:
        return ticket

    try:
        ticket = await support_repository.create_ticket(
            session,
            user_id=user_id,
        )
        await session.commit()
        await session.refresh(ticket)

        return ticket

    except IntegrityError:
        # Возможно, параллельный запрос уже создал обращение.
        await session.rollback()

        ticket = await support_repository.get_open_ticket_by_user_id(
            session,
            user_id,
        )

        if ticket is None:
            raise

        return ticket


async def save_support_message(
    session: AsyncSession,
    *,
    ticket_id: int,
    sender_type: str,
    content_type: str,
    preview: str | None,
    user_message_id: int,
    admin_message_id: int,
) -> SupportMessage:
    """Сохраняет сообщение и обновляет дату последней активности обращения."""

    if sender_type not in {"client", "admin"}:
        raise ValueError(
            "sender_type должен быть 'client' или 'admin'."
        )

    ticket = await support_repository.get_ticket_by_id(
        session,
        ticket_id,
    )

    if ticket is None:
        raise ValueError(
            f"Обращение с ID {ticket_id} не найдено."
        )

    if ticket.status != "open":
        raise ValueError(
            f"Обращение с ID {ticket_id} уже закрыто."
        )

    try:
        message = await support_repository.create_message(
            session,
            ticket_id=ticket_id,
            sender_type=sender_type,
            content_type=content_type,
            preview=preview,
            user_message_id=user_message_id,
            admin_message_id=admin_message_id,
        )

        ticket.updated_at = datetime.now(UTC)

        await session.commit()
        await session.refresh(message)

        return message

    except Exception:
        await session.rollback()
        raise


async def get_message_by_admin_message_id(
    session: AsyncSession,
    admin_message_id: int,
) -> SupportMessage | None:
    """Находит сообщение по ID сообщения в чате администратора."""

    return await support_repository.get_message_by_admin_message_id(
        session,
        admin_message_id,
    )


async def get_message_by_user_message_id(
    session: AsyncSession,
    *,
    ticket_id: int,
    user_message_id: int,
) -> SupportMessage | None:
    """Находит сообщение по ID в чате пользователя и ID обращения."""

    return await support_repository.get_message_by_user_message_id(
        session,
        ticket_id=ticket_id,
        user_message_id=user_message_id,
    )


async def close_support_ticket(
    session: AsyncSession,
    *,
    ticket_id: int,
) -> SupportTicket | None:
    """Закрывает обращение. Возвращает None, если оно уже закрыто или не найдено."""

    ticket = await support_repository.get_ticket_by_id(
        session,
        ticket_id,
    )

    if ticket is None or ticket.status != "open":
        return None

    current_time = datetime.now(UTC)

    ticket.status = "closed"
    ticket.closed_at = current_time
    ticket.updated_at = current_time

    try:
        await session.commit()
        await session.refresh(ticket)
    except Exception:
        await session.rollback()
        raise

    return ticket