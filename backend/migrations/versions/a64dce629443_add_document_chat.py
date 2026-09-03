"""add document chat sessions

Revision ID: a64dce629443
Revises: 7ded17ffc82f
Create Date: 2026-09-02 19:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a64dce629443"
down_revision: str | Sequence[str] | None = "7ded17ffc82f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the chat sidebar's data model: one session/message table pair per
    document type, plus a nullable chat_session_id on the generated
    documents themselves so the version history panel can group versions
    produced by the same chat session."""
    op.create_table(
        "cv_chat_session",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cv_root_id", sa.Integer(), nullable=True),
        sa.Column("current_cv_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("turn_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["cv_root_id"], ["generated_cv.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["current_cv_id"], ["generated_cv.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "cv_chat_message",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("proposed_patch_json", sa.Text(), nullable=True),
        sa.Column("patch_status", sa.String(length=16), nullable=True),
        sa.Column("resulting_cv_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["cv_chat_session.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resulting_cv_id"], ["generated_cv.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cv_chat_message_session_id", "cv_chat_message", ["session_id"], unique=False)

    op.create_table(
        "cover_letter_chat_session",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cl_root_id", sa.Integer(), nullable=True),
        sa.Column("current_cl_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("turn_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["cl_root_id"], ["generated_cover_letter.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["current_cl_id"], ["generated_cover_letter.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "cover_letter_chat_message",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("proposed_patch_json", sa.Text(), nullable=True),
        sa.Column("patch_status", sa.String(length=16), nullable=True),
        sa.Column("resulting_cl_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["cover_letter_chat_session.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resulting_cl_id"], ["generated_cover_letter.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cover_letter_chat_message_session_id", "cover_letter_chat_message", ["session_id"], unique=False
    )

    with op.batch_alter_table("generated_cv", schema=None) as batch_op:
        batch_op.add_column(sa.Column("chat_session_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_generated_cv_chat_session_id",
            "cv_chat_session",
            ["chat_session_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("generated_cover_letter", schema=None) as batch_op:
        batch_op.add_column(sa.Column("chat_session_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_generated_cover_letter_chat_session_id",
            "cover_letter_chat_session",
            ["chat_session_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("generated_cover_letter", schema=None) as batch_op:
        batch_op.drop_constraint("fk_generated_cover_letter_chat_session_id", type_="foreignkey")
        batch_op.drop_column("chat_session_id")

    with op.batch_alter_table("generated_cv", schema=None) as batch_op:
        batch_op.drop_constraint("fk_generated_cv_chat_session_id", type_="foreignkey")
        batch_op.drop_column("chat_session_id")

    op.drop_index("ix_cover_letter_chat_message_session_id", table_name="cover_letter_chat_message")
    op.drop_table("cover_letter_chat_message")
    op.drop_table("cover_letter_chat_session")
    op.drop_index("ix_cv_chat_message_session_id", table_name="cv_chat_message")
    op.drop_table("cv_chat_message")
    op.drop_table("cv_chat_session")
