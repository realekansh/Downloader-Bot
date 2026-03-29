from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message
from database.connection import get_db
from database.models import User

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
        (
            "<b>Welcome to HyperTech Downloader Bot!</b>\n\n"
            "Download videos and audio from supported public links in private chats and approved groups.\n"
            "Supports platforms like YouTube, Instagram, TikTok, Facebook, and X/Twitter.\n"
            "View /help to know more!"
        ),
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Show detailed help"""
    await message.answer(
        (
            "<b>HyperTech Downloader Bot - Help Menu</b>\n\n"
            "<b>Bot Commands:</b>\n"
            "&#8226; /start - <b>Start the bot</b>\n"
            "&#8226; /download &lt;url&gt; - <b>Download media</b>\n"
            "&#8226; /info - <b>View your statistics</b>\n"
            "&#8226; /autodl - <b>Toggle auto-download</b>\n"
            "&#8226; /help - <b>View this help menu</b>\n\n"
            "<b>Support:</b> @ForgeFluxCommunity"
        ),
        parse_mode=ParseMode.HTML,
    )
