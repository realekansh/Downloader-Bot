from typing import Optional

from config import settings
from database.models import User, Group, RankType, RANK_CONFIGS
from database.connection import get_db
from sqlalchemy.orm import Session

TELEGRAM_SAFE_UPLOAD_BYTES = settings.TELEGRAM_MAX_UPLOAD_MB * 1024 * 1024


def get_user(user_id: int, db: Session) -> Optional[User]:
    """Get user from database"""
    return db.query(User).filter(User.id == user_id).first()


def get_group(group_id: int, db: Session) -> Optional[Group]:
    """Get group from database"""
    return db.query(Group).filter(Group.id == group_id).first()


def is_admin(user_id: int, db: Session) -> bool:
    """Check if user is admin"""
    user = get_user(user_id, db)
    return user and (user.is_admin or user.is_owner)


def is_owner(user_id: int, db: Session) -> bool:
    """Check if user is owner"""
    user = get_user(user_id, db)
    return user and user.is_owner


def is_group_approved(group_id: int, db: Session) -> bool:
    """Check if group is approved"""
    group = get_group(group_id, db)
    return group and group.is_approved


def get_rank_config(rank: RankType) -> dict:
    """Get configuration for rank"""
    return RANK_CONFIGS.get(rank, RANK_CONFIGS[RankType.LESS])


def get_group_rank(group_id: int, db: Session) -> RankType:
    """Get group's rank"""
    group = get_group(group_id, db)
    return group.rank if group else RankType.LESS


def can_download(group_id: int, filesize: int, db: Session) -> tuple[bool, str]:
    """
    Check if download is allowed for group
    Returns: (allowed: bool, reason: str)
    """
    group = get_group(group_id, db)
    if not group:
        return False, "Group not found"
    
    if not group.is_approved:
        return False, "Group is not approved"
    
    config = get_rank_config(group.rank)
    max_allowed_size = min(config['max_file_size'], TELEGRAM_SAFE_UPLOAD_BYTES)

    if filesize > max_allowed_size:
        return False, f"File too large (max: {max_allowed_size // (1024*1024)}MB)"

    return True, "OK"
