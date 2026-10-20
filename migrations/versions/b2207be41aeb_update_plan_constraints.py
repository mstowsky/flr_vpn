
"""update plan constraints

Revision ID: b2207be41aeb
Revises: 21e80b7032e2
Create Date: 2026-10-20 20:21:56.215324
"""

from typing import Sequence, Union

from alembic import op

revision: str = "b2207be41aeb"
down_revision: Union[str, Sequence[str], None] = "21e80b7032e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("plans") as batch_op:
        batch_op.drop_constraint(
            "ck_plans_price_rub_non_negative",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_plans_price_rub_positive",
            "price_rub > 0",
        )
        batch_op.drop_constraint(
            "ck_plans_traffic_limit_gb_positive",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_plans_traffic_limit_gb_non_negative",
            "traffic_limit_gb IS NULL OR traffic_limit_gb >= 0",
        )


def downgrade() -> None:
    with op.batch_alter_table("plans") as batch_op:
        batch_op.drop_constraint(
            "ck_plans_price_rub_positive",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_plans_price_rub_non_negative",
            "price_rub >= 0",
        )
        batch_op.drop_constraint(
            "ck_plans_traffic_limit_gb_non_negative",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_plans_traffic_limit_gb_positive",
            "traffic_limit_gb IS NULL OR traffic_limit_gb > 0",
        )
