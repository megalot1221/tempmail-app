from typing import Sequence, Union

from alembic import op


revision: str = "e6fd871c3669"
down_revision: Union[str, Sequence[str], None] = "5d221d14fc2a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
