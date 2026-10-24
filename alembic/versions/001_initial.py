"""Initial schema for referral giveaway bot.

Revision ID: 001
Revises:
Create Date: 2026-10-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("first_name", sa.String(128), nullable=True),
        sa.Column("last_name", sa.String(128), nullable=True),
        sa.Column("language_code", sa.String(16), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("rules_accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_bot", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )
    op.create_index("ix_users_username", "users", ["username"])
    op.create_index("ix_users_status", "users", ["status"])

    op.create_table(
        "giveaways",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("channel_id", sa.BigInteger(), nullable=False),
        sa.Column("channel_username", sa.String(64), nullable=True),
        sa.Column("organizer_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rules_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("rules_hash", sa.String(64), nullable=True),
        sa.Column("rules_text", sa.Text(), nullable=True),
        sa.Column("settings", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("seed_commitment", sa.String(64), nullable=True),
        sa.Column("seed_commitment_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_reason", sa.Text(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organizer_id"], ["users.id"], name="fk_giveaways_organizer_id_users", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_giveaways"),
    )
    op.create_index("ix_giveaways_channel_id", "giveaways", ["channel_id"])
    op.create_index("ix_giveaways_status", "giveaways", ["status"])

    op.create_table(
        "giveaway_prizes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("giveaway_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("place", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_leader_prize", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["giveaway_id"], ["giveaways.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("giveaway_id", "place", name="uq_prize_place"),
    )
    op.create_index("ix_giveaway_prizes_giveaway_id", "giveaway_prizes", ["giveaway_id"])

    op.create_table(
        "giveaway_required_channels",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("giveaway_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("channel_id", sa.BigInteger(), nullable=False),
        sa.Column("channel_username", sa.String(64), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["giveaway_id"], ["giveaways.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("giveaway_id", "channel_id", name="uq_required_channel"),
    )

    op.create_table(
        "invite_links",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("giveaway_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("invite_link", sa.String(256), nullable=False),
        sa.Column("name", sa.String(32), nullable=False),
        sa.Column("is_revoked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("member_limit", sa.Integer(), nullable=True),
        sa.Column("expire_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["giveaway_id"], ["giveaways.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("giveaway_id", "owner_id", name="uq_invite_owner_giveaway"),
        sa.UniqueConstraint("invite_link", name="uq_invite_link"),
    )
    op.create_index("ix_invite_links_giveaway_id", "invite_links", ["giveaway_id"])
    op.create_index("ix_invite_links_owner_id", "invite_links", ["owner_id"])

    op.create_table(
        "referrals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("giveaway_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("inviter_id", sa.BigInteger(), nullable=False),
        sa.Column("invitee_id", sa.BigInteger(), nullable=False),
        sa.Column("invite_link_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("status_reason", sa.String(64), nullable=True),
        sa.Column("status_detail", sa.Text(), nullable=True),
        sa.Column("first_joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_update_id", sa.BigInteger(), nullable=True),
        sa.Column("source_chat_member_date", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["giveaway_id"], ["giveaways.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["inviter_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invitee_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invite_link_id"], ["invite_links.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("giveaway_id", "invitee_id", name="uq_referral_invitee_giveaway"),
    )
    op.create_index("ix_referrals_giveaway_id", "referrals", ["giveaway_id"])
    op.create_index("ix_referrals_inviter_id", "referrals", ["inviter_id"])
    op.create_index("ix_referrals_invitee_id", "referrals", ["invitee_id"])
    op.create_index("ix_referrals_status", "referrals", ["status"])

    op.create_table(
        "tickets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("giveaway_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("referral_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(16), nullable=False, server_default="referral"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("weight", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["giveaway_id"], ["giveaways.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["referral_id"], ["referrals.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("referral_id", "source", name="uq_ticket_referral_source"),
    )
    op.create_index("ix_tickets_giveaway_id", "tickets", ["giveaway_id"])
    op.create_index("ix_tickets_user_id", "tickets", ["user_id"])
    op.create_index("ix_tickets_status", "tickets", ["status"])

    op.create_table(
        "fraud_cases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("giveaway_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("referral_id", sa.Integer(), nullable=True),
        sa.Column("risk_level", sa.String(16), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("reason_detail", sa.Text(), nullable=True),
        sa.Column("signals", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("decision", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("decided_by", sa.BigInteger(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("review_history", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["giveaway_id"], ["giveaways.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["referral_id"], ["referrals.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fraud_cases_giveaway_id", "fraud_cases", ["giveaway_id"])
    op.create_index("ix_fraud_cases_decision", "fraud_cases", ["decision"])

    op.create_table(
        "draws",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("giveaway_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("draw_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("snapshot_data", postgresql.JSONB(), nullable=False),
        sa.Column("seed_commitment", sa.String(64), nullable=False),
        sa.Column("seed_revealed", sa.Text(), nullable=True),
        sa.Column("algorithm", sa.String(64), nullable=False),
        sa.Column("results", postgresql.JSONB(), nullable=True),
        sa.Column("protocol_hash", sa.String(64), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["giveaway_id"], ["giveaways.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("giveaway_id", "draw_number", name="uq_draw_number"),
    )

    op.create_table(
        "draw_winners",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("draw_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("place", sa.Integer(), nullable=False),
        sa.Column("prize_title", sa.String(256), nullable=False),
        sa.Column("ticket_count", sa.Integer(), nullable=False),
        sa.Column("is_leader_prize", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["draw_id"], ["draws.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("draw_id", "place", "user_id", name="uq_winner_place_user"),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.BigInteger(), nullable=True),
        sa.Column("actor_type", sa.String(16), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=True),
        sa.Column("entity_id", sa.String(64), nullable=True),
        sa.Column("giveaway_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("prev_hash", sa.String(64), nullable=True),
        sa.Column("entry_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("seq"),
    )
    op.create_index("ix_audit_log_seq", "audit_log", ["seq"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])
    op.create_index("ix_audit_log_giveaway_id", "audit_log", ["giveaway_id"])

    op.create_table(
        "appeals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("giveaway_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("referral_id", sa.Integer(), nullable=True),
        sa.Column("fraud_case_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("subject", sa.String(128), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("reviewed_by", sa.BigInteger(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["giveaway_id"], ["giveaways.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["referral_id"], ["referrals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["fraud_case_id"], ["fraud_cases.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_appeals_status", "appeals", ["status"])


def downgrade() -> None:
    op.drop_table("appeals")
    op.drop_table("audit_log")
    op.drop_table("draw_winners")
    op.drop_table("draws")
    op.drop_table("fraud_cases")
    op.drop_table("tickets")
    op.drop_table("referrals")
    op.drop_table("invite_links")
    op.drop_table("giveaway_required_channels")
    op.drop_table("giveaway_prizes")
    op.drop_table("giveaways")
    op.drop_table("users")
