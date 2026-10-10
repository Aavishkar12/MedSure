"""Add processing jobs and durable document extraction output.

Revision ID: e7725f800001
Revises: 728a18300001
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = "e7725f800001"
down_revision: Union[str, None] = "728a18300001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    document_columns = {column["name"] for column in inspector.get_columns("document")}
    if "classified_type" not in document_columns:
        op.add_column("document", sa.Column("classified_type", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    if "extraction_method" not in document_columns:
        op.add_column("document", sa.Column("extraction_method", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    if "extraction" not in document_columns:
        op.add_column("document", sa.Column("extraction", sa.JSON(), nullable=True))

    if "processingjob" not in inspector.get_table_names():
        op.create_table(
            "processingjob",
            sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("case_id", sa.Integer(), nullable=False),
            sa.Column("stage", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("progress", sa.Float(), nullable=False),
            sa.Column("total_files", sa.Integer(), nullable=False),
            sa.Column("processed_files", sa.Integer(), nullable=False),
            sa.Column("files", sa.JSON(), nullable=True),
            sa.Column("warnings", sa.JSON(), nullable=True),
            sa.Column("error", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column("created_at", sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
            sa.Column("completed_at", sqlmodel.sql.sqltypes.UTCDateTime(), nullable=True),
            sa.ForeignKeyConstraint(["case_id"], ["case.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_processingjob_case_id"), "processingjob", ["case_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_processingjob_case_id"), table_name="processingjob")
    op.drop_table("processingjob")
    op.drop_column("document", "extraction")
    op.drop_column("document", "extraction_method")
    op.drop_column("document", "classified_type")
