"""Referral attribution and ticket issuance — the core business logic."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.db.base import utcnow
from app.models.giveaway import Giveaway, GiveawayStatus
from app.models.invite_link import InviteLink
from app.models.referral import Referral, ReferralStatus
from app.models.ticket import Ticket, TicketSource, TicketStatus
from app.models.user import User
from app.services.audit import write_audit
from app.services.fraud import evaluate_join_signals

logger = get_logger(__name__)


class ReferralService:
    """
    Handles ChatMemberUpdated events for invite-link attribution.

    Rules (fixed before contest start and published):
    1. Only joins that carry a matching invite_link are attributed.
    2. One invitee contributes at most one referral per giveaway
       (DB unique constraint + application check).
    3. Self-referral is rejected.
    4. Joins after ends_at are ignored.
    5. Re-joins / duplicate updates are idempotent.
    6. If invite_link is absent or unknown → no credit (never guess).
    7. Tickets are issued only when status becomes VERIFIED.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def process_chat_member_update(
        self,
        *,
        chat_id: int,
        user_id: int,
        old_status: str,
        new_status: str,
        invite_link_str: str | None,
        update_id: int | None,
        event_date: int | None,
        via_join_request: bool = False,
        via_chat_folder: bool = False,
    ) -> dict[str, Any]:
        """Process a single ChatMemberUpdated event. Idempotent: safe to replay."""
        result: dict[str, Any] = {"action": "ignored", "reason": None}

        is_join = new_status in ("member", "restricted", "administrator", "creator") and old_status in (
            "left",
            "kicked",
            "banned",
        )
        if not is_join:
            result["reason"] = "not_a_join"
            return result

        if via_join_request or via_chat_folder:
            result["reason"] = "join_without_tracked_link"
            return result

        if not invite_link_str:
            result["reason"] = "no_invite_link_in_update"
            return result

        link = await self._find_active_link(invite_link_str, chat_id)
        if link is None:
            result["reason"] = "unknown_or_revoked_link"
            return result

        giveaway = await self.session.get(
            Giveaway, link.giveaway_id, options=[selectinload(Giveaway.required_channels)]
        )
        if giveaway is None:
            result["reason"] = "giveaway_missing"
            return result

        if giveaway.status not in (GiveawayStatus.ACTIVE, GiveawayStatus.SCHEDULED):
            if giveaway.status != GiveawayStatus.ACTIVE:
                result["reason"] = f"giveaway_status_{giveaway.status}"
                return result

        now = utcnow()
        if giveaway.ends_at and now > giveaway.ends_at:
            result["reason"] = "after_end"
            return result

        if link.owner_id == user_id:
            result["reason"] = "self_referral"
            await self._record_rejected_referral(
                giveaway=giveaway,
                inviter_id=link.owner_id,
                invitee_id=user_id,
                link=link,
                reason="self_referral",
                update_id=update_id,
                event_date=event_date,
            )
            return result

        await self._ensure_user(user_id)
        await self._ensure_user(link.owner_id)

        existing = await self.session.scalar(
            select(Referral).where(
                and_(
                    Referral.giveaway_id == giveaway.id,
                    Referral.invitee_id == user_id,
                )
            )
        )
        if existing is not None:
            result["action"] = "idempotent"
            result["reason"] = "already_attributed"
            result["referral_id"] = existing.id
            result["status"] = existing.status
            return result

        joined_at = (
            datetime.fromtimestamp(event_date, tz=timezone.utc) if event_date else now
        )
        referral = Referral(
            giveaway_id=giveaway.id,
            inviter_id=link.owner_id,
            invitee_id=user_id,
            invite_link_id=link.id,
            status=ReferralStatus.PENDING,
            status_reason="awaiting_verification",
            first_joined_at=joined_at,
            source_update_id=update_id,
            source_chat_member_date=event_date,
        )
        self.session.add(referral)
        await self.session.flush()

        signals = await evaluate_join_signals(
            self.session,
            giveaway=giveaway,
            inviter_id=link.owner_id,
            invitee_id=user_id,
            joined_at=joined_at,
        )

        if signals.get("auto_reject"):
            referral.status = ReferralStatus.REJECTED
            referral.status_reason = signals["reason_code"]
            referral.status_detail = signals.get("detail")
            await write_audit(
                self.session,
                actor_id=None,
                actor_type="system",
                action="referral_rejected",
                entity_type="referral",
                entity_id=str(referral.id),
                giveaway_id=giveaway.id,
                payload=signals,
            )
            result["action"] = "rejected"
            result["reason"] = signals["reason_code"]
            result["referral_id"] = referral.id
            return result

        if signals.get("suspicious"):
            referral.status = ReferralStatus.SUSPICIOUS
            referral.status_reason = signals["reason_code"]
            referral.status_detail = signals.get("detail")
            from app.models.fraud import FraudCase, FraudRiskLevel, FraudDecision

            case = FraudCase(
                giveaway_id=giveaway.id,
                user_id=link.owner_id,
                referral_id=referral.id,
                risk_level=signals.get("risk_level", FraudRiskLevel.MEDIUM),
                reason_code=signals["reason_code"],
                reason_detail=signals.get("detail"),
                signals=signals,
                decision=FraudDecision.PENDING,
            )
            self.session.add(case)
            result["action"] = "suspicious"
            result["reason"] = signals["reason_code"]
            result["referral_id"] = referral.id
            return result

        await self._verify_and_issue_ticket(referral, giveaway, link)
        result["action"] = "verified"
        result["referral_id"] = referral.id
        result["status"] = ReferralStatus.VERIFIED
        return result

    async def _verify_and_issue_ticket(
        self, referral: Referral, giveaway: Giveaway, link: InviteLink
    ) -> Ticket:
        referral.status = ReferralStatus.VERIFIED
        referral.status_reason = "clean_join"
        referral.verified_at = utcnow()

        tickets_per = int(giveaway.settings.get("tickets_per_referral", 1))
        ticket = Ticket(
            giveaway_id=giveaway.id,
            user_id=referral.inviter_id,
            referral_id=referral.id,
            source=TicketSource.REFERRAL,
            status=TicketStatus.ACTIVE,
            weight=tickets_per,
        )
        self.session.add(ticket)
        link.usage_count = (link.usage_count or 0) + 1

        await write_audit(
            self.session,
            actor_id=None,
            actor_type="system",
            action="referral_verified",
            entity_type="referral",
            entity_id=str(referral.id),
            giveaway_id=giveaway.id,
            payload={
                "inviter_id": referral.inviter_id,
                "invitee_id": referral.invitee_id,
                "tickets": tickets_per,
            },
        )
        await self.session.flush()
        return ticket

    async def _find_active_link(self, invite_link_str: str, chat_id: int) -> InviteLink | None:
        stmt = (
            select(InviteLink)
            .join(Giveaway, InviteLink.giveaway_id == Giveaway.id)
            .where(
                and_(
                    InviteLink.invite_link == invite_link_str,
                    InviteLink.is_revoked.is_(False),
                    Giveaway.channel_id == chat_id,
                )
            )
        )
        return await self.session.scalar(stmt)

    async def _ensure_user(self, user_id: int) -> User:
        user = await self.session.get(User, user_id)
        if user is None:
            user = User(id=user_id)
            self.session.add(user)
            await self.session.flush()
        return user

    async def _record_rejected_referral(
        self,
        *,
        giveaway: Giveaway,
        inviter_id: int,
        invitee_id: int,
        link: InviteLink,
        reason: str,
        update_id: int | None,
        event_date: int | None,
    ) -> None:
        existing = await self.session.scalar(
            select(Referral).where(
                and_(
                    Referral.giveaway_id == giveaway.id,
                    Referral.invitee_id == invitee_id,
                )
            )
        )
        if existing:
            return
        ref = Referral(
            giveaway_id=giveaway.id,
            inviter_id=inviter_id,
            invitee_id=invitee_id,
            invite_link_id=link.id,
            status=ReferralStatus.REJECTED,
            status_reason=reason,
            source_update_id=update_id,
            source_chat_member_date=event_date,
        )
        self.session.add(ref)
