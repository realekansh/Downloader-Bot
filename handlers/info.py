import platform
import time
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version

from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import func, text

from config import settings
from database.connection import get_db
from database.models import Download, Group, User
from utils.formatters import detail_text, format_group_info, format_uptime, format_user_info, panel
from utils.redis_client import get_redis

router = Router(name='info')
APP_STARTED_AT = datetime.now(timezone.utc)



def _package_version(name: str, fallback: str = 'Unavailable') -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return fallback



def _database_label_and_version(db) -> tuple[str, str]:
    dialect = db.bind.dialect.name.lower()
    label = 'PostgreSQL' if dialect == 'postgresql' else dialect.title()

    try:
        if dialect == 'postgresql':
            raw_version = db.execute(text('SELECT version()')).scalar() or ''
            version_text = str(raw_version).split(',')[0].replace('PostgreSQL ', '') or 'Unknown'
        elif dialect == 'sqlite':
            raw_version = db.execute(text('SELECT sqlite_version()')).scalar() or 'Unknown'
            version_text = str(raw_version)
        else:
            version_text = 'Unknown'
    except Exception:
        version_text = 'Unknown'

    return label, version_text



def _redis_version() -> str:
    if settings.DEV_MODE:
        return 'Disabled in DEV_MODE'

    try:
        redis_client = get_redis()
        info = redis_client.info('server')
        return str(info.get('redis_version') or 'Unknown')
    except Exception:
        return 'Unavailable'



def _uptime_text() -> str:
    elapsed = datetime.now(timezone.utc) - APP_STARTED_AT
    return format_uptime(int(elapsed.total_seconds()))


@router.message(Command('info'))
async def cmd_info(message: Message):
    """Show user or group statistics."""
    with get_db() as db:
        if message.chat.type in ['group', 'supergroup']:
            group = db.query(Group).filter(Group.id == message.chat.id).first()
            if not group:
                await message.answer(
                    panel('Group Setup Needed', ['Ask an admin to use /addgroup first.']),
                    parse_mode=ParseMode.HTML,
                )
                return
            info_text = format_group_info(group, db)
            await message.answer(info_text, parse_mode=ParseMode.HTML)
            return

        user = db.query(User).filter(User.id == message.from_user.id).first()
        if not user:
            await message.answer(
                panel('No Activity Yet', ['Use /download with a supported link to get started.']),
                parse_mode=ParseMode.HTML,
            )
            return

        info_text = format_user_info(user, db)
        await message.answer(info_text, parse_mode=ParseMode.HTML)


@router.message(Command('ping'))
async def cmd_ping(message: Message):
    """Show bot latency and uptime."""
    started = time.perf_counter()
    ping_message = await message.answer('<b>Pinging...</b>', parse_mode=ParseMode.HTML)
    latency_ms = round((time.perf_counter() - started) * 1000)

    await ping_message.edit_text(
        panel(
            f'Pong! {latency_ms} ms',
            [detail_text('Uptime', _uptime_text())],
        ),
        parse_mode=ParseMode.HTML,
    )


@router.message(Command('stats'))
async def cmd_stats(message: Message):
    """Show bot/runtime/database statistics."""
    with get_db() as db:
        database_label, database_version = _database_label_and_version(db)
        total_users = db.query(func.count(User.id)).scalar() or 0
        total_groups = db.query(func.count(Group.id)).scalar() or 0
        approved_groups = db.query(func.count(Group.id)).filter(Group.is_approved.is_(True)).scalar() or 0
        total_downloads = db.query(func.count(Download.id)).scalar() or 0
        completed_downloads = db.query(func.count(Download.id)).filter(Download.status == 'completed').scalar() or 0
        failed_downloads = db.query(func.count(Download.id)).filter(Download.status == 'failed').scalar() or 0

    stats_lines = [
        detail_text('Uptime', _uptime_text()),
        detail_text('Python', platform.python_version()),
        detail_text('Aiogram', _package_version('aiogram')),
        detail_text('SQLAlchemy', _package_version('sqlalchemy')),
        detail_text('yt-dlp', _package_version('yt-dlp')),
        detail_text('RQ', _package_version('rq')),
        detail_text('Redis', _redis_version()),
        detail_text('Database', database_label),
        detail_text('Database Version', database_version),
        detail_text('Download Path', settings.DOWNLOAD_PATH),
        '',
        detail_text('Users', total_users),
        detail_text('Groups', total_groups),
        detail_text('Approved Groups', approved_groups),
        detail_text('Total Downloads', total_downloads),
        detail_text('Completed Downloads', completed_downloads),
        detail_text('Failed Downloads', failed_downloads),
    ]

    await message.answer(
        panel('Bot Statistics', stats_lines),
        parse_mode=ParseMode.HTML,
    )
