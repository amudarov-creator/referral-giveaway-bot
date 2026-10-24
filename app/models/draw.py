"""Cryptographically verifiable draw records."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Draw(Base, TimestampMixin):
    __tablename__ = "draws"
    __table_args__ = (UniqueConstraint("giveaway_id", "draw_number", name="uq_draw_number"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    giveaway_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("giveaways.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    draw_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    seed_commitment: Mapped[str] = mapped_column(String(64), nullable=False)
    seed_revealed: Mapped[str | None] = mapped_column(Text, nullable=True)
    algorithm: Mapped[str] = mapped_column(String(64), nullable=False)

    results: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    protocol_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    giveaway = relationship("Giveaway", back_populates="draws")
    winners = relationship("DrawWinner", back_populates="draw", cascade="all, delete-orphan")


class DrawWinner(Base, TimestampMixin):
    __tablename__ = "draw_winners"
    __table_args__ = (
        UniqueConstraint("draw_id", "place", "user_id", name="uq_winner_place_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    draw_id: Mapped[int] = mapped_column(
        ForeignKey("draws.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    place: Mapped[int] = mapped_column(Integer, nullable=False)
    prize_title: Mapped[str] = mapped_column(String(256), nullable=False)
    ticket_count: Mapped[int] = mapped_column(Integer, nullable=False)
    is_leader_prize: Mapped[bool] = mapped_column(default=False, nullable=False)

    draw = relationship("Draw", back_populates="winners")
