from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message

from database.connection import get_db
from database.models import User
from utils.formatters import panel

router = Router(name="start")


@router.message(Command("start"))
async def cmd_start(message: Message):
    """Welcome message"""
    with get_db() as db:
        user = db.query(User).filter(User.id == message.from_user.id).first()
        if not user:
            user = User(
                id=message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name,
            )
            db.add(user)
            db.commit()

    await message.answer(
        panel(
            'Welcome to HyperTech Downloader Bot!',
            [
                'Download videos and audio from supported public links in private chats and approved groups.',
                'Supports platforms like YouTube, Instagram, TikTok, Facebook, and X/Twitter.',
                'View /help to know more!',
            ],
        ),
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Show detailed help"""
    await message.answer(
        panel(
            'HyperTech Downloader Bot - Help Menu',
            [
                '<b>Bot Commands:</b>',
                '? /start - <b>Start the bot</b>',
                '? /download &lt;url&gt; - <b>Download media</b>',
                '? /info - <b>View your information</b>',
                '? /autodl - <b>Toggle auto-download</b>',
                '? /ping - <b>Check bot latency and uptime</b>',
                '? /stats - <b>View bot stats and versions</b>',
                '? /help - <b>View this help menu</b>',
                '',
                '<b>Support:</b> @ForgeFluxCommunity',
            ],
        ),
        parse_mode=ParseMode.HTML,
    )
