"""Giveaway and related configuration models."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class GiveawayStatus(StrEnum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    ACTIVE = "active"
    PAUSED = "paused"
    ENDED = "ended"
    VERIFICATION = "verification"
    FINALIZED = "finalized"
    CANCELLED = "cancelled"


class Giveaway(Base, TimestampMixin):
    """Core contest entity. Rules version is immutable after transition to ACTIVE."""

    __tablename__ = "giveaways"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )

    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    channel_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    organizer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        String(32), default=GiveawayStatus.DRAFT, nullable=False, index=True
    )

    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    rules_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    rules_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rules_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    seed_commitment: Mapped[str | None] = mapped_column(String(64), nullable=True)
    seed_commitment_published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    cancelled_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    prizes = relationship(
        "GiveawayPrize",
        back_populates="giveaway",
        cascade="all, delete-orphan",
        order_by="GiveawayPrize.place",
    )
    required_channels = relationship(
        "GiveawayRequiredChannel",
        back_populates="giveaway",
        cascade="all, delete-orphan",
    )
    invite_links = relationship("InviteLink", back_populates="giveaway")
    referrals = relationship("Referral", back_populates="giveaway")
    tickets = relationship("Ticket", back_populates="giveaway")
    draws = relationship("Draw", back_populates="giveaway")

    def __repr__(self) -> str:
        return f"<Giveaway id={self.id} status={self.status}>"


class GiveawayPrize(Base, TimestampMixin):
    __tablename__ = "giveaway_prizes"
    __table_args__ = (UniqueConstraint("giveaway_id", "place", name="uq_prize_place"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    giveaway_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("giveaways.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    place: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_leader_prize: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    giveaway = relationship("Giveaway", back_populates="prizes")


class GiveawayRequiredChannel(Base, TimestampMixin):
    __tablename__ = "giveaway_required_channels"
    __table_args__ = (
        UniqueConstraint("giveaway_id", "channel_id", name="uq_required_channel"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    giveaway_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("giveaways.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    channel_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    giveaway = relationship("Giveaway", back_populates="required_channels")
