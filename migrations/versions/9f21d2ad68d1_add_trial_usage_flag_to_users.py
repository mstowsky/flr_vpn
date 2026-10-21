"""add trial usage flag to users

Revision ID: 9f21d2ad68d1
Revises: 37d80bd9174f
Create Date: 2026-10-21 23:55:41.013745
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9f21d2ad68d1"
down_revision: Union[str, Sequence[str], None] = "37d80bd9174f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column(
            "has_used_trial",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "has_used_trial")