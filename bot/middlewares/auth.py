from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.enums import ParseMode
from aiogram.types import Message

from database.connection import get_db
from database.models import Group, User
from utils.formatters import panel

PUBLIC_COMMANDS = {"/start", "/help"}
ADMIN_COMMANDS = {
    "/adminhelp",
    "/promote",
    "/demote",
    "/addgroup",
    "/add_group",
    "/rmgroup",
    "/remove_group",
    "/setrank",
    "/set_rank",
}


class GroupApprovalMiddleware(BaseMiddleware):
    """Check if group is approved before processing commands."""

    @staticmethod
    def _extract_command(message: Message) -> str | None:
        if not message.text or not message.text.startswith("/"):
            return None
        command = message.text.split(maxsplit=1)[0]
        return command.split("@", maxsplit=1)[0].lower()

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        if event.chat.type not in ["group", "supergroup"]:
            return await handler(event, data)

        command = self._extract_command(event)
        if command in PUBLIC_COMMANDS or command in ADMIN_COMMANDS:
            return await handler(event, data)

        with get_db() as db:
            if event.from_user:
                user = db.query(User).filter(User.id == event.from_user.id).first()
                if user and (user.is_admin or user.is_owner):
                    return await handler(event, data)

            group = db.query(Group).filter(Group.id == event.chat.id).first()
            if not group or not group.is_approved:
                await event.answer(
                    panel(
                        'Group Approval Required',
                        ['Ask an admin to use /addgroup in this group before downloading.'],
                    ),
                    parse_mode=ParseMode.HTML,
                )
                return

        return await handler(event, data)
