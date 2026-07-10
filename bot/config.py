"""
Central configuration loaded from environment variables.

Every module in the project imports ``from config import settings``.
Uses pydantic-settings so values can come from a ``.env`` file or real
environment variables without any manual parsing.
"""

import os
from pathlib import Path
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings

BOT_ROOT = Path(__file__).resolve().parent


class Settings(BaseSettings):
    # ── Telegram ──────────────────────────────────────────────
    BOT_TOKEN: str = ""

    # ── Owner bootstrap ───────────────────────────────────────
    # Telegram user ID that is auto-promoted to owner on first run.
    OWNER_ID: int = 0

    # ── Database ──────────────────────────────────────────────
    DATABASE_URL: str = f"sqlite:///{BOT_ROOT / 'data' / 'bot.db'}"

    # ── Redis ─────────────────────────────────────────────────
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None

    # ── Downloads ─────────────────────────────────────────────
    DOWNLOAD_PATH: str = str(BOT_ROOT / "downloads")
    DOWNLOAD_JOB_TIMEOUT: int = 600  # seconds
    MAX_RETRIES: int = 3

    # ── Runtime flags ─────────────────────────────────────────
    DEV_MODE: bool = False
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # ── Telegram API limits ───────────────────────────────────
    # Maximum file size the bot can send via Telegram Bot API (50 MB).
    TELEGRAM_MAX_FILE_SIZE: int = 50 * 1024 * 1024

    @field_validator("BOT_TOKEN")
    @classmethod
    def _token_must_be_set(cls, v: str) -> str:
        if not v:
            raise ValueError(
                "BOT_TOKEN is required. Set it in .env or as an environment variable."
            )
        return v

    model_config = {
        "env_file": str(BOT_ROOT / ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
