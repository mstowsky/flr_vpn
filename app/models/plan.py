from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Plan(Base):
    __tablename__ = "plans"

    __table_args__ = (
        CheckConstraint(
            "price_rub >= 0",
            name="ck_plans_price_rub_non_negative",
        ),
        CheckConstraint(
            "duration_days > 0",
            name="ck_plans_duration_days_positive",
        ),
        CheckConstraint(
            "max_devices > 0",
            name="ck_plans_max_devices_positive",
        ),
        CheckConstraint(
            "traffic_limit_gb IS NULL OR traffic_limit_gb >= 0",
            name="ck_plans_traffic_limit_gb_non_negative",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    price_rub: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    duration_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    max_devices: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    traffic_limit_gb: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        default=None,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    is_trial: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )