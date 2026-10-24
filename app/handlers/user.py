"""Participant-facing commands and callbacks."""

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.models.giveaway import Giveaway, GiveawayStatus
from app.models.referral import Referral, ReferralStatus
from app.models.ticket import Ticket, TicketStatus
from app.models.user import User
from app.services.invite_links import InviteLinkService

router = Router(name="user")


def main_keyboard(giveaway_id: str | None = None) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="📜 Rules", callback_data="rules")],
        [InlineKeyboardButton(text="📊 My stats", callback_data="mystats")],
        [InlineKeyboardButton(text="🏆 Leaderboard", callback_data="leaderboard")],
        [InlineKeyboardButton(text="🆘 Appeal", callback_data="appeal")],
    ]
    if giveaway_id:
        rows.insert(
            0,
            [
                InlineKeyboardButton(
                    text="🔗 Get referral link",
                    callback_data=f"getlink:{giveaway_id}",
                )
            ],
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession) -> None:
    user = await session.get(User, message.from_user.id)
    if user is None:
        user = User(
            id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
            language_code=message.from_user.language_code,
            is_bot=message.from_user.is_bot,
        )
        session.add(user)
    else:
        user.username = message.from_user.username
        user.first_name = message.from_user.first_name
        user.last_name = message.from_user.last_name

    giveaway = await session.scalar(
        select(Giveaway)
        .where(Giveaway.status == GiveawayStatus.ACTIVE)
        .order_by(Giveaway.created_at.desc())
        .limit(1)
    )
    gid = giveaway.id if giveaway else None

    text = (
        "Welcome to the referral giveaway bot.\n\n"
        "Invite friends using your personal link. "
        "Each confirmed new subscriber gives you tickets for the draw.\n\n"
        "Rules are fixed before the contest starts and cannot be changed silently."
    )
    if giveaway:
        text += f"\n\nActive contest: <b>{giveaway.title}</b>"
    await message.answer(text, reply_markup=main_keyboard(gid), parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "/start — start\n"
        "/rules — contest rules\n"
        "/myref — your referral link\n"
        "/mystats — your tickets and referrals\n"
        "/leaderboard — top inviters\n"
        "/appeal — submit an appeal"
    )


@router.message(Command("rules"))
@router.callback_query(F.data == "rules")
async def show_rules(event: Message | CallbackQuery, session: AsyncSession) -> None:
    giveaway = await session.scalar(
        select(Giveaway)
        .where(
            Giveaway.status.in_(
                [
                    GiveawayStatus.ACTIVE,
                    GiveawayStatus.SCHEDULED,
                    GiveawayStatus.ENDED,
                    GiveawayStatus.VERIFICATION,
                    GiveawayStatus.FINALIZED,
                ]
            )
        )
        .order_by(Giveaway.created_at.desc())
        .limit(1)
    )
    text = (
        giveaway.rules_text
        if giveaway and giveaway.rules_text
        else "No active contest rules published yet."
    )
    if isinstance(event, CallbackQuery):
        await event.message.answer(text)
        await event.answer()
    else:
        await event.answer(text)


@router.callback_query(F.data.startswith("getlink:"))
async def get_link(callback: CallbackQuery, session: AsyncSession, bot) -> None:
    giveaway_id = callback.data.split(":", 1)[1]
    try:
        svc = InviteLinkService(session, bot)
        link = await svc.get_or_create_personal_link(
            user_id=callback.from_user.id, giveaway_id=giveaway_id
        )
        await callback.message.answer(
            f"Your personal invite link:\n<code>{link.invite_link}</code>\n\n"
            "Share it. Only joins that Telegram reports with this exact link "
            "are counted. One person = one referral max.",
            parse_mode="HTML",
        )
    except ValueError as e:
        await callback.message.answer(f"Cannot create link: {e}")
    except RuntimeError as e:
        await callback.message.answer(f"Telegram error: {e}")
    await callback.answer()


@router.message(Command("mystats"))
@router.callback_query(F.data == "mystats")
async def my_stats(event: Message | CallbackQuery, session: AsyncSession) -> None:
    user_id = event.from_user.id
    giveaway = await session.scalar(
        select(Giveaway)
        .where(
            Giveaway.status.in_(
                [
                    GiveawayStatus.ACTIVE,
                    GiveawayStatus.ENDED,
                    GiveawayStatus.VERIFICATION,
                    GiveawayStatus.FINALIZED,
                ]
            )
        )
        .order_by(Giveaway.created_at.desc())
        .limit(1)
    )
    if not giveaway:
        text = "No active or recent contest."
    else:
        verified = await session.scalar(
            select(func.count()).where(
                and_(
                    Referral.giveaway_id == giveaway.id,
                    Referral.inviter_id == user_id,
                    Referral.status == ReferralStatus.VERIFIED,
                )
            )
        )
        tickets = await session.scalar(
            select(func.coalesce(func.sum(Ticket.weight), 0)).where(
                and_(
                    Ticket.giveaway_id == giveaway.id,
                    Ticket.user_id == user_id,
                    Ticket.status == TicketStatus.ACTIVE,
                )
            )
        )
        text = (
            f"Contest: {giveaway.title}\n"
            f"Verified referrals: {verified or 0}\n"
            f"Active tickets: {tickets or 0}"
        )
    if isinstance(event, CallbackQuery):
        await event.message.answer(text)
        await event.answer()
    else:
        await event.answer(text)


@router.message(Command("leaderboard"))
@router.callback_query(F.data == "leaderboard")
async def leaderboard(event: Message | CallbackQuery, session: AsyncSession) -> None:
    giveaway = await session.scalar(
        select(Giveaway)
        .where(
            Giveaway.status.in_(
                [
                    GiveawayStatus.ACTIVE,
                    GiveawayStatus.ENDED,
                    GiveawayStatus.VERIFICATION,
                    GiveawayStatus.FINALIZED,
                ]
            )
        )
        .order_by(Giveaway.created_at.desc())
        .limit(1)
    )
    if not giveaway:
        text = "No contest data."
    else:
        rows = (
            await session.execute(
                select(Referral.inviter_id, func.count().label("cnt"))
                .where(
                    and_(
                        Referral.giveaway_id == giveaway.id,
                        Referral.status == ReferralStatus.VERIFIED,
                    )
                )
                .group_by(Referral.inviter_id)
                .order_by(func.count().desc())
                .limit(20)
            )
        ).all()
        if not rows:
            text = "Leaderboard is empty."
        else:
            lines = [f"{i+1}. ID {r.inviter_id}: {r.cnt}" for i, r in enumerate(rows)]
            text = "Top inviters (verified):\n" + "\n".join(lines)
    if isinstance(event, CallbackQuery):
        await event.message.answer(text)
        await event.answer()
    else:
        await event.answer(text)


@router.message(Command("appeal"))
@router.callback_query(F.data == "appeal")
async def appeal_start(event: Message | CallbackQuery) -> None:
    text = (
        "To submit an appeal, send a message starting with:\n"
        "<code>/appeal_text Your explanation here</code>\n\n"
        "Appeals are reviewed manually. Include your user ID and contest title."
    )
    if isinstance(event, CallbackQuery):
        await event.message.answer(text, parse_mode="HTML")
        await event.answer()
    else:
        await event.answer(text, parse_mode="HTML")


@router.message(Command("appeal_text"))
async def appeal_text(message: Message, session: AsyncSession) -> None:
    from app.models.appeal import Appeal, AppealStatus

    body = (message.text or "").replace("/appeal_text", "", 1).strip()
    if len(body) < 10:
        await message.answer("Please provide more detail (min 10 characters).")
        return
    giveaway = await session.scalar(
        select(Giveaway).order_by(Giveaway.created_at.desc()).limit(1)
    )
    if not giveaway:
        await message.answer("No contest found.")
        return
    appeal = Appeal(
        giveaway_id=giveaway.id,
        user_id=message.from_user.id,
        subject="User appeal",
        body=body[:4000],
        status=AppealStatus.OPEN,
    )
    session.add(appeal)
    await message.answer("Appeal submitted. We will review it.")
