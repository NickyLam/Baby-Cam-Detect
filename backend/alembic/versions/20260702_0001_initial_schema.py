"""Initial schema for Baby-Cam-Detect.

Revision ID: 20260702_0001
Revises:
Create Date: 2026-07-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260702_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("timezone", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "cameras",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("rtsp_url", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("resolution", sa.String(length=20), nullable=True),
        sa.Column("last_frame_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cameras_user_id", "cameras", ["user_id"], unique=False)

    op.create_table(
        "device_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("push_token", sa.String(length=500), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_device_tokens_user_id", "device_tokens", ["user_id"], unique=False)

    op.create_table(
        "notification_preferences",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("safety_alerts", sa.Boolean(), nullable=True),
        sa.Column("milestone_alerts", sa.Boolean(), nullable=True),
        sa.Column("quiet_start", sa.String(length=5), nullable=True),
        sa.Column("quiet_end", sa.String(length=5), nullable=True),
        sa.Column("cooldown_minutes", sa.Integer(), nullable=True),
        sa.Column("sensitivity", sa.String(length=10), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )

    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("camera_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clip_url", sa.String(length=500), nullable=True),
        sa.Column("thumbnail_url", sa.String(length=500), nullable=True),
        sa.Column("llm_response", sa.JSON(), nullable=True),
        sa.Column("frames_analyzed", sa.Integer(), nullable=True),
        sa.Column("dismissed", sa.Boolean(), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_events_camera_id", "events", ["camera_id"], unique=False)
    op.create_index("ix_events_detected_at", "events", ["detected_at"], unique=False)

    op.create_table(
        "analysis_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("camera_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_used", sa.String(length=50), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("result", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analysis_logs_camera_id", "analysis_logs", ["camera_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_analysis_logs_camera_id", table_name="analysis_logs")
    op.drop_table("analysis_logs")
    op.drop_index("ix_events_detected_at", table_name="events")
    op.drop_index("ix_events_camera_id", table_name="events")
    op.drop_table("events")
    op.drop_table("notification_preferences")
    op.drop_index("ix_device_tokens_user_id", table_name="device_tokens")
    op.drop_table("device_tokens")
    op.drop_index("ix_cameras_user_id", table_name="cameras")
    op.drop_table("cameras")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
