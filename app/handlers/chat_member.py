"""Handler for ChatMemberUpdated — referral attribution entry point."""

from aiogram import Router
from aiogram.enums import ChatMemberStatus
from aiogram.types import ChatMemberUpdated
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.services.referral import ReferralService

router = Router(name="chat_member")
logger = get_logger(__name__)


def _status_str(member) -> str:
    status = member.status
    if isinstance(status, ChatMemberStatus):
        return status.value
    return str(status)


@router.chat_member()
async def on_chat_member(event: ChatMemberUpdated, session: AsyncSession) -> None:
    """Process membership changes. Bot must be channel admin with invite rights."""
    old_status = _status_str(event.old_chat_member)
    new_status = _status_str(event.new_chat_member)
    user_id = event.new_chat_member.user.id
    chat_id = event.chat.id

    invite_link_str = None
    if event.invite_link is not None:
        invite_link_str = event.invite_link.invite_link

    svc = ReferralService(session)
    result = await svc.process_chat_member_update(
        chat_id=chat_id,
        user_id=user_id,
        old_status=old_status,
        new_status=new_status,
        invite_link_str=invite_link_str,
        update_id=None,
        event_date=int(event.date.timestamp()) if event.date else None,
        via_join_request=bool(event.via_join_request),
        via_chat_folder=bool(event.via_chat_folder_invite_link),
    )
    logger.info(
        "chat_member_processed",
        chat_id=chat_id,
        user_id=user_id,
        old=old_status,
        new=new_status,
        result=result,
    )
