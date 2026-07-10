"""
Main entry point for HyperTech Downloader Bot.

Usage:
    python main.py
"""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import settings
from database.connection import init_db, get_db
from database.models import User

# ── Logging ────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="[%(asctime)s] %(levelname)-7s %(name)s | %(message)s",
    datefmt="%H:%M:%S",
    force=True,
)
logger = logging.getLogger("hypertech.main")


def _bootstrap_owner() -> None:
    """Ensure the configured OWNER_ID exists as an owner in the database."""
    if not settings.OWNER_ID:
        logger.warning("OWNER_ID is not set. No owner will be bootstrapped.")
        return

    with get_db() as db:
        user = db.query(User).filter(User.id == settings.OWNER_ID).first()
        if not user:
            user = User(id=settings.OWNER_ID, is_admin=True, is_owner=True)
            db.add(user)
        else:
            if not user.is_owner:
                user.is_owner = True
            if not user.is_admin:
                user.is_admin = True
        db.commit()
    logger.info("Owner bootstrapped: user_id=%s", settings.OWNER_ID)


async def main() -> None:
    logger.info("Initializing database...")
    init_db()

    _bootstrap_owner()

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # ── Register middleware ────────────────────────────────────
    from middlewares.logging import LoggingMiddleware
    from middlewares.auth import GroupApprovalMiddleware
    from middlewares.rate_limit import RateLimitMiddleware

    dp.message.middleware(LoggingMiddleware())
    dp.message.middleware(GroupApprovalMiddleware())
    dp.message.middleware(RateLimitMiddleware())

    # ── Register routers ──────────────────────────────────────
    from handlers.start import router as start_router
    from handlers.download import router as download_router
    from handlers.auto_dl import router as auto_dl_router
    from handlers.info import router as info_router
    from handlers.admin import router as admin_router

    dp.include_router(start_router)
    dp.include_router(admin_router)
    dp.include_router(auto_dl_router)
    dp.include_router(info_router)
    dp.include_router(download_router)   # download last so auto_download regex doesn't eat commands

    logger.info("Bot is starting polling...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        sys.exit(0)
