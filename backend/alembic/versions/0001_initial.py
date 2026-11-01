"""initial schema: watchlist, earnings events, provider snapshots, job runs

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watchlist_items",
        sa.Column("symbol", sa.Text, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "earnings_events",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("symbol", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("report_date", sa.Date, nullable=False),
        sa.Column("fiscal_date_ending", sa.Date, nullable=False),
        sa.Column("estimate", sa.Text, nullable=False, server_default=""),
        sa.Column("currency", sa.Text, nullable=False, server_default=""),
        sa.Column("rescheduled_to", sa.Date, nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("symbol", "fiscal_date_ending", "report_date"),
    )
    op.create_index("ix_earnings_events_report_date", "earnings_events", ["report_date"])
    op.create_index("ix_earnings_events_symbol_report_date", "earnings_events", ["symbol", "report_date"])
    op.create_table(
        "provider_snapshots",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon", sa.Text, nullable=False),
        sa.Column("body", sa.Text, nullable=False),
    )
    op.create_table(
        "job_runs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("trigger", sa.Text, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("success", sa.Boolean, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("event_count", sa.Integer, nullable=True),
        sa.Column("matched_symbols", sa.ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("missing_symbols", sa.ARRAY(sa.Text), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    for table in ("job_runs", "provider_snapshots", "earnings_events", "watchlist_items"):
        op.drop_table(table)
