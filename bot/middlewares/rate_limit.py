import logging
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.enums import ParseMode
from aiogram.types import Message

from utils.formatters import panel
from utils.redis_client import check_cooldown

logger = logging.getLogger("hypertech.ratelimit")


class RateLimitMiddleware(BaseMiddleware):
    """Rate limiting middleware using Redis cooldowns.

    Applied at the middleware level as a safety net. The download handler
    also checks cooldowns with rank-specific timing, but this catches
    auto-download URL messages that bypass the /download command.
    """

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        # Only rate-limit messages that contain URLs (potential downloads)
        if not event.text or 'http' not in event.text:
            return await handler(event, data)

        # Skip if no user (channel posts, etc.)
        if not event.from_user:
            return await handler(event, data)

        user_id = event.from_user.id

        # Commands handle their own cooldown messaging with rank details,
        # so only block auto-download (non-command) URL messages here.
        if event.text.startswith('/'):
            return await handler(event, data)

        if check_cooldown(user_id):
            logger.debug('rate-limited user=%s', user_id)
            # Silently drop auto-download attempts during cooldown
            # (no message to avoid spamming the chat)
            return

        return await handler(event, data)
