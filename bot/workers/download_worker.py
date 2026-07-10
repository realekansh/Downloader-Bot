import asyncio
import logging
import os
import sys
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# Resolve bot root dynamically instead of hard-coding /app
_BOT_ROOT = str(Path(__file__).resolve().parents[1])
if _BOT_ROOT not in sys.path:
    sys.path.insert(0, _BOT_ROOT)

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import FSInputFile

from config import settings
from database.connection import get_db
from database.models import Download
from utils.downloader import download_media, DownloaderError
from utils.formatters import clean_url, detail_text, format_bytes, human_platform, link_detail, panel
from utils.redis_client import clear_active_job, register_active_job

logger = logging.getLogger('hypertech.worker')
JOB_TTL_PADDING_SECONDS = 300

# Telegram Bot API limits
TELEGRAM_MAX_FILE_SIZE = getattr(settings, 'TELEGRAM_MAX_FILE_SIZE', 50 * 1024 * 1024)

VIDEO_EXTENSIONS = {
    '.avi',
    '.m4v',
    '.mkv',
    '.mov',
    '.mp4',
    '.webm',
}


def _create_bot() -> Bot:
    return Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def _is_video_file(file_path: str) -> bool:
    return os.path.splitext(file_path)[1].lower() in VIDEO_EXTENSIONS


def _get_video_metadata(file_path: str) -> dict:
    try:
        cmd = [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,duration",
            "-of", "json", file_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        data = json.loads(result.stdout)
        stream = data.get("streams", [{}])[0]
        return {
            "width": int(stream.get("width", 0)),
            "height": int(stream.get("height", 0)),
            "duration": int(float(stream.get("duration", 0)))
        }
    except Exception:
        return {"width": 0, "height": 0, "duration": 0}


def _run_async(coro):
    """Run an async coroutine safely from sync context.

    Handles the case where asyncio.run() has already been called (and closed
    its event loop) by creating a fresh loop.  This is needed because the RQ
    worker calls process_download synchronously, and we may need to run
    multiple async operations (edit status, deliver file, etc.) in sequence.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("loop closed")
        if loop.is_running():
            # We're already inside an event loop (e.g. DEV_MODE asyncio.to_thread)
            # Create a new loop in a thread-safe way
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


async def _safe_edit_status(bot: Bot, chat_id: int | None, message_id: int | None, text: str) -> None:
    """Edit a status message, silently ignoring errors (message deleted, etc.)."""
    if not chat_id or not message_id:
        return

    try:
        await bot.edit_message_text(text=text, chat_id=chat_id, message_id=message_id)
    except Exception:
        logger.warning('status-update failed chat=%s message=%s', chat_id, message_id)


async def _deliver_file(bot: Bot, chat_id: int, source_url: str, platform: str, file_path: str, duration: int | None = None) -> None:
    """Send the downloaded file to the Telegram chat."""
    # Check file size before attempting to send
    file_size = os.path.getsize(file_path)
    if file_size > TELEGRAM_MAX_FILE_SIZE:
        raise DownloaderError(
            f"File too large for Telegram ({format_bytes(file_size)}). "
            f"Telegram allows up to {format_bytes(TELEGRAM_MAX_FILE_SIZE)}."
        )

    vid_duration = duration or 0
    vid_width = 0
    vid_height = 0

    if _is_video_file(file_path):
        meta = _get_video_metadata(file_path)
        vid_duration = meta["duration"] or vid_duration
        vid_width = meta["width"]
        vid_height = meta["height"]

    caption = panel(
        'Download Ready',
        [
            detail_text('Platform', human_platform(platform)),
            detail_text('Size', format_bytes(file_size)),
            detail_text('Duration', f"{vid_duration}s" if vid_duration else "Unknown"),
            link_detail('Source', clean_url(source_url), 'Link'),
        ],
        footer='Delivered by HyperTech Downloader Bot.',
    )

    media = FSInputFile(file_path)
    if _is_video_file(file_path):
        await bot.send_video(
            chat_id=chat_id,
            video=media,
            caption=caption,
            duration=vid_duration,
            width=vid_width,
            height=vid_height,
            supports_streaming=True,
        )
    else:
        await bot.send_document(
            chat_id=chat_id,
            document=media,
            caption=caption,
        )


async def _process_download_async(download_id: int) -> str | None:
    """Core async download logic; returns file path on success."""
    bot = _create_bot()
    file_path = None

    try:
        with get_db() as db:
            download = db.query(Download).filter(Download.id == download_id).first()
            if not download:
                logger.error('download=%s stage=missing', download_id)
                return None

            group_id = download.group_id
            chat_id = download.chat_id
            status_message_id = download.status_message_id
            source_url = download.url
            platform = download.platform
            duration = download.duration

            try:
                if group_id:
                    register_active_job(
                        group_id,
                        download_id,
                        settings.DOWNLOAD_JOB_TIMEOUT + JOB_TTL_PADDING_SECONDS,
                    )

                download.status = 'processing'
                download.error_message = None
                db.commit()

                file_path = download_media(source_url, settings.DOWNLOAD_PATH)

                if not chat_id:
                    raise RuntimeError('Missing chat_id for queued download delivery.')

                await _deliver_file(bot, chat_id, source_url, platform, file_path, duration)

                download.status = 'completed'
                download.completed_at = datetime.now(timezone.utc)
                db.commit()

                await _safe_edit_status(
                    bot,
                    chat_id,
                    status_message_id,
                    panel('Download Complete', ['Your file has been sent below.']),
                )
                logger.info('download=%s stage=completed file=%s', download_id, os.path.basename(file_path))
                return file_path

            except Exception as exc:
                logger.exception('download=%s stage=failed', download_id)
                download.status = 'failed'
                download.error_message = str(exc)[:500]
                db.commit()
                await _safe_edit_status(
                    bot,
                    chat_id,
                    status_message_id,
                    panel(
                        'Download Failed',
                        [detail_text('Reason', str(exc))],
                        footer='Please try the link again in a moment.',
                    ),
                )
                raise
            finally:
                if group_id:
                    clear_active_job(group_id, download_id)

                if file_path and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except OSError:
                        logger.warning('download=%s cleanup=failed file=%s', download_id, file_path)
    finally:
        await bot.session.close()


def process_download(download_id: int):
    """Entry point called by RQ worker or DEV_MODE asyncio.to_thread."""
    logger.info('download=%s stage=processing', download_id)
    return _run_async(_process_download_async(download_id))


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] %(levelname)-7s %(name)s | %(message)s',
        datefmt='%H:%M:%S',
        force=True,
    )

    from redis import Redis
    from rq import Connection, Worker

    redis_conn = Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
        decode_responses=False,
    )

    with Connection(redis_conn):
        worker = Worker(['default'])
        worker.work()
