"""add is_trial flag to plans

Revision ID: 0473a506bd6e
Revises: 9c800a876ee0
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Замени значение revision на ID, созданный Alembic.
revision: str = "0473a506bd6e"
down_revision: Union[str, Sequence[str], None] = "9c800a876ee0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Добавляет признак пробного тарифа."""
    op.add_column(
        "plans",
        sa.Column(
            "is_trial",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )

    # Если пробный тариф уже существует, помечаем его.
    op.execute(
        sa.text(
            """
            UPDATE plans
            SET is_trial = 1
            WHERE name = 'Пробный период'
            """
        )
    )


def downgrade() -> None:
    """Удаляет признак пробного тарифа."""
    op.drop_column("plans", "is_trial")