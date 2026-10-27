"""PostgreSQL tables for durable backend records, not authoritative simulation state."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

metadata = sa.MetaData()
command_order_seq = sa.Sequence("command_order_seq", metadata=metadata)
parking_request_order_seq = sa.Sequence("parking_request_order_seq", metadata=metadata)

unity_sessions = sa.Table(
    "unity_sessions",
    metadata,
    sa.Column("unity_session_id", sa.Text, primary_key=True),
    sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("last_sequence", sa.BigInteger, nullable=False),
    sa.Column("ended_at", sa.DateTime(timezone=True)),
)

parking_requests = sa.Table(
    "parking_requests",
    metadata,
    sa.Column("request_order", sa.BigInteger, parking_request_order_seq, primary_key=True, autoincrement=False),
    sa.Column("request_id", sa.Text, nullable=False, unique=True),
    sa.Column("request_type", sa.Text, nullable=False),
    sa.Column("preferred_level", sa.Text),
    sa.Column("auto_depart", sa.Boolean, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

commands = sa.Table(
    "commands",
    metadata,
    sa.Column("command_order", sa.BigInteger, command_order_seq, primary_key=True, autoincrement=False),
    sa.Column("command_id", sa.Text, nullable=False, unique=True),
    sa.Column("unity_session_id", sa.Text, sa.ForeignKey("unity_sessions.unity_session_id"), nullable=False),
    sa.Column("spawn_request_id", sa.Text, sa.ForeignKey("parking_requests.request_id"), unique=True),
    sa.Column("command_type", sa.Text, nullable=False),
    sa.Column("payload", JSONB, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("delivery_count", sa.Integer, nullable=False),
    sa.Column("delivered_at", sa.DateTime(timezone=True)),
    sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
    sa.Column("result_message", sa.Text),
    sa.Column("vehicle_id", sa.Text),
    sa.Column("error_code", sa.Text),
    sa.Index("ix_commands_session_status_order", "unity_session_id", "status", "command_order"),
)

latest_garage_snapshot = sa.Table(
    "latest_garage_snapshot",
    metadata,
    sa.Column("singleton_id", sa.Integer, primary_key=True, autoincrement=False),
    sa.Column("unity_session_id", sa.Text, sa.ForeignKey("unity_sessions.unity_session_id"), nullable=False),
    sa.Column("sequence", sa.BigInteger, nullable=False),
    sa.Column("unity_timestamp", sa.DateTime(timezone=True), nullable=False),
    sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("payload", JSONB, nullable=False),
)
