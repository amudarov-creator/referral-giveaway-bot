"""Admin authorization middleware."""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.core.config import get_settings


class AdminOnlyMiddleware(BaseMiddleware):
    """Reject non-admin users for admin routers. Always check server-side."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        settings = get_settings()
        user = None
        if isinstance(event, Message) and event.from_user:
            user = event.from_user
        elif isinstance(event, CallbackQuery) and event.from_user:
            user = event.from_user

        if user is None or user.id not in settings.admin_ids:
            if isinstance(event, CallbackQuery):
                await event.answer("Access denied.", show_alert=True)
            elif isinstance(event, Message):
                await event.answer("Access denied.")
            return None

        data["is_admin"] = True
        return await handler(event, data)
