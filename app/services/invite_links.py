"""Creation and management of personal Telegram invite links."""

from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.base import utcnow
from app.models.giveaway import Giveaway, GiveawayStatus
from app.models.invite_link import InviteLink
from app.models.user import User
from app.services.audit import write_audit

logger = get_logger(__name__)
settings = get_settings()


class InviteLinkService:
    def __init__(self, session: AsyncSession, bot: Bot) -> None:
        self.session = session
        self.bot = bot

    async def get_or_create_personal_link(
        self, *, user_id: int, giveaway_id: str
    ) -> InviteLink:
        giveaway = await self.session.get(Giveaway, giveaway_id)
        if giveaway is None:
            raise ValueError("giveaway_not_found")
        if giveaway.status not in (
            GiveawayStatus.ACTIVE,
            GiveawayStatus.SCHEDULED,
            GiveawayStatus.DRAFT,
        ):
            raise ValueError(f"cannot_create_link_in_status_{giveaway.status}")

        existing = await self.session.scalar(
            select(InviteLink).where(
                and_(
                    InviteLink.giveaway_id == giveaway_id,
                    InviteLink.owner_id == user_id,
                    InviteLink.is_revoked.is_(False),
                )
            )
        )
        if existing:
            return existing

        user = await self.session.get(User, user_id)
        if user is None:
            user = User(id=user_id)
            self.session.add(user)
            await self.session.flush()

        name = f"g{giveaway_id[:8]}_u{user_id}"[:32]
        try:
            tg_link = await self.bot.create_chat_invite_link(
                chat_id=giveaway.channel_id,
                name=name,
                creates_join_request=False,
            )
        except TelegramAPIError as e:
            logger.error("create_invite_link_failed", error=str(e), user_id=user_id)
            raise RuntimeError(f"telegram_api_error:{e}") from e

        link = InviteLink(
            giveaway_id=giveaway_id,
            owner_id=user_id,
            invite_link=tg_link.invite_link,
            name=name,
            member_limit=tg_link.member_limit,
            expire_date=tg_link.expire_date,
        )
        self.session.add(link)
        await write_audit(
            self.session,
            actor_id=user_id,
            actor_type="user",
            action="invite_link_created",
            entity_type="invite_link",
            entity_id=None,
            giveaway_id=giveaway_id,
            payload={"name": name},
        )
        await self.session.flush()
        return link

    async def revoke_link(self, link_id: int, admin_id: int | None = None) -> None:
        link = await self.session.get(InviteLink, link_id)
        if link is None or link.is_revoked:
            return
        giveaway = await self.session.get(Giveaway, link.giveaway_id)
        if giveaway is None:
            return
        try:
            await self.bot.revoke_chat_invite_link(
                chat_id=giveaway.channel_id,
                invite_link=link.invite_link,
            )
        except TelegramAPIError as e:
            logger.warning("revoke_failed", error=str(e), link_id=link_id)

        link.is_revoked = True
        link.revoked_at = utcnow()
        await write_audit(
            self.session,
            actor_id=admin_id,
            actor_type="admin" if admin_id else "system",
            action="invite_link_revoked",
            entity_type="invite_link",
            entity_id=str(link_id),
            giveaway_id=link.giveaway_id,
        )
