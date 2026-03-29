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
from utils.downloader import download_media
from utils.formatters import clean_url, detail_text, human_platform, link_detail, panel
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


async def _deliver_file(chat_id: int, source_url: str, platform: str, file_path: str) -> None:
    caption = panel(
        'Download Ready',
        [
            detail_text('Platform', human_platform(platform)),
            link_detail('Source', clean_url(source_url), 'Open Source Link'),
        ],
        footer='Delivered by HyperTech Downloader Bot.',
    )

    bot = _create_bot()
    try:
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

            asyncio.run(_deliver_file(chat_id, source_url, platform, file_path))

            download.status = 'completed'
            download.completed_at = datetime.utcnow()
            db.commit()

            asyncio.run(
                _safe_edit_status(
                    chat_id,
                    status_message_id,
                    panel('Download Complete', ['Your file has been sent below.']),
                )
            )
            logger.info('download=%s stage=completed file=%s', download_id, os.path.basename(file_path))
            return file_path

        except Exception as exc:
            logger.exception('download=%s stage=failed', download_id)
            download.status = 'failed'
            download.error_message = str(exc)
            db.commit()
            asyncio.run(
                _safe_edit_status(
                    chat_id,
                    status_message_id,
                    panel(
                        'Download Failed',
                        [detail_text('Reason', str(exc))],
                        footer='Please try the link again in a moment.',
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
