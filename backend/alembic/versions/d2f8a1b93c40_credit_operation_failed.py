# IA/backend/alembic/versions/d2f8a1b93c40_credit_operation_failed.py
"""Allow failed credit operations for flashcard generation recovery."""

from typing import Sequence, Union

from alembic import op

revision: str = "d2f8a1b93c40"
down_revision: Union[str, Sequence[str], None] = "c9a1e4f72b36"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("credit_operations_status_known", "credit_operations", type_="check")
    op.create_check_constraint(
        "credit_operations_status_known",
        "credit_operations",
        "status IN ('pending', 'completed', 'failed')",
    )


def downgrade() -> None:
    op.drop_constraint("credit_operations_status_known", "credit_operations", type_="check")
    op.create_check_constraint(
        "credit_operations_status_known",
        "credit_operations",
        "status IN ('pending', 'completed')",
    )
