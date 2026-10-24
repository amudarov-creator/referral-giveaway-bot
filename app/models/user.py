"""User model — Telegram participants and organizers."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class UserStatus(StrEnum):
    ACTIVE = "active"
    BLOCKED = "blocked"
    DELETED = "deleted"


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)

    username: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    language_code: Mapped[str | None] = mapped_column(String(16), nullable=True)

    status: Mapped[str] = mapped_column(
        String(16), default=UserStatus.ACTIVE, nullable=False, index=True
    )
    rules_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    invite_links = relationship("InviteLink", back_populates="owner", lazy="selectin")
    tickets = relationship("Ticket", back_populates="user", lazy="selectin")
    referrals_as_inviter = relationship(
        "Referral",
        foreign_keys="Referral.inviter_id",
        back_populates="inviter",
        lazy="selectin",
    )
    referrals_as_invitee = relationship(
        "Referral",
        foreign_keys="Referral.invitee_id",
        back_populates="invitee",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r}>"
