"""add_document_versioning

Revision ID: 7ded17ffc82f
Revises: f24b8ab225da
Create Date: 2026-09-02 12:51:57.454184

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7ded17ffc82f'
down_revision: Union[str, Sequence[str], None] = 'f24b8ab225da'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Adds self-referential versioning columns to generated_cv and
    generated_cover_letter, mirroring role_match_analysis's
    parent_analysis_id/superseded_by_id pattern: no "is_current" flag,
    the head of a version chain is whichever row has superseded_by_id
    IS NULL, and the root is found by walking parent_version_id back
    to null. All columns are nullable/additive - existing rows are
    unaffected and become single-node chains.
    """
    for table in ("generated_cv", "generated_cover_letter"):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column("parent_version_id", sa.Integer(), nullable=True))
            batch_op.add_column(sa.Column("superseded_by_id", sa.Integer(), nullable=True))
            batch_op.add_column(sa.Column("edit_source", sa.String(length=32), nullable=True))
            batch_op.add_column(sa.Column("edit_instruction", sa.Text(), nullable=True))
            batch_op.add_column(sa.Column("edit_target_excerpt", sa.Text(), nullable=True))
            batch_op.create_foreign_key(
                f"fk_{table}_parent_version_id",
                table,
                ["parent_version_id"],
                ["id"],
                ondelete="SET NULL",
            )
            batch_op.create_foreign_key(
                f"fk_{table}_superseded_by_id",
                table,
                ["superseded_by_id"],
                ["id"],
                ondelete="SET NULL",
            )


def downgrade() -> None:
    """Downgrade schema."""
    for table in ("generated_cv", "generated_cover_letter"):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_constraint(f"fk_{table}_superseded_by_id", type_="foreignkey")
            batch_op.drop_constraint(f"fk_{table}_parent_version_id", type_="foreignkey")
            batch_op.drop_column("edit_target_excerpt")
            batch_op.drop_column("edit_instruction")
            batch_op.drop_column("edit_source")
            batch_op.drop_column("superseded_by_id")
            batch_op.drop_column("parent_version_id")
