from html import escape

from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message, User as TelegramUser
from sqlalchemy import func
from sqlalchemy.orm import Session

from database.connection import get_db
from database.models import AdminAction, Group, RankType, User
from utils.permissions import is_admin, is_owner

router = Router(name="admin")


BULLET = "&#8226;"
GROUP_CHAT_TYPES = {"group", "supergroup"}
ANONYMOUS_ADMIN_ERROR = "Send this command from your personal account. Anonymous admin or channel messages are not supported."


def get_actor_id(message: Message) -> int | None:
    return message.from_user.id if message.from_user else None


def sync_user_record(db: Session, telegram_user: TelegramUser) -> User:
    """Ensure we have a local user row for a Telegram user."""
    user = db.query(User).filter(User.id == telegram_user.id).first()
    if not user:
        user = User(id=telegram_user.id)
        db.add(user)

    user.username = telegram_user.username
    user.first_name = telegram_user.first_name
    user.last_name = telegram_user.last_name
    db.flush()
    return user


def resolve_target_user(message: Message, db: Session) -> tuple[int | None, str | None]:
    """Resolve a promotion target from reply, user ID, or known username."""
    if message.reply_to_message and message.reply_to_message.from_user:
        user = sync_user_record(db, message.reply_to_message.from_user)
        return user.id, None

    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        return None, (
            "Usage:\n"
            f"{BULLET} Reply to user: /promote or /demote\n"
            f"{BULLET} By user ID: /promote 123456789\n"
            f"{BULLET} By username: /promote @username"
        )

    target = args[1].strip()
    if target.isdigit():
        return int(target), None

    if target.startswith('@'):
        target = target[1:]

    user = db.query(User).filter(func.lower(User.username) == target.lower()).first()
    if user:
        return user.id, None

    return None, "User not found. Use a reply or a numeric user ID."


async def resolve_group_target(message: Message, db: Session, target_ref: str | None) -> tuple[Group | None, str | None]:
    """Resolve a group from the current chat, DB lookup, or Telegram chat lookup."""
    if not target_ref:
        if message.chat.type in GROUP_CHAT_TYPES:
            group = db.query(Group).filter(Group.id == message.chat.id).first()
            if not group:
                group = Group(
                    id=message.chat.id,
                    title=message.chat.title,
                    username=message.chat.username,
                )
                db.add(group)
                db.flush()
            return group, None
        return None, "This command needs a group target. Use it inside a group or pass a group ID/@username."

    lookup_value: int | str = target_ref
    group = None

    if target_ref.lstrip('-').isdigit():
        lookup_value = int(target_ref)
        group = db.query(Group).filter(Group.id == lookup_value).first()
    else:
        username = target_ref[1:] if target_ref.startswith('@') else target_ref
        group = db.query(Group).filter(func.lower(Group.username) == username.lower()).first()
        lookup_value = f"@{username}"

    if group:
        return group, None

    try:
        chat = await message.bot.get_chat(lookup_value)
    except Exception:
        return None, "Group not found. Use a valid group ID or @username."

    if chat.type not in GROUP_CHAT_TYPES:
        return None, "Target must be a group or supergroup."

    group = db.query(Group).filter(Group.id == chat.id).first()
    if not group:
        group = Group(id=chat.id, title=chat.title or str(chat.id), username=chat.username)
        db.add(group)
    else:
        group.title = chat.title or group.title
        group.username = chat.username
    db.flush()
    return group, None


def build_admin_help() -> str:
    return (
        "<b>Admin Commands:</b>\n"
        f"{BULLET} /promote &lt;user_id|@username|reply&gt; - <b>Promote to admin</b>\n"
        f"{BULLET} /demote &lt;user_id|@username|reply&gt; - <b>Demote admin</b>\n"
        f"{BULLET} /addgroup - <b>Approve group</b>\n"
        f"{BULLET} /rmgroup - <b>Remove group approval</b>\n"
        f"{BULLET} /setrank &lt;full|sudo|less&gt; - <b>Set group rank</b>\n\n"
        "<b>Group Ranks:</b>\n"
        f"{BULLET} Full - <b>No restrictions</b>\n"
        f"{BULLET} Sudo - <b>100MB limit, 10s cooldown</b>\n"
        f"{BULLET} Less - <b>50MB limit, 30s cooldown</b>"
    )


@router.message(Command("adminhelp"))
async def cmd_admin_help(message: Message):
    """Show hidden admin commands."""
    actor_id = get_actor_id(message)
    if actor_id is None:
        await message.answer(ANONYMOUS_ADMIN_ERROR)
        return

    with get_db() as db:
        if not is_admin(actor_id, db):
            return

    await message.answer(build_admin_help(), parse_mode=ParseMode.HTML)


@router.message(Command("promote"))
async def cmd_promote(message: Message):
    """Promote user to admin - Owner only."""
    actor_id = get_actor_id(message)
    if actor_id is None:
        await message.answer(ANONYMOUS_ADMIN_ERROR)
        return

    with get_db() as db:
        if not is_owner(actor_id, db):
            return

        target_id, error_message = resolve_target_user(message, db)
        if error_message:
            await message.answer(error_message, parse_mode=ParseMode.HTML)
            return

        target_user = db.query(User).filter(User.id == target_id).first()
        if not target_user:
            target_user = User(id=target_id, is_admin=True)
            db.add(target_user)
            db.commit()
            response_text = f"User <b>{target_id}</b> promoted to admin."
            await message.answer(response_text, parse_mode=ParseMode.HTML)
            return

        if target_user.is_admin:
            await message.answer("User is already an admin.")
            return

        target_user.is_admin = True
        display_name = escape(target_user.first_name or target_user.username or str(target_id))

        action = AdminAction(
            admin_id=actor_id,
            action_type="promote",
            target_id=target_id,
            details=f"Promoted user {target_id} to admin",
        )
        db.add(action)
        db.commit()
        response_text = f"User <b>{display_name}</b> promoted to admin."

    await message.answer(response_text, parse_mode=ParseMode.HTML)


@router.message(Command("demote"))
async def cmd_demote(message: Message):
    """Demote admin - Owner only."""
    actor_id = get_actor_id(message)
    if actor_id is None:
        await message.answer(ANONYMOUS_ADMIN_ERROR)
        return

    with get_db() as db:
        if not is_owner(actor_id, db):
            return

        target_id, error_message = resolve_target_user(message, db)
        if error_message:
            await message.answer(error_message, parse_mode=ParseMode.HTML)
            return

        target_user = db.query(User).filter(User.id == target_id).first()
        if not target_user or not target_user.is_admin:
            await message.answer("User is not an admin.")
            return

        target_user.is_admin = False
        display_name = escape(target_user.first_name or target_user.username or str(target_id))

        action = AdminAction(
            admin_id=actor_id,
            action_type="demote",
            target_id=target_id,
            details=f"Demoted admin {target_id}",
        )
        db.add(action)
        db.commit()
        response_text = f"User <b>{display_name}</b> demoted from admin."

    await message.answer(response_text, parse_mode=ParseMode.HTML)


@router.message(Command(commands=["addgroup", "add_group"]))
async def cmd_add_group(message: Message):
    """Approve group - Admin only."""
    actor_id = get_actor_id(message)
    if actor_id is None:
        await message.answer(ANONYMOUS_ADMIN_ERROR)
        return

    with get_db() as db:
        if not is_admin(actor_id, db):
            return

        args = message.text.split(maxsplit=1)
        target_ref = args[1].strip() if len(args) > 1 else None
        group, error_message = await resolve_group_target(message, db, target_ref)
        if error_message:
            await message.answer(error_message)
            return

        if group.is_approved:
            await message.answer("Group is already approved.")
            return

        group.is_approved = True
        if message.chat.type in GROUP_CHAT_TYPES and group.id == message.chat.id:
            group.title = message.chat.title
            group.username = message.chat.username

        group_title = escape(group.title or str(group.id))
        action = AdminAction(
            admin_id=actor_id,
            action_type="add_group",
            target_id=group.id,
            details=f"Approved group {group.title}",
        )
        db.add(action)
        db.commit()
        response_text = f"Group approved: <b>{group_title}</b>"

    await message.answer(response_text, parse_mode=ParseMode.HTML)


@router.message(Command(commands=["rmgroup", "remove_group"]))
async def cmd_remove_group(message: Message):
    """Remove group approval - Admin only."""
    actor_id = get_actor_id(message)
    if actor_id is None:
        await message.answer(ANONYMOUS_ADMIN_ERROR)
        return

    with get_db() as db:
        if not is_admin(actor_id, db):
            return

        args = message.text.split(maxsplit=1)
        target_ref = args[1].strip() if len(args) > 1 else None
        group, error_message = await resolve_group_target(message, db, target_ref)
        if error_message:
            await message.answer(error_message)
            return

        if not group.is_approved:
            await message.answer("Group is already unapproved.")
            return

        group.is_approved = False
        group_title = escape(group.title or str(group.id))

        action = AdminAction(
            admin_id=actor_id,
            action_type="remove_group",
            target_id=group.id,
            details=f"Removed approval for group {group.title}",
        )
        db.add(action)
        db.commit()
        response_text = f"Group approval removed: <b>{group_title}</b>"

    await message.answer(response_text, parse_mode=ParseMode.HTML)


@router.message(Command(commands=["setrank", "set_rank"]))
async def cmd_set_rank(message: Message):
    """Set group rank - Admin only."""
    actor_id = get_actor_id(message)
    if actor_id is None:
        await message.answer(ANONYMOUS_ADMIN_ERROR)
        return

    with get_db() as db:
        if not is_admin(actor_id, db):
            return

        parts = message.text.split()
        if len(parts) < 2:
            await message.answer(
                "Usage: /setrank &lt;full|sudo|less&gt; or /setrank &lt;group_id|@username&gt; &lt;full|sudo|less&gt;",
                parse_mode=ParseMode.HTML,
            )
            return

        if len(parts) == 2 and message.chat.type in GROUP_CHAT_TYPES:
            target_ref = None
            rank_str = parts[1].lower()
        elif len(parts) >= 3:
            target_ref = parts[1]
            rank_str = parts[2].lower()
        else:
            await message.answer(
                "Usage: /setrank &lt;full|sudo|less&gt; or /setrank &lt;group_id|@username&gt; &lt;full|sudo|less&gt;",
                parse_mode=ParseMode.HTML,
            )
            return

        if rank_str not in ["full", "sudo", "less"]:
            await message.answer("Invalid rank. Choose: full, sudo, or less")
            return

        group, error_message = await resolve_group_target(message, db, target_ref)
        if error_message:
            await message.answer(error_message)
            return

        group.rank = RankType[rank_str.upper()]
        group_title = escape(group.title or str(group.id))

        action = AdminAction(
            admin_id=actor_id,
            action_type="set_rank",
            target_id=group.id,
            details=f"Set rank to {rank_str} for group {group.title}",
        )
        db.add(action)
        db.commit()
        response_text = f"Group rank for <b>{group_title}</b> set to <b>{rank_str.title()}</b>"

    await message.answer(response_text, parse_mode=ParseMode.HTML)
