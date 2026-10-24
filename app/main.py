"""Application entrypoint."""

from __future__ import annotations

import asyncio
import threading

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
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
    # Create tables if missing (phone-friendly deploys without shell access)
    try:
        from app.db.migrate import run_migrations

        run_migrations()
    except Exception as e:
        logger.error("migrations_failed", error=str(e))
        raise

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


async def _try_redis(url: str) -> Redis | None:
    """Connect to Redis; return None if unavailable (MemoryStorage fallback)."""
    client = Redis.from_url(url, decode_responses=True, socket_connect_timeout=2)
    try:
        await client.ping()
        safe = url.split("@")[-1] if "@" in url else url
        logger.info("redis_connected", url=safe)
        return client
    except Exception as e:
        logger.warning(
            "redis_unavailable_using_memory_storage",
            error=str(e),
            hint="Set REDIS_URL to a reachable Redis. FSM will not persist across restarts.",
        )
        try:
            await client.aclose()
        except Exception:
            pass
        return None


def create_dispatcher(storage: BaseStorage, redis: Redis | None) -> Dispatcher:
    dp = Dispatcher(storage=storage)

    dp.message.middleware(DbSessionMiddleware())
    dp.callback_query.middleware(DbSessionMiddleware())
    dp.chat_member.middleware(DbSessionMiddleware())

    if redis is not None:
        dp.message.middleware(RateLimitMiddleware(redis))
        dp.callback_query.middleware(RateLimitMiddleware(redis))
    else:
        logger.warning("rate_limit_disabled_no_redis")

    admin.router.message.middleware(AdminOnlyMiddleware())
    admin.router.callback_query.middleware(AdminOnlyMiddleware())

    dp.include_router(user.router)
    dp.include_router(chat_member.router)
    dp.include_router(admin.router)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    return dp


def _make_health_app() -> web.Application:
    app = web.Application()

    async def health(_request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    app.router.add_get("/health", health)
    return app


def _start_health_server(port: int) -> web.AppRunner:
    loop = asyncio.new_event_loop()
    app = _make_health_app()
    runner = web.AppRunner(app)

    def _run() -> None:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(runner.setup())
        site = web.TCPSite(runner, "0.0.0.0", port)
        loop.run_until_complete(site.start())
        logger.info("health_server_started", port=port)
        loop.run_forever()

    thread = threading.Thread(target=_run, name="health-server", daemon=True)
    thread.start()
    return runner


async def _build_storage_and_redis() -> tuple[BaseStorage, Redis | None]:
    settings = get_settings()
    redis = await _try_redis(settings.redis_url)
    if redis is not None:
        from aiogram.fsm.storage.redis import RedisStorage

        return RedisStorage(redis=redis), redis
    return MemoryStorage(), None


async def run_polling() -> None:
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_json)
    _start_health_server(settings.health_port)

    storage, redis = await _build_storage_and_redis()
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = create_dispatcher(storage, redis)
    try:
        await dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query", "chat_member", "my_chat_member"],
        )
    finally:
        if redis is not None:
            await redis.aclose()


async def _run_webhook_async() -> None:
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_json)

    storage, redis = await _build_storage_and_redis()
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = create_dispatcher(storage, redis)

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

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", settings.health_port)
    await site.start()
    logger.info("webhook_server_started", port=settings.health_port)
    try:
        await asyncio.Event().wait()
    finally:
        if redis is not None:
            await redis.aclose()
        await runner.cleanup()


def main() -> None:
    settings = get_settings()
    if settings.is_webhook:
        asyncio.run(_run_webhook_async())
    else:
        asyncio.run(run_polling())


if __name__ == "__main__":
    main()
