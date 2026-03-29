import asyncio
import re

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message
from rq import Queue

from config import settings
from database.connection import get_db
from database.models import Download, Group, User
from utils.downloader import DownloaderError, get_video_info
from utils.formatters import detail_text, download_panel, html, panel
from utils.permissions import can_download, get_group_rank, get_rank_config
from utils.redis_client import (
    check_cooldown,
    clear_active_job,
    get_active_jobs,
    get_redis,
    register_active_job,
    set_cooldown,
)
from workers.download_worker import process_download

router = Router(name='download')
JOB_TTL_PADDING_SECONDS = 300

URL_PATTERN = re.compile(
    r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"
)



def _default_rank_config() -> dict[str, int]:
    return {
        'cooldown_seconds': 30,
        'concurrent_jobs': 1,
        'max_file_size': 100 * 1024 * 1024,
    }



def _sync_user_record(message: Message, db) -> User:
    user = db.query(User).filter(User.id == message.from_user.id).first()
    if not user:
        user = User(id=message.from_user.id)
        db.add(user)

    user.username = message.from_user.username
    user.first_name = message.from_user.first_name
    user.last_name = message.from_user.last_name
    db.flush()
    return user


@router.message(Command('download'))
async def cmd_download(message: Message):
    """Download media from URL."""
    command_parts = message.text.split(maxsplit=1)
    await handle_download(message, command_parts[1] if len(command_parts) > 1 else None)


@router.message(F.text.regexp(URL_PATTERN))
async def auto_download(message: Message):
    """Auto-download when URL is detected."""
    with get_db() as db:
        if message.chat.type in ['group', 'supergroup']:
            group = db.query(Group).filter(Group.id == message.chat.id).first()
            if not group or not group.auto_dl_enabled:
                return
        else:
            user = db.query(User).filter(User.id == message.from_user.id).first()
            if not user or not user.auto_dl_enabled:
                return

    urls = URL_PATTERN.findall(message.text)
    if urls:
        await handle_download(message, urls[0])


async def handle_download(message: Message, url: str):
    """Core download logic."""
    if not url:
        await message.answer(
            panel(
                'Download Command',
                ['Use /download followed by a supported link to start a download.'],
                footer='Example: /download https://youtube.com/watch?v=dQw4w9WgXcQ',
            ),
            parse_mode=ParseMode.HTML,
        )
        return

    with get_db() as db:
        if message.chat.type in ['group', 'supergroup']:
            group = db.query(Group).filter(Group.id == message.chat.id).first()
            if not group or not group.is_approved:
                await message.answer(
                    panel('Group Approval Required', ['Ask an admin to use /addgroup in this group first.']),
                    parse_mode=ParseMode.HTML,
                )
                return

            group_id = message.chat.id
            rank = get_group_rank(group_id, db)
        else:
            group_id = None
            rank = None

        _sync_user_record(message, db)
        user_id = message.from_user.id
        config = get_rank_config(rank) if rank else _default_rank_config()

        if check_cooldown(user_id):
            await message.answer(
                panel(
                    'Please Wait',
                    [
                        detail_text('Cooldown', f"{config['cooldown_seconds']} seconds"),
                        'Try the download again after the cooldown ends.',
                    ],
                ),
                parse_mode=ParseMode.HTML,
            )
            return

        if group_id:
            active_jobs = get_active_jobs(group_id)
            if active_jobs >= config['concurrent_jobs']:
                await message.answer(
                    panel(
                        'Download Queue Busy',
                        [
                            detail_text('Active Limit', config['concurrent_jobs']),
                            'Wait for the current downloads to finish before starting another one.',
                        ],
                    ),
                    parse_mode=ParseMode.HTML,
                )
                return

        status_msg = await message.answer(
            panel('Checking Media', ['Reading the link and preparing download details...']),
            parse_mode=ParseMode.HTML,
        )

        try:
            info = get_video_info(url)
        except DownloaderError as exc:
            await status_msg.edit_text(
                panel(
                    'Link Unavailable',
                    [detail_text('Reason', str(exc))],
                    footer='Try another supported link and send the command again.',
                ),
                parse_mode=ParseMode.HTML,
            )
            return

        if group_id:
            allowed, reason = can_download(group_id, info['filesize'], db)
            if not allowed:
                await status_msg.edit_text(
                    panel('Download Blocked', [detail_text('Reason', reason)]),
                    parse_mode=ParseMode.HTML,
                )
                return

        download = Download(
            user_id=user_id,
            group_id=group_id,
            chat_id=message.chat.id,
            request_message_id=message.message_id,
            status_message_id=status_msg.message_id,
            url=url,
            platform=info['platform'],
            file_size=info['filesize'],
            duration=info['duration'],
            status='pending',
        )
        db.add(download)
        db.commit()

        download_id = download.id
        set_cooldown(user_id, config['cooldown_seconds'])

        if settings.DEV_MODE:
            await status_msg.edit_text(
                download_panel(
                    'Download Started',
                    info,
                    footer='Working locally now. The bot will send the file here when it is ready.',
                ),
                parse_mode=ParseMode.HTML,
            )
            try:
                await asyncio.to_thread(process_download, download_id)
            except Exception:
                return
            return

        redis_conn = get_redis()
        queue = Queue('default', connection=redis_conn)

        try:
            if group_id:
                register_active_job(
                    group_id,
                    download_id,
                    settings.DOWNLOAD_JOB_TIMEOUT + JOB_TTL_PADDING_SECONDS,
                )

            queue.enqueue(
                'workers.download_worker.process_download',
                download_id,
                job_timeout=settings.DOWNLOAD_JOB_TIMEOUT,
                result_ttl=0,
            )
        except Exception as exc:
            if group_id:
                clear_active_job(group_id, download_id)

            download.status = 'failed'
            download.error_message = f'Queueing failed: {exc}'
            db.commit()
            await status_msg.edit_text(
                panel(
                    'Queue Error',
                    [detail_text('Reason', str(exc))],
                    footer='Please try the command again in a moment.',
                ),
                parse_mode=ParseMode.HTML,
            )
            return

        await status_msg.edit_text(
            download_panel(
                'Download Queued',
                info,
                footer='The bot will send the file here as soon as it is ready.',
            ),
            parse_mode=ParseMode.HTML,
        )
