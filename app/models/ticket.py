"""Tickets awarded for verified referrals or other rules."""

from enum import StrEnum

from sqlalchemy import BigInteger, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class TicketStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"
    USED = "used"


class TicketSource(StrEnum):
    REFERRAL = "referral"
    BONUS = "bonus"
    MANUAL = "manual"


class Ticket(Base, TimestampMixin):
    __tablename__ = "tickets"
    __table_args__ = (
        UniqueConstraint("referral_id", "source", name="uq_ticket_referral_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    giveaway_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("giveaways.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    referral_id: Mapped[int | None] = mapped_column(
        ForeignKey("referrals.id", ondelete="SET NULL"), nullable=True, index=True
    )

    source: Mapped[str] = mapped_column(String(16), default=TicketSource.REFERRAL, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default=TicketStatus.ACTIVE, nullable=False, index=True
    )
    weight: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    giveaway = relationship("Giveaway", back_populates="tickets")
    user = relationship("User", back_populates="tickets")
    referral = relationship("Referral", back_populates="tickets")

    def __repr__(self) -> str:
        return f"<Ticket id={self.id} user={self.user_id} status={self.status}>"
