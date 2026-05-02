import asyncio
import logging
import os
import sys
from datetime import datetime

sys.path.insert(0, '/app')

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import FSInputFile
from redis import Redis
from rq import Connection, Worker

from config import settings
from database.connection import get_db
from database.models import Download
from utils.downloader import DownloaderError, download_media, get_video_info
from utils.formatters import (
    clean_url,
    detail_text,
    format_bytes,
    format_duration,
    human_platform,
    media_details_message,
    panel,
)
from utils.redis_client import clear_active_job, register_active_job

logger = logging.getLogger('hypertech.worker')
JOB_TTL_PADDING_SECONDS = 300

redis_conn = Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB,
    password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
    decode_responses=False,
)



def _create_bot() -> Bot:
    return Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )



def _is_video_file(file_path: str) -> bool:
    return os.path.splitext(file_path)[1].lower() in {
        '.avi',
        '.m4v',
        '.mkv',
        '.mov',
        '.mp4',
        '.webm',
    }


async def _safe_edit_status(chat_id: int | None, message_id: int | None, text: str) -> None:
    if not chat_id or not message_id:
        return

    bot = _create_bot()
    try:
        await bot.edit_message_text(text=text, chat_id=chat_id, message_id=message_id)
    except Exception:
        logger.warning('status-update failed chat=%s message=%s', chat_id, message_id)
    finally:
        await bot.session.close()


async def _safe_delete_status(chat_id: int | None, message_id: int | None) -> None:
    if not chat_id or not message_id:
        return

    bot = _create_bot()
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        logger.warning('status-delete failed chat=%s message=%s', chat_id, message_id)
    finally:
        await bot.session.close()


async def _deliver_file(
    chat_id: int,
    source_url: str,
    platform: str,
    file_path: str,
    title: str,
    duration_seconds: int,
) -> None:
    bot = _create_bot()
    try:
        bot_me = await bot.get_me()
        bot_username = bot_me.username or ''
        bot_url = f'https://t.me/{bot_username}' if bot_username else None
        footer = '<b>Delivered by HyperTech Downloader Bot</b>'
        if bot_url:
            footer = f'<b>Delivered by <a href="{bot_url}">HyperTech Downloader Bot</a></b>'

        caption = media_details_message(
            title=title,
            platform=human_platform(platform),
            duration_seconds=duration_seconds,
            size_bytes=os.path.getsize(file_path),
            source_url=clean_url(source_url),
            footer=footer,
        )

        media = FSInputFile(file_path)
        if _is_video_file(file_path):
            await bot.send_video(
                chat_id=chat_id,
                video=media,
                caption=caption,
                supports_streaming=True,
            )
        else:
            await bot.send_document(
                chat_id=chat_id,
                document=media,
                caption=caption,
            )
    finally:
        await bot.session.close()



def _fallback_title(file_path: str) -> str:
    return os.path.splitext(os.path.basename(file_path))[0].replace('_', ' ')



def process_download(download_id: int):
    logger.info('download=%s stage=processing', download_id)
    file_path = None

    with get_db() as db:
        download = db.query(Download).filter(Download.id == download_id).first()
        if not download:
            logger.error('download=%s stage=missing', download_id)
            return

        group_id = download.group_id
        chat_id = download.chat_id
        status_message_id = download.status_message_id
        source_url = download.url
        platform = download.platform
        title = 'Downloaded Media'
        duration_seconds = download.duration or 0

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

            try:
                metadata = get_video_info(source_url)
                title = metadata.get('title') or title
                duration_seconds = metadata.get('duration') or duration_seconds
            except DownloaderError:
                logger.warning('download=%s metadata-refresh=failed', download_id)

            file_path = download_media(source_url, settings.DOWNLOAD_PATH)
            download.file_size = os.path.getsize(file_path)

            if not chat_id:
                raise RuntimeError('Missing chat_id for queued download delivery.')

            asyncio.run(_deliver_file(chat_id, source_url, platform, file_path, title or _fallback_title(file_path), duration_seconds))

            download.status = 'completed'
            download.completed_at = datetime.utcnow()
            db.commit()

            asyncio.run(_safe_delete_status(chat_id, status_message_id))
            logger.info('download=%s stage=completed file=%s', download_id, os.path.basename(file_path))
            return file_path

        except Exception as exc:
            logger.exception('download=%s stage=failed', download_id)
            error_message = str(exc)
            if 'Request Entity Too Large' in error_message or 'too large for Telegram bots to send' in error_message:
                error_message = f'The file ended up larger than Telegram bots can upload. Try a shorter or lower-quality video (max: {settings.TELEGRAM_MAX_UPLOAD_MB}MB).'

            download.status = 'failed'
            download.error_message = error_message
            db.commit()
            asyncio.run(
                _safe_edit_status(
                    chat_id,
                    status_message_id,
                    panel(
                        'Download Failed',
                        [detail_text('Reason', error_message)],
                        footer='Please try a shorter link or a lower-quality source.',
                    ),
                )
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


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] %(levelname)-7s %(name)s | %(message)s',
        datefmt='%H:%M:%S',
        force=True,
    )
    with Connection(redis_conn):
        worker = Worker(['default'])
        worker.work()
