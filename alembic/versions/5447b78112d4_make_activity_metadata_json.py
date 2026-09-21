"""make activity metadata json

Revision ID: 5447b78112d4
Revises: ce85756acff3
Create Date: 2026-09-19 11:25:09.980367
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "5447b78112d4"
down_revision: Union[str, Sequence[str], None] = "ce85756acff3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "activity",
        "metadata_json",
        existing_type=sa.TEXT(),
        type_=sa.JSON(),
        existing_nullable=True,
        postgresql_using="metadata_json::json",
    )


def downgrade() -> None:
    op.alter_column(
        "activity",
        "metadata_json",
        existing_type=sa.JSON(),
        type_=sa.TEXT(),
        existing_nullable=True,
    )