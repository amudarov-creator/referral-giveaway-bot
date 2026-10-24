"""Simple Redis-backed rate limiter."""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, redis: Redis) -> None:
        self.redis = redis
        self.settings = get_settings()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id = None
        if isinstance(event, (Message, CallbackQuery)) and event.from_user:
            user_id = event.from_user.id
        if user_id is None:
            return await handler(event, data)

        key = f"rl:{user_id}"
        try:
            count = await self.redis.incr(key)
            if count == 1:
                await self.redis.expire(key, self.settings.rate_limit_window_seconds)
            if count > self.settings.rate_limit_max_requests:
                if isinstance(event, CallbackQuery):
                    await event.answer("Too many requests. Please wait.", show_alert=True)
                elif isinstance(event, Message):
                    await event.answer("Too many requests. Please wait a moment.")
                return None
        except Exception as e:
            logger.warning("rate_limit_redis_error", error=str(e))

        return await handler(event, data)
