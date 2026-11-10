from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.support_message import SupportMessage
from app.models.support_ticket import SupportTicket


async def get_open_ticket_by_user_id(
    session: AsyncSession,
    user_id: int,
) -> SupportTicket | None:
    result = await session.execute(
        select(SupportTicket).where(
            SupportTicket.user_id == user_id,
            SupportTicket.status == "open",
        )
    )
    return result.scalar_one_or_none()


async def get_ticket_by_id(
    session: AsyncSession,
    ticket_id: int,
) -> SupportTicket | None:
    return await session.get(SupportTicket, ticket_id)


async def create_ticket(
    session: AsyncSession,
    *,
    user_id: int,
) -> SupportTicket:
    ticket = SupportTicket(
        user_id=user_id,
        status="open",
    )
    session.add(ticket)
    await session.flush()
    return ticket


async def get_message_by_admin_message_id(
    session: AsyncSession,
    admin_message_id: int,
) -> SupportMessage | None:
    result = await session.execute(
        select(SupportMessage).where(
            SupportMessage.admin_message_id == admin_message_id,
        )
    )
    return result.scalar_one_or_none()


async def get_message_by_user_message_id(
    session: AsyncSession,
    *,
    ticket_id: int,
    user_message_id: int,
) -> SupportMessage | None:
    result = await session.execute(
        select(SupportMessage).where(
            SupportMessage.ticket_id == ticket_id,
            SupportMessage.user_message_id == user_message_id,
        )
    )
    return result.scalar_one_or_none()


async def create_message(
    session: AsyncSession,
    *,
    ticket_id: int,
    sender_type: str,
    content_type: str,
    preview: str | None,
    user_message_id: int,
    admin_message_id: int,
) -> SupportMessage:
    message = SupportMessage(
        ticket_id=ticket_id,
        sender_type=sender_type,
        content_type=content_type,
        preview=preview,
        user_message_id=user_message_id,
        admin_message_id=admin_message_id,
    )
    session.add(message)
    await session.flush()
    return message