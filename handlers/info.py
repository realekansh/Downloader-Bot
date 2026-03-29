from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message

from database.connection import get_db
from database.models import Group, User
from utils.formatters import format_group_info, format_user_info, panel

router = Router(name='info')


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
