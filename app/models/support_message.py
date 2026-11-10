from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SupportMessage(Base):
    __tablename__ = "support_messages"

    __table_args__ = (
        CheckConstraint(
            "sender_type IN ('client', 'admin')",
            name="ck_support_messages_sender_type_valid",
        ),
        UniqueConstraint(
            "ticket_id",
            "user_message_id",
            name="uq_support_messages_ticket_user_message",
        ),
        UniqueConstraint(
            "admin_message_id",
            name="uq_support_messages_admin_message",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("support_tickets.id"),
        nullable=False,
        index=True,
    )

    sender_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    content_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    preview: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    user_message_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    admin_message_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )