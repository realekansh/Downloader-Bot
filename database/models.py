from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class RankType(PyEnum):
    FULL = "full"
    SUDO = "sudo"
    LESS = "less"


class Group(Base):
    __tablename__ = "groups"

    id = Column(BigInteger, primary_key=True)  # Telegram group ID
    title = Column(String(255), nullable=False)
    username = Column(String(255), nullable=True)
    rank = Column(Enum(RankType), default=RankType.LESS, nullable=False)
    is_approved = Column(Boolean, default=False, nullable=False)
    auto_dl_enabled = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    downloads = relationship("Download", back_populates="group")

    __table_args__ = (
        Index('idx_group_approved', 'is_approved'),
        Index('idx_group_rank', 'rank'),
    )


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True)  # Telegram user ID
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    is_admin = Column(Boolean, default=False, nullable=False)
    is_owner = Column(Boolean, default=False, nullable=False)
    auto_dl_enabled = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    downloads = relationship("Download", back_populates="user")
    admin_actions = relationship("AdminAction", back_populates="admin")

    __table_args__ = (
        Index('idx_user_admin', 'is_admin'),
        Index('idx_user_owner', 'is_owner'),
    )


class Download(Base):
    __tablename__ = "downloads"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    group_id = Column(BigInteger, ForeignKey("groups.id"), nullable=True)
    chat_id = Column(BigInteger, nullable=True)
    request_message_id = Column(Integer, nullable=True)
    status_message_id = Column(Integer, nullable=True)
    url = Column(Text, nullable=False)
    platform = Column(String(50), nullable=False)  # youtube, instagram, tiktok, twitter
    file_size = Column(BigInteger, nullable=True)  # bytes
    duration = Column(Integer, nullable=True)  # seconds
    status = Column(String(50), default="pending", nullable=False)  # pending, processing, completed, failed
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="downloads")
    group = relationship("Group", back_populates="downloads")

    __table_args__ = (
        Index('idx_download_user', 'user_id'),
        Index('idx_download_group', 'group_id'),
        Index('idx_download_chat', 'chat_id'),
        Index('idx_download_status', 'status'),
        Index('idx_download_started', 'started_at'),
    )


class AdminAction(Base):
    __tablename__ = "admin_actions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    admin_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    action_type = Column(String(100), nullable=False)  # promote, demote, add_group, set_rank, etc.
    target_id = Column(BigInteger, nullable=False)  # User or Group ID
    details = Column(Text, nullable=True)  # JSON or text description
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    admin = relationship("User", back_populates="admin_actions")

    __table_args__ = (
        Index('idx_action_admin', 'admin_id'),
        Index('idx_action_type', 'action_type'),
        Index('idx_action_timestamp', 'timestamp'),
    )


RANK_CONFIGS = {
    RankType.FULL: {
        "max_file_size": 2 * 1024 * 1024 * 1024,
        "concurrent_jobs": 5,
        "nsfw_allowed": True,
        "cooldown_seconds": 10,
    },
    RankType.SUDO: {
        "max_file_size": 500 * 1024 * 1024,
        "concurrent_jobs": 3,
        "nsfw_allowed": True,
        "cooldown_seconds": 20,
    },
    RankType.LESS: {
        "max_file_size": 100 * 1024 * 1024,
        "concurrent_jobs": 1,
        "nsfw_allowed": False,
        "cooldown_seconds": 30,
    },
}
