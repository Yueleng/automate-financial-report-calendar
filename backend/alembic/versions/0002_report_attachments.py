"""add report_attachments table for PDF financial reports

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_attachments",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column(
            "event_id",
            sa.Text,
            sa.ForeignKey("earnings_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.Text, nullable=False),
        sa.Column("content_type", sa.Text, nullable=False, server_default="application/pdf"),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("storage_key", sa.Text, nullable=False, unique=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_report_attachments_event_id", "report_attachments", ["event_id"])


def downgrade() -> None:
    op.drop_index("ix_report_attachments_event_id", table_name="report_attachments")
    op.drop_table("report_attachments")
