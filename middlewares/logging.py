import logging
import re
from urllib.parse import urlsplit, urlunsplit
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message

logger = logging.getLogger('hypertech.telegram')
URL_PATTERN = re.compile(r'https?://\S+')



def _clean_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, '', ''))



def _summarize_text(text: str | None) -> str:
    if not text:
        return 'message=no-text'

    text = text.strip()
    command = text.split(maxsplit=1)[0] if text.startswith('/') else None
    url_match = URL_PATTERN.search(text)
    safe_url = _clean_url(url_match.group(0)) if url_match else None

    if command and safe_url:
        return f'command={command} url={safe_url}'
    if command and len(text.split(maxsplit=1)) > 1:
        args = text.split(maxsplit=1)[1][:48]
        return f'command={command} args={args}'
    if command:
        return f'command={command}'
    if safe_url:
        return f'url={safe_url}'
    return f'text={text[:60]}'


class LoggingMiddleware(BaseMiddleware):
    """Log incoming messages in a cleaner format."""

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        sender = event.from_user.id if event.from_user else f'sender_chat:{getattr(event.sender_chat, "id", "unknown")}'
        logger.info('chat=%s sender=%s %s', event.chat.id, sender, _summarize_text(event.text))
        return await handler(event, data)
