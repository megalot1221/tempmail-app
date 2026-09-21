from typing import Sequence, Union

from alembic import op


revision: str = "5d221d14fc2a"
down_revision: Union[str, Sequence[str], None] = "5447b78112d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
