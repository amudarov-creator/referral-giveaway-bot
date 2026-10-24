"""Fraud / risk cases for manual review."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class FraudRiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FraudDecision(StrEnum):
    PENDING = "pending"
    CLEARED = "cleared"
    REJECTED = "rejected"
    ESCALATED = "escalated"


class FraudCase(Base, TimestampMixin):
    __tablename__ = "fraud_cases"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    giveaway_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("giveaways.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    referral_id: Mapped[int | None] = mapped_column(
        ForeignKey("referrals.id", ondelete="SET NULL"), nullable=True
    )

    risk_level: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    reason_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    signals: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    decision: Mapped[str] = mapped_column(
        String(16), default=FraudDecision.PENDING, nullable=False, index=True
    )
    decided_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    review_history: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, nullable=False
    )
