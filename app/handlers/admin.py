"""Administrative commands — server-side auth enforced by middleware."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.base import utcnow
from app.models.giveaway import (
    Giveaway,
    GiveawayPrize,
    GiveawayRequiredChannel,
    GiveawayStatus,
)
from app.models.referral import Referral, ReferralStatus
from app.models.ticket import Ticket, TicketStatus
from app.models.user import User
from app.services.audit import write_audit
from app.services.crypto import sha256_hex
from app.services.draw import DrawService

router = Router(name="admin")
settings = get_settings()


@router.message(Command("admin"))
async def admin_help(message: Message) -> None:
    await message.answer(
        "Admin commands:\n"
        "/new_giveaway <channel_id> <title> — create draft\n"
        "/set_dates <gid> <start_iso> <end_iso>\n"
        "/add_prize <gid> <place> <title>\n"
        "/set_rules <gid> — reply with rules text\n"
        "/activate <gid> — freeze rules and go ACTIVE\n"
        "/pause <gid> / /resume <gid>\n"
        "/end <gid>\n"
        "/commit_seed <gid> — publish seed commitment\n"
        "/finalize <gid> — run draw\n"
        "/stats <gid>\n"
        "/cancel <gid> <reason>"
    )


@router.message(Command("new_giveaway"))
async def new_giveaway(message: Message, session: AsyncSession) -> None:
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Usage: /new_giveaway <channel_id> <title>")
        return
    try:
        channel_id = int(parts[1])
    except ValueError:
        await message.answer("channel_id must be integer")
        return
    title = parts[2][:256]

    org = await session.get(User, message.from_user.id)
    if org is None:
        org = User(id=message.from_user.id)
        session.add(org)
        await session.flush()

    gid = str(uuid4())
    g = Giveaway(
        id=gid,
        channel_id=channel_id,
        organizer_id=message.from_user.id,
        title=title,
        status=GiveawayStatus.DRAFT,
        settings={
            "tickets_per_referral": 1,
            "one_prize_per_user": True,
            "weighted_draw": True,
            "require_subscription": True,
            "leader_prize_enabled": False,
        },
        rules_version=1,
    )
    session.add(g)
    session.add(
        GiveawayRequiredChannel(
            giveaway_id=gid,
            channel_id=channel_id,
            is_primary=True,
        )
    )
    await write_audit(
        session,
        actor_id=message.from_user.id,
        actor_type="admin",
        action="giveaway_created",
        entity_type="giveaway",
        entity_id=gid,
        giveaway_id=gid,
        payload={"title": title, "channel_id": channel_id},
    )
    await message.answer(f"Draft created: <code>{gid}</code>", parse_mode="HTML")


@router.message(Command("set_dates"))
async def set_dates(message: Message, session: AsyncSession) -> None:
    parts = (message.text or "").split()
    if len(parts) < 4:
        await message.answer("Usage: /set_dates <gid> <start_iso> <end_iso>")
        return
    gid, start_s, end_s = parts[1], parts[2], parts[3]
    g = await session.get(Giveaway, gid)
    if not g or g.status != GiveawayStatus.DRAFT:
        await message.answer("Only draft giveaways can change dates.")
        return
    try:
        starts = datetime.fromisoformat(start_s.replace("Z", "+00:00"))
        ends = datetime.fromisoformat(end_s.replace("Z", "+00:00"))
    except ValueError:
        await message.answer("Invalid ISO dates")
        return
    if starts.tzinfo is None:
        starts = starts.replace(tzinfo=timezone.utc)
    if ends.tzinfo is None:
        ends = ends.replace(tzinfo=timezone.utc)
    g.starts_at = starts
    g.ends_at = ends
    await message.answer("Dates set.")


@router.message(Command("add_prize"))
async def add_prize(message: Message, session: AsyncSession) -> None:
    parts = (message.text or "").split(maxsplit=3)
    if len(parts) < 4:
        await message.answer("Usage: /add_prize <gid> <place> <title>")
        return
    gid, place_s, title = parts[1], parts[2], parts[3]
    try:
        place = int(place_s)
    except ValueError:
        await message.answer("place must be int")
        return
    g = await session.get(Giveaway, gid)
    if not g or g.status != GiveawayStatus.DRAFT:
        await message.answer("Only draft.")
        return
    session.add(
        GiveawayPrize(giveaway_id=gid, place=place, title=title[:256], quantity=1)
    )
    await message.answer("Prize added.")


@router.message(Command("set_rules"))
async def set_rules(message: Message, session: AsyncSession) -> None:
    if not message.reply_to_message or not message.reply_to_message.text:
        await message.answer("Reply to a message containing the rules text with /set_rules <gid>")
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Usage: reply with /set_rules <gid>")
        return
    gid = parts[1]
    g = await session.get(Giveaway, gid)
    if not g or g.status != GiveawayStatus.DRAFT:
        await message.answer("Only draft.")
        return
    text = message.reply_to_message.text
    g.rules_text = text
    g.rules_hash = sha256_hex(text)
    await message.answer(f"Rules set. Hash: {g.rules_hash}")


@router.message(Command("activate"))
async def activate(message: Message, session: AsyncSession) -> None:
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Usage: /activate <gid>")
        return
    gid = parts[1]
    g = await session.get(Giveaway, gid)
    if not g or g.status != GiveawayStatus.DRAFT:
        await message.answer("Only draft can be activated.")
        return
    if not g.rules_text or not g.ends_at:
        await message.answer("Set rules and dates first.")
        return
    g.status = GiveawayStatus.ACTIVE
    if not g.starts_at:
        g.starts_at = utcnow()
    await write_audit(
        session,
        actor_id=message.from_user.id,
        actor_type="admin",
        action="giveaway_activated",
        entity_type="giveaway",
        entity_id=gid,
        giveaway_id=gid,
        payload={"rules_hash": g.rules_hash},
    )
    await message.answer("Giveaway is now ACTIVE. Rules are frozen.")


@router.message(Command("pause"))
async def pause_giveaway(message: Message, session: AsyncSession) -> None:
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Usage: /pause <gid>")
        return
    g = await session.get(Giveaway, parts[1])
    if not g or g.status != GiveawayStatus.ACTIVE:
        await message.answer("Only an ACTIVE giveaway can be paused.")
        return
    g.status = GiveawayStatus.PAUSED
    await write_audit(
        session,
        actor_id=message.from_user.id,
        actor_type="admin",
        action="giveaway_paused",
        entity_type="giveaway",
        entity_id=g.id,
        giveaway_id=g.id,
    )
    await message.answer("Giveaway paused. New referrals will not be attributed until resume.")


@router.message(Command("resume"))
async def resume_giveaway(message: Message, session: AsyncSession) -> None:
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Usage: /resume <gid>")
        return
    g = await session.get(Giveaway, parts[1])
    if not g or g.status != GiveawayStatus.PAUSED:
        await message.answer("Only a PAUSED giveaway can be resumed.")
        return
    g.status = GiveawayStatus.ACTIVE
    await write_audit(
        session,
        actor_id=message.from_user.id,
        actor_type="admin",
        action="giveaway_resumed",
        entity_type="giveaway",
        entity_id=g.id,
        giveaway_id=g.id,
    )
    await message.answer("Giveaway resumed (ACTIVE).")


@router.message(Command("stats"))
async def stats_giveaway(message: Message, session: AsyncSession) -> None:
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Usage: /stats <gid>")
        return
    gid = parts[1]
    g = await session.get(Giveaway, gid)
    if not g:
        await message.answer("Giveaway not found.")
        return

    verified = await session.scalar(
        select(func.count()).where(
            and_(
                Referral.giveaway_id == gid,
                Referral.status == ReferralStatus.VERIFIED,
            )
        )
    )
    pending = await session.scalar(
        select(func.count()).where(
            and_(
                Referral.giveaway_id == gid,
                Referral.status == ReferralStatus.PENDING,
            )
        )
    )
    suspicious = await session.scalar(
        select(func.count()).where(
            and_(
                Referral.giveaway_id == gid,
                Referral.status == ReferralStatus.SUSPICIOUS,
            )
        )
    )
    rejected = await session.scalar(
        select(func.count()).where(
            and_(
                Referral.giveaway_id == gid,
                Referral.status == ReferralStatus.REJECTED,
            )
        )
    )
    tickets = await session.scalar(
        select(func.coalesce(func.sum(Ticket.weight), 0)).where(
            and_(
                Ticket.giveaway_id == gid,
                Ticket.status == TicketStatus.ACTIVE,
            )
        )
    )
    participants = await session.scalar(
        select(func.count(func.distinct(Ticket.user_id))).where(
            and_(
                Ticket.giveaway_id == gid,
                Ticket.status == TicketStatus.ACTIVE,
            )
        )
    )

    text = (
        f"<b>{g.title}</b>\n"
        f"ID: <code>{g.id}</code>\n"
        f"Status: {g.status}\n"
        f"Channel: {g.channel_id}\n"
        f"Starts: {g.starts_at}\n"
        f"Ends: {g.ends_at}\n"
        f"Rules hash: <code>{g.rules_hash or '—'}</code>\n"
        f"Seed commitment: <code>{g.seed_commitment or '—'}</code>\n\n"
        f"Referrals verified: {verified or 0}\n"
        f"Referrals pending: {pending or 0}\n"
        f"Referrals suspicious: {suspicious or 0}\n"
        f"Referrals rejected: {rejected or 0}\n"
        f"Active tickets (weight sum): {tickets or 0}\n"
        f"Participants with tickets: {participants or 0}"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("end"))
async def end_giveaway(message: Message, session: AsyncSession) -> None:
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Usage: /end <gid>")
        return
    g = await session.get(Giveaway, parts[1])
    if not g or g.status not in (GiveawayStatus.ACTIVE, GiveawayStatus.PAUSED):
        await message.answer("Invalid status.")
        return
    g.verification_ends_at = utcnow() + timedelta(hours=settings.verification_period_hours)
    g.status = GiveawayStatus.VERIFICATION
    await write_audit(
        session,
        actor_id=message.from_user.id,
        actor_type="admin",
        action="giveaway_ended",
        entity_type="giveaway",
        entity_id=g.id,
        giveaway_id=g.id,
    )
    await message.answer("Moved to VERIFICATION.")


@router.message(Command("commit_seed"))
async def commit_seed(message: Message, session: AsyncSession) -> None:
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Usage: /commit_seed <gid>")
        return
    svc = DrawService(session)
    try:
        result = await svc.create_seed_commitment(parts[1], message.from_user.id)
        await message.answer(
            f"Seed commitment published:\n<code>{result['commitment']}</code>\n"
            "Publish this hash in the channel before finalizing.",
            parse_mode="HTML",
        )
    except ValueError as e:
        await message.answer(str(e))


@router.message(Command("finalize"))
async def finalize(message: Message, session: AsyncSession) -> None:
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Usage: /finalize <gid>")
        return
    svc = DrawService(session)
    try:
        draw = await svc.finalize_draw(parts[1], message.from_user.id)
        winners = draw.results.get("winners", []) if draw.results else []
        lines = [
            f"Place {w['place']}: user {w['user_id']} ({w['tickets']} tickets) — {w['prize_title']}"
            for w in winners
        ]
        await message.answer(
            f"Draw finalized.\nSnapshot: <code>{draw.snapshot_hash}</code>\n"
            f"Protocol: <code>{draw.protocol_hash}</code>\n"
            f"Seed (reveal): <code>{draw.seed_revealed}</code>\n\n"
            + "\n".join(lines),
            parse_mode="HTML",
        )
    except ValueError as e:
        await message.answer(str(e))


@router.message(Command("cancel"))
async def cancel(message: Message, session: AsyncSession) -> None:
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Usage: /cancel <gid> <reason>")
        return
    g = await session.get(Giveaway, parts[1])
    if not g:
        await message.answer("Not found")
        return
    g.status = GiveawayStatus.CANCELLED
    g.cancelled_reason = parts[2][:1000]
    g.cancelled_at = utcnow()
    await write_audit(
        session,
        actor_id=message.from_user.id,
        actor_type="admin",
        action="giveaway_cancelled",
        entity_type="giveaway",
        entity_id=g.id,
        giveaway_id=g.id,
        reason=parts[2][:500],
    )
    await message.answer("Cancelled.")
