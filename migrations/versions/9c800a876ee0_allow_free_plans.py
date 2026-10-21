"""allow free plans

Revision ID: 9c800a876ee0
Revises: 9f21d2ad68d1
Create Date: 2026-10-22 00:02:23.280638
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "9c800a876ee0"
down_revision: Union[str, Sequence[str], None] = "9f21d2ad68d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Allow plans with a zero price."""
    with op.batch_alter_table("plans") as batch_op:
        batch_op.drop_constraint(
            "ck_plans_price_rub_positive",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_plans_price_rub_non_negative",
            "price_rub >= 0",
        )


def downgrade() -> None:
    """Restore the requirement for a positive plan price."""
    with op.batch_alter_table("plans") as batch_op:
        batch_op.drop_constraint(
            "ck_plans_price_rub_non_negative",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_plans_price_rub_positive",
            "price_rub > 0",
        )