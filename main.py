import asyncio
import logging
from contextlib import suppress

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import settings
from database.connection import init_db
from handlers import admin, auto_dl, download, info, start
from middlewares.auth import GroupApprovalMiddleware
from middlewares.logging import LoggingMiddleware
from middlewares.rate_limit import RateLimitMiddleware


def configure_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='[%(asctime)s] %(levelname)-7s %(name)s | %(message)s',
        datefmt='%H:%M:%S',
        force=True,
    )
    logging.getLogger('aiogram.event').setLevel(logging.WARNING)
    logging.getLogger('aiogram.dispatcher').setLevel(logging.CRITICAL)
    logging.getLogger('aiohttp.access').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING if not debug else logging.DEBUG)


configure_logging(settings.DEBUG)
logger = logging.getLogger('hypertech.bot')


async def start_healthcheck_server() -> tuple[web.AppRunner, web.BaseSite] | tuple[None, None]:
    """Start a tiny HTTP server for Render health checks and UptimeRobot pings."""
    if not settings.PORT:
        return None, None

    async def healthcheck(_: web.Request) -> web.Response:
        return web.json_response({'status': 'ok', 'service': 'hypertech-downloader-bot'})

    app = web.Application()
    app.router.add_get('/', healthcheck)
    app.router.add_get('/health', healthcheck)

    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host='0.0.0.0', port=settings.PORT)
    await site.start()
    logger.info('Health endpoint listening on port %s', settings.PORT)
    return runner, site


async def stop_healthcheck_server(runner: web.AppRunner | None) -> None:
    if runner is None:
        return

    with suppress(Exception):
        await runner.cleanup()


async def main():
    """Main bot entry point."""
    logger.info('Booting HyperTech Downloader Bot')
    init_db()
    logger.info('Database ready')

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )

    dp = Dispatcher()
    dp.message.middleware(LoggingMiddleware())
    dp.message.middleware(GroupApprovalMiddleware())
    dp.message.middleware(RateLimitMiddleware())

    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(download.router)
    dp.include_router(info.router)
    dp.include_router(auto_dl.router)

    from database.connection import get_db
    from database.models import User

    with get_db() as db:
        owner = db.query(User).filter(User.id == settings.OWNER_ID).first()
        if not owner:
            owner = User(id=settings.OWNER_ID, is_owner=True, is_admin=True)
            db.add(owner)
            db.commit()
            logger.info('Owner profile created for %s', settings.OWNER_ID)

    health_runner, _ = await start_healthcheck_server()

    try:
        logger.info('Polling started')
        await dp.start_polling(bot)
    finally:
        await stop_healthcheck_server(health_runner)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info('Shutdown requested. Bot stopped cleanly.')
