from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8a83d7634285"
down_revision: Union[str, Sequence[str], None] = "d652075601a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "country_code",
            sa.String(length=10),
            nullable=True,
        ),
    )

    op.add_column(
        "guest_sessions",
        sa.Column(
            "country_code",
            sa.String(length=10),
            nullable=True,
        ),
    )

    op.add_column(
        "mailboxes",
        sa.Column(
            "country_code",
            sa.String(length=10),
            nullable=True,
        ),
    )

    op.add_column(
        "activity",
        sa.Column(
            "country_code",
            sa.String(length=10),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("activity", "country_code")
    op.drop_column("mailboxes", "country_code")
    op.drop_column("guest_sessions", "country_code")
    op.drop_column("users", "country_code")