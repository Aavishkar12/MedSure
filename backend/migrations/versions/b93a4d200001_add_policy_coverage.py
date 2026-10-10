"""Add policy summaries and coverage reports from the LLM-enabled main app.

Revision ID: b93a4d200001
Revises: e7725f800001
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = "b93a4d200001"
down_revision: Union[str, None] = "e7725f800001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "policysummary" not in tables:
        op.create_table(
            "policysummary",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("case_id", sa.Integer(), nullable=False),
            sa.Column("document_id", sa.Integer(), nullable=False),
            sa.Column("data", sa.JSON(), nullable=True),
            sa.Column("created_at", sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
            sa.ForeignKeyConstraint(["case_id"], ["case.id"]),
            sa.ForeignKeyConstraint(["document_id"], ["document.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_policysummary_case_id"), "policysummary", ["case_id"], unique=False)
    if "coveragereport" not in tables:
        op.create_table(
            "coveragereport",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("case_id", sa.Integer(), nullable=False),
            sa.Column("data", sa.JSON(), nullable=True),
            sa.Column("created_at", sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
            sa.ForeignKeyConstraint(["case_id"], ["case.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_coveragereport_case_id"), "coveragereport", ["case_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_coveragereport_case_id"), table_name="coveragereport")
    op.drop_table("coveragereport")
    op.drop_index(op.f("ix_policysummary_case_id"), table_name="policysummary")
    op.drop_table("policysummary")
