import os
import platform
import time
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import func, text

from config import settings
from database.connection import get_db
from database.models import Download, Group, User
from utils.formatters import detail_text, format_bytes, format_group_info, format_uptime, format_user_info, panel
from utils.permissions import is_admin
from utils.redis_client import get_redis

router = Router(name='info')
APP_STARTED_AT = datetime.now(timezone.utc)



def _quote_block(lines: list[str]) -> str:
    return f"<blockquote>{'\n'.join(lines)}</blockquote>"



def _package_version(name: str, fallback: str = 'Unavailable') -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return fallback



def _database_details(db) -> dict[str, str]:
    dialect = db.bind.dialect.name.lower()
    label = 'PostgreSQL' if dialect == 'postgresql' else dialect.title()
    health = 'Healthy'
    version_text = 'Unknown'
    size_text = 'Unknown'
    name_text = str(db.bind.url.database or 'Unknown')

    try:
        db.execute(text('SELECT 1'))
    except Exception:
        health = 'Unhealthy'

    try:
        if dialect == 'postgresql':
            raw_version = db.execute(text('SELECT version()')).scalar() or ''
            version_text = str(raw_version).split(',')[0].replace('PostgreSQL ', '') or 'Unknown'
            size_text = str(db.execute(text('SELECT pg_size_pretty(pg_database_size(current_database()))')).scalar() or 'Unknown')
        elif dialect == 'sqlite':
            raw_version = db.execute(text('SELECT sqlite_version()')).scalar() or 'Unknown'
            version_text = str(raw_version)
            sqlite_path = Path(name_text)
            size_text = format_bytes(sqlite_path.stat().st_size) if sqlite_path.exists() else '0 B'
    except Exception:
        pass

    return {
        'label': label,
        'health': health,
        'version': version_text,
        'size': size_text,
        'name': name_text,
        'driver': db.bind.dialect.driver,
    }



def _redis_details() -> dict[str, str]:
    if settings.DEV_MODE:
        return {
            'health': 'Disabled in DEV_MODE',
            'version': 'Disabled in DEV_MODE',
            'memory': 'Disabled in DEV_MODE',
        }

    try:
        redis_client = get_redis()
        info = redis_client.info()
        return {
            'health': 'Healthy',
            'version': str(info.get('redis_version') or 'Unknown'),
            'memory': str(info.get('used_memory_human') or 'Unknown'),
        }
    except Exception:
        return {
            'health': 'Unavailable',
            'version': 'Unavailable',
            'memory': 'Unavailable',
        }



def _uptime_text() -> str:
    elapsed = datetime.now(timezone.utc) - APP_STARTED_AT
    return format_uptime(int(elapsed.total_seconds()))



def _system_details() -> dict[str, str]:
    uname = platform.uname()
    return {
        'os_name': uname.system or 'Unknown',
        'kernel_version': uname.release or 'Unknown',
        'kernel_build': uname.version or 'Unknown',
        'architecture': uname.machine or 'Unknown',
        'processor': uname.processor or 'Unknown',
        'hostname': uname.node or 'Unknown',
        'python': platform.python_version(),
        'cpu_count': str(os.cpu_count() or 'Unknown'),
    }



def _config_details() -> dict[str, str]:
    return {
        'mode': 'DEV_MODE' if settings.DEV_MODE else 'PRODUCTION',
        'debug': 'Enabled' if settings.DEBUG else 'Disabled',
        'download_path': settings.DOWNLOAD_PATH,
        'telegram_max_upload': f"{settings.TELEGRAM_MAX_UPLOAD_MB} MB",
        'telegram_timeout': f"{settings.TELEGRAM_REQUEST_TIMEOUT_SECONDS} seconds",
        'telegram_upload_retries': str(settings.TELEGRAM_UPLOAD_RETRIES),
        'job_timeout': f"{settings.DOWNLOAD_JOB_TIMEOUT} seconds",
        'max_retries': str(settings.MAX_RETRIES),
        'port': str(settings.PORT or 'Auto'),
    }



def _stats_message(db_stats: dict[str, str], redis_stats: dict[str, str], system_stats: dict[str, str], config_stats: dict[str, str], totals: dict[str, int]) -> str:
    lines = [
        '<b>Bot Statistics</b>',
        '',
        detail_text('Uptime', _uptime_text()),
        '',
        '<b>Database</b>',
        detail_text('Database Health', db_stats['health']),
        detail_text('Database Engine', db_stats['label']),
        detail_text('Database Version', db_stats['version']),
        detail_text('Database Size', db_stats['size']),
        detail_text('Database Name', db_stats['name']),
        detail_text('Database Driver', db_stats['driver']),
        '',
        '<b>Redis</b>',
        detail_text('Redis Health', redis_stats['health']),
        detail_text('Redis Version', redis_stats['version']),
        detail_text('Redis Memory', redis_stats['memory']),
        '',
        '<b>System</b>',
        detail_text('OS Name', system_stats['os_name']),
        detail_text('Kernel Version', system_stats['kernel_version']),
        detail_text('Kernel Build', system_stats['kernel_build']),
        detail_text('Architecture', system_stats['architecture']),
        detail_text('Processor', system_stats['processor']),
        detail_text('Hostname', system_stats['hostname']),
        detail_text('CPU Count', system_stats['cpu_count']),
        detail_text('Python Version', system_stats['python']),
        detail_text('Aiogram Version', _package_version('aiogram')),
        detail_text('SQLAlchemy Version', _package_version('sqlalchemy')),
        detail_text('yt-dlp Version', _package_version('yt-dlp')),
        detail_text('RQ Version', _package_version('rq')),
        '',
        '<b>Configuration</b>',
        detail_text('Mode', config_stats['mode']),
        detail_text('Debug', config_stats['debug']),
        detail_text('Download Path', config_stats['download_path']),
        detail_text('Telegram Max Upload', config_stats['telegram_max_upload']),
        detail_text('Telegram Timeout', config_stats['telegram_timeout']),
        detail_text('Telegram Upload Retries', config_stats['telegram_upload_retries']),
        detail_text('Job Timeout', config_stats['job_timeout']),
        detail_text('Max Retries', config_stats['max_retries']),
        detail_text('Port', config_stats['port']),
        '',
        '<b>Bot Totals</b>',
        detail_text('Users', totals['users']),
        detail_text('Groups', totals['groups']),
        detail_text('Approved Groups', totals['approved_groups']),
        detail_text('Total Downloads', totals['total_downloads']),
        detail_text('Completed Downloads', totals['completed_downloads']),
        detail_text('Failed Downloads', totals['failed_downloads']),
    ]
    return _quote_block(lines)


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
    """Show bot latency and uptime for admins only."""
    with get_db() as db:
        if not is_admin(message.from_user.id, db):
            return

    started = time.perf_counter()
    ping_message = await message.answer('<blockquote><b>Pinging...</b></blockquote>', parse_mode=ParseMode.HTML)
    latency_ms = round((time.perf_counter() - started) * 1000)

    await ping_message.edit_text(
        _quote_block([
            f'<b>Pong!</b> {latency_ms} ms',
            detail_text('Uptime', _uptime_text()),
        ]),
        parse_mode=ParseMode.HTML,
    )


@router.message(Command('stats'))
async def cmd_stats(message: Message):
    """Show detailed bot/runtime/database/system stats for admins only."""
    with get_db() as db:
        if not is_admin(message.from_user.id, db):
            return

        db_stats = _database_details(db)
        totals = {
            'users': db.query(func.count(User.id)).scalar() or 0,
            'groups': db.query(func.count(Group.id)).scalar() or 0,
            'approved_groups': db.query(func.count(Group.id)).filter(Group.is_approved.is_(True)).scalar() or 0,
            'total_downloads': db.query(func.count(Download.id)).scalar() or 0,
            'completed_downloads': db.query(func.count(Download.id)).filter(Download.status == 'completed').scalar() or 0,
            'failed_downloads': db.query(func.count(Download.id)).filter(Download.status == 'failed').scalar() or 0,
        }

    redis_stats = _redis_details()
    system_stats = _system_details()
    config_stats = _config_details()

    await message.answer(
        _stats_message(db_stats, redis_stats, system_stats, config_stats, totals),
        parse_mode=ParseMode.HTML,
    )
