"""Personal invite links created by the bot for attribution."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class InviteLink(Base, TimestampMixin):
    __tablename__ = "invite_links"
    __table_args__ = (
        UniqueConstraint("giveaway_id", "owner_id", name="uq_invite_owner_giveaway"),
        UniqueConstraint("invite_link", name="uq_invite_link"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    giveaway_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("giveaways.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    invite_link: Mapped[str] = mapped_column(String(256), nullable=False)
    name: Mapped[str] = mapped_column(String(32), nullable=False)

    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    member_limit: Mapped[int | None] = mapped_column(nullable=True)
    expire_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    usage_count: Mapped[int] = mapped_column(default=0, nullable=False)

    giveaway = relationship("Giveaway", back_populates="invite_links")
    owner = relationship("User", back_populates="invite_links")
    referrals = relationship("Referral", back_populates="invite_link")

    def __repr__(self) -> str:
        return f"<InviteLink id={self.id} owner={self.owner_id} revoked={self.is_revoked}>"
