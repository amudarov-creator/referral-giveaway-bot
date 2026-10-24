"""Explainable anti-fraud signal evaluation."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fraud import FraudRiskLevel
from app.models.giveaway import Giveaway
from app.models.referral import Referral, ReferralStatus
from app.models.ticket import Ticket


async def evaluate_join_signals(
    session: AsyncSession,
    *,
    giveaway: Giveaway,
    inviter_id: int,
    invitee_id: int,
    joined_at: datetime,
) -> dict[str, Any]:
    """Return signals dict. Never claims identity resolution."""
    signals: dict[str, Any] = {
        "auto_reject": False,
        "suspicious": False,
        "reason_code": None,
        "detail": None,
        "risk_level": FraudRiskLevel.LOW,
        "checks": {},
    }

    window = joined_at - timedelta(minutes=5)
    burst_count = await session.scalar(
        select(func.count())
        .select_from(Referral)
        .where(
            and_(
                Referral.giveaway_id == giveaway.id,
                Referral.inviter_id == inviter_id,
                Referral.first_joined_at >= window,
                Referral.status.in_(
                    [ReferralStatus.PENDING, ReferralStatus.VERIFIED, ReferralStatus.SUSPICIOUS]
                ),
            )
        )
    )
    signals["checks"]["burst_5m"] = burst_count or 0
    if (burst_count or 0) >= 15:
        signals["suspicious"] = True
        signals["reason_code"] = "burst_joins"
        signals["detail"] = f"{burst_count} joins in 5 minutes"
        signals["risk_level"] = FraudRiskLevel.HIGH

    inviter_total = await session.scalar(
        select(func.count())
        .select_from(Referral)
        .where(
            and_(
                Referral.giveaway_id == giveaway.id,
                Referral.inviter_id == inviter_id,
                Referral.status == ReferralStatus.VERIFIED,
            )
        )
    )
    signals["checks"]["inviter_verified"] = inviter_total or 0
    if (inviter_total or 0) >= 100:
        signals["suspicious"] = True
        signals["reason_code"] = signals["reason_code"] or "high_concentration"
        signals["detail"] = (signals["detail"] or "") + f"; inviter has {inviter_total} verified"
        signals["risk_level"] = max(
            signals["risk_level"],
            FraudRiskLevel.MEDIUM,
            key=lambda x: ["low", "medium", "high", "critical"].index(x),
        )

    prior = await session.scalar(
        select(func.count())
        .select_from(Referral)
        .where(
            and_(
                Referral.invitee_id == invitee_id,
                Referral.giveaway_id != giveaway.id,
                Referral.status == ReferralStatus.VERIFIED,
            )
        )
    )
    signals["checks"]["invitee_prior_referrals"] = prior or 0

    return signals


async def suspend_tickets_for_referral(session: AsyncSession, referral_id: int) -> int:
    from app.models.ticket import TicketStatus

    result = await session.execute(
        select(Ticket).where(Ticket.referral_id == referral_id)
    )
    tickets = result.scalars().all()
    for t in tickets:
        if t.status == TicketStatus.ACTIVE:
            t.status = TicketStatus.SUSPENDED
    return len(tickets)
