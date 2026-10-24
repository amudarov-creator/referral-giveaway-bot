"""Application entrypoint."""

import asyncio
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.handlers import admin, chat_member, user
from app.middlewares.auth import AdminOnlyMiddleware
from app.middlewares.db import DbSessionMiddleware
from app.middlewares.rate_limit import RateLimitMiddleware

logger = get_logger(__name__)


async def on_startup(bot: Bot) -> None:
    settings = get_settings()
    if settings.is_webhook and settings.webhook_host:
        url = f"{settings.webhook_host.rstrip('/')}{settings.webhook_path}"
        await bot.set_webhook(
            url,
            secret_token=settings.webhook_secret,
            allowed_updates=["message", "callback_query", "chat_member", "my_chat_member"],
        )
        logger.info("webhook_set", url=url)
    else:
        await bot.delete_webhook(drop_pending_updates=False)
        logger.info("polling_mode")


async def on_shutdown(bot: Bot) -> None:
    await bot.session.close()
    logger.info("shutdown")


def create_dispatcher(redis: Redis) -> Dispatcher:
    storage = RedisStorage(redis=redis)
    dp = Dispatcher(storage=storage)

    dp.message.middleware(DbSessionMiddleware())
    dp.callback_query.middleware(DbSessionMiddleware())
    dp.chat_member.middleware(DbSessionMiddleware())

    dp.message.middleware(RateLimitMiddleware(redis))
    dp.callback_query.middleware(RateLimitMiddleware(redis))

    admin.router.message.middleware(AdminOnlyMiddleware())
    admin.router.callback_query.middleware(AdminOnlyMiddleware())

    dp.include_router(user.router)
    dp.include_router(chat_member.router)
    dp.include_router(admin.router)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    return dp


async def run_polling() -> None:
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_json)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = create_dispatcher(redis)
    try:
        await dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query", "chat_member", "my_chat_member"],
        )
    finally:
        await redis.aclose()


def run_webhook() -> None:
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_json)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = create_dispatcher(redis)

    app = web.Application()
    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=settings.webhook_secret,
    ).register(app, path=settings.webhook_path)
    setup_application(app, dp, bot=bot)

    async def health(_request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    app.router.add_get("/health", health)

    web.run_app(app, host="0.0.0.0", port=settings.health_port)


def main() -> None:
    settings = get_settings()
    if settings.is_webhook:
        run_webhook()
    else:
        asyncio.run(run_polling())


if __name__ == "__main__":
    main()
