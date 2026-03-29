from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message

from database.connection import get_db
from database.models import Group, User
from utils.formatters import panel, toggle_panel

router = Router(name='auto_dl')


@router.message(Command('autodl'))
async def cmd_autodl(message: Message):
    """Toggle auto-download."""
    with get_db() as db:
        if message.chat.type in ['group', 'supergroup']:
            from utils.permissions import is_admin

            if not is_admin(message.from_user.id, db):
                await message.answer(
                    panel('Admin Access Required', ['Only bot admins can change auto-download in groups.']),
                    parse_mode=ParseMode.HTML,
                )
                return

            group = db.query(Group).filter(Group.id == message.chat.id).first()
            if not group:
                await message.answer(
                    panel('Group Setup Needed', ['Ask an admin to use /addgroup first.']),
                    parse_mode=ParseMode.HTML,
                )
                return

            group.auto_dl_enabled = not group.auto_dl_enabled
            db.commit()
            await message.answer(toggle_panel('This group', group.auto_dl_enabled), parse_mode=ParseMode.HTML)
            return

        user = db.query(User).filter(User.id == message.from_user.id).first()
        if not user:
            user = User(
                id=message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name,
            )
            db.add(user)

        user.auto_dl_enabled = not user.auto_dl_enabled
        db.commit()
        await message.answer(toggle_panel('Your account', user.auto_dl_enabled), parse_mode=ParseMode.HTML)
