"""Referral attribution records."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class ReferralStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    SUSPICIOUS = "suspicious"
    REJECTED = "rejected"
    REVOKED = "revoked"


class Referral(Base, TimestampMixin):
    """One verified referral = one invitee counted toward one inviter per giveaway."""

    __tablename__ = "referrals"
    __table_args__ = (
        UniqueConstraint("giveaway_id", "invitee_id", name="uq_referral_invitee_giveaway"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    giveaway_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("giveaways.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    inviter_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invitee_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invite_link_id: Mapped[int | None] = mapped_column(
        ForeignKey("invite_links.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[str] = mapped_column(
        String(16), default=ReferralStatus.PENDING, nullable=False, index=True
    )
    status_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    first_joined_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    source_update_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_chat_member_date: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    giveaway = relationship("Giveaway", back_populates="referrals")
    inviter = relationship("User", foreign_keys=[inviter_id], back_populates="referrals_as_inviter")
    invitee = relationship("User", foreign_keys=[invitee_id], back_populates="referrals_as_invitee")
    invite_link = relationship("InviteLink", back_populates="referrals")
    tickets = relationship("Ticket", back_populates="referral")

    def __repr__(self) -> str:
        return (
            f"<Referral id={self.id} inviter={self.inviter_id} "
            f"invitee={self.invitee_id} status={self.status}>"
        )
