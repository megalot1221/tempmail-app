from typing import Sequence, Union

from alembic import op


revision: str = "d652075601a8"
down_revision: Union[str, Sequence[str], None] = "e6fd871c3669"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
