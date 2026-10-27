"""Persist Unity sessions, request intent, command outcomes and the latest snapshot."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_postgres_storage"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.schema.CreateSequence(sa.Sequence("parking_request_order_seq")))
    op.execute(sa.schema.CreateSequence(sa.Sequence("command_order_seq")))
    op.create_table(
        "unity_sessions",
        sa.Column("unity_session_id", sa.Text, primary_key=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_sequence", sa.BigInteger, nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "parking_requests",
        sa.Column("request_order", sa.BigInteger, primary_key=True, autoincrement=False),
        sa.Column("request_id", sa.Text, nullable=False, unique=True),
        sa.Column("request_type", sa.Text, nullable=False),
        sa.Column("preferred_level", sa.Text),
        sa.Column("auto_depart", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "commands",
        sa.Column("command_order", sa.BigInteger, primary_key=True, autoincrement=False),
        sa.Column("command_id", sa.Text, nullable=False, unique=True),
        sa.Column("unity_session_id", sa.Text, sa.ForeignKey("unity_sessions.unity_session_id"), nullable=False),
        sa.Column("spawn_request_id", sa.Text, sa.ForeignKey("parking_requests.request_id"), unique=True),
        sa.Column("command_type", sa.Text, nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivery_count", sa.Integer, nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("result_message", sa.Text),
        sa.Column("vehicle_id", sa.Text),
        sa.Column("error_code", sa.Text),
    )
    op.create_index("ix_commands_session_status_order", "commands", ["unity_session_id", "status", "command_order"])
    op.create_table(
        "latest_garage_snapshot",
        sa.Column("singleton_id", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("unity_session_id", sa.Text, sa.ForeignKey("unity_sessions.unity_session_id"), nullable=False),
        sa.Column("sequence", sa.BigInteger, nullable=False),
        sa.Column("unity_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("latest_garage_snapshot")
    op.drop_index("ix_commands_session_status_order", table_name="commands")
    op.drop_table("commands")
    op.drop_table("parking_requests")
    op.drop_table("unity_sessions")
    op.execute(sa.schema.DropSequence(sa.Sequence("command_order_seq")))
    op.execute(sa.schema.DropSequence(sa.Sequence("parking_request_order_seq")))
