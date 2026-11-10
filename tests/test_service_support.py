import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.support_message import SupportMessage
from app.models.support_ticket import SupportTicket
from app.models.user import User
from app.services.support import (
    close_support_ticket,
    get_message_by_admin_message_id,
    get_message_by_user_message_id,
    get_or_create_open_ticket,
    save_support_message,
)


async def create_user(
    session: AsyncSession,
    telegram_id: int,
) -> User:
    user = User(
        telegram_id=telegram_id,
        username=None,
        first_name="Test",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_get_or_create_open_ticket_creates_ticket(
    session: AsyncSession,
) -> None:
    user = await create_user(session, 200001)

    ticket = await get_or_create_open_ticket(
        session,
        user_id=user.id,
    )

    assert ticket.id is not None
    assert ticket.user_id == user.id
    assert ticket.status == "open"
    assert ticket.closed_at is None


@pytest.mark.asyncio
async def test_get_or_create_open_ticket_reuses_existing_ticket(
    session: AsyncSession,
) -> None:
    user = await create_user(session, 200002)

    first_ticket = await get_or_create_open_ticket(
        session,
        user_id=user.id,
    )
    second_ticket = await get_or_create_open_ticket(
        session,
        user_id=user.id,
    )

    result = await session.execute(
        select(func.count()).select_from(SupportTicket)
    )

    assert first_ticket.id == second_ticket.id
    assert result.scalar_one() == 1


@pytest.mark.asyncio
async def test_new_ticket_can_be_created_after_closing_previous(
    session: AsyncSession,
) -> None:
    user = await create_user(session, 200003)

    first_ticket = await get_or_create_open_ticket(
        session,
        user_id=user.id,
    )

    closed_ticket = await close_support_ticket(
        session,
        ticket_id=first_ticket.id,
    )

    second_ticket = await get_or_create_open_ticket(
        session,
        user_id=user.id,
    )

    assert closed_ticket is not None
    assert closed_ticket.status == "closed"
    assert closed_ticket.closed_at is not None
    assert second_ticket.id != first_ticket.id
    assert second_ticket.status == "open"


@pytest.mark.asyncio
async def test_save_support_message(
    session: AsyncSession,
) -> None:
    user = await create_user(session, 200004)

    ticket = await get_or_create_open_ticket(
        session,
        user_id=user.id,
    )

    message = await save_support_message(
        session,
        ticket_id=ticket.id,
        sender_type="client",
        content_type="text",
        preview="Нужна помощь",
        user_message_id=101,
        admin_message_id=501,
    )

    assert message.id is not None
    assert message.ticket_id == ticket.id
    assert message.sender_type == "client"
    assert message.content_type == "text"
    assert message.preview == "Нужна помощь"
    assert message.user_message_id == 101
    assert message.admin_message_id == 501

    saved_ticket = await session.get(SupportTicket, ticket.id)
    assert saved_ticket is not None
    assert saved_ticket.updated_at is not None


@pytest.mark.asyncio
async def test_find_message_by_admin_message_id(
    session: AsyncSession,
) -> None:
    user = await create_user(session, 200005)

    ticket = await get_or_create_open_ticket(
        session,
        user_id=user.id,
    )

    saved_message = await save_support_message(
        session,
        ticket_id=ticket.id,
        sender_type="client",
        content_type="text",
        preview="Сообщение",
        user_message_id=102,
        admin_message_id=502,
    )

    found_message = await get_message_by_admin_message_id(
        session,
        admin_message_id=502,
    )

    assert found_message is not None
    assert found_message.id == saved_message.id
    assert found_message.ticket_id == ticket.id


@pytest.mark.asyncio
async def test_find_message_by_user_message_id(
    session: AsyncSession,
) -> None:
    user = await create_user(session, 200006)

    ticket = await get_or_create_open_ticket(
        session,
        user_id=user.id,
    )

    saved_message = await save_support_message(
        session,
        ticket_id=ticket.id,
        sender_type="admin",
        content_type="text",
        preview="Ответ администратора",
        user_message_id=103,
        admin_message_id=503,
    )

    found_message = await get_message_by_user_message_id(
        session,
        ticket_id=ticket.id,
        user_message_id=103,
    )

    assert found_message is not None
    assert found_message.id == saved_message.id


@pytest.mark.asyncio
async def test_close_ticket_returns_none_when_already_closed(
    session: AsyncSession,
) -> None:
    user = await create_user(session, 200007)

    ticket = await get_or_create_open_ticket(
        session,
        user_id=user.id,
    )

    first_result = await close_support_ticket(
        session,
        ticket_id=ticket.id,
    )
    second_result = await close_support_ticket(
        session,
        ticket_id=ticket.id,
    )

    assert first_result is not None
    assert first_result.status == "closed"
    assert second_result is None


@pytest.mark.asyncio
async def test_cannot_save_message_to_closed_ticket(
    session: AsyncSession,
) -> None:
    user = await create_user(session, 200008)

    ticket = await get_or_create_open_ticket(
        session,
        user_id=user.id,
    )

    await close_support_ticket(
        session,
        ticket_id=ticket.id,
    )

    with pytest.raises(ValueError, match="уже закрыто"):
        await save_support_message(
            session,
            ticket_id=ticket.id,
            sender_type="client",
            content_type="text",
            preview="Позднее сообщение",
            user_message_id=104,
            admin_message_id=504,
        )

    result = await session.execute(
        select(func.count()).select_from(SupportMessage)
    )
    assert result.scalar_one() == 0


@pytest.mark.asyncio
async def test_save_message_rejects_invalid_sender_type(
    session: AsyncSession,
) -> None:
    user = await create_user(session, 200009)

    ticket = await get_or_create_open_ticket(
        session,
        user_id=user.id,
    )

    with pytest.raises(ValueError, match="sender_type"):
        await save_support_message(
            session,
            ticket_id=ticket.id,
            sender_type="unknown",
            content_type="text",
            preview="Сообщение",
            user_message_id=105,
            admin_message_id=505,
        )