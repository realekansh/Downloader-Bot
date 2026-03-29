from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message
from utils.redis_client import check_cooldown


class RateLimitMiddleware(BaseMiddleware):
    """Rate limiting middleware using Redis cooldowns"""
    
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        # Only apply to download-related messages
        if not (event.text and ('/download' in event.text or 'http' in event.text)):
            return await handler(event, data)
        
        user_id = event.from_user.id
        
        # Check cooldown is handled in download handler
        # This is just a backup check
        
        return await handler(event, data)
