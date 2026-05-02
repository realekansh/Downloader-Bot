from datetime import datetime
from html import escape
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import func
from sqlalchemy.orm import Session

from database.models import Download, Group, RankType, User

PLATFORM_NAMES = {
    'facebook': 'Facebook',
    'instagram': 'Instagram',
    'tiktok': 'TikTok',
    'twitter': 'X/Twitter',
    'x': 'X/Twitter',
    'youtube': 'YouTube',
}


def html(value: object | None, fallback: str = 'N/A') -> str:
    if value is None:
        return escape(fallback)

    text = str(value).strip()
    if not text:
        text = fallback
    return escape(text)



def clean_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, '', ''))



def human_platform(platform: str | None) -> str:
    if not platform:
        return 'Unknown'
    return PLATFORM_NAMES.get(platform.lower(), platform.title())



def detail(label: str, value: str) -> str:
    return f"<b>{escape(label)}:</b> {value}"



def detail_text(label: str, value: object | None, fallback: str = 'N/A') -> str:
    return detail(label, html(value, fallback=fallback))



def link_detail(label: str, url: str, text: str = 'Open Link') -> str:
    safe_url = escape(url, quote=True)
    return detail(label, f'<a href="{safe_url}">{escape(text)}</a>')



def panel(title: str, lines: list[str] | None = None, footer: str | None = None) -> str:
    parts = [f"<b>{escape(title)}</b>"]
    clean_lines = [line for line in (lines or []) if line is not None]

    if clean_lines:
        parts.append('')
        parts.extend(clean_lines)

    if footer:
        parts.append('')
        parts.append(footer)

    return '\n'.join(parts)



def note(title: str, body: str, footer: str | None = None) -> str:
    return panel(title, [html(body)], footer=footer)



def media_details_message(
    title: str,
    platform: str | None,
    duration_seconds: int | None,
    size_bytes: int | None,
    source_url: str | None = None,
    footer: str | None = None,
) -> str:
    lines = [
        f"<b>{html(title, fallback='Untitled media')}</b>",
        '',
        detail_text('Platform', human_platform(platform)),
        detail_text('Duration', format_duration(duration_seconds or 0)),
        detail_text('Size', format_bytes(size_bytes or 0)),
    ]

    if source_url:
        lines.append(link_detail('Source', clean_url(source_url), 'Open Source Link'))

    if footer:
        lines.append('')
        lines.append(footer)

    return '\n'.join(lines)



def download_panel(info: dict, footer: str | None = None, source_url: str | None = None) -> str:
    return media_details_message(
        title=info.get('title') or 'Untitled media',
        platform=info.get('platform'),
        duration_seconds=info.get('duration', 0),
        size_bytes=info.get('filesize', 0),
        source_url=source_url,
        footer=footer,
    )



def toggle_panel(scope: str, enabled: bool) -> str:
    return panel(
        'Auto-Download Updated',
        [
            detail_text('Scope', scope),
            detail_text('Status', 'Enabled' if enabled else 'Disabled'),
        ],
        footer='New supported links will follow this setting automatically.',
    )



def format_user_info(user: User, db: Session) -> str:
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    downloads_today = db.query(func.count(Download.id), func.sum(Download.file_size)).filter(
        Download.user_id == user.id,
        Download.started_at >= today_start,
        Download.status == 'completed',
    ).first()

    count = downloads_today[0] or 0
    total_size = downloads_today[1] or 0

    last_download = db.query(Download).filter(
        Download.user_id == user.id,
        Download.status == 'completed',
    ).order_by(Download.completed_at.desc()).first()

    last_time = (
        last_download.completed_at.strftime('%Y-%m-%d %H:%M UTC')
        if (last_download and last_download.completed_at)
        else 'Never'
    )
    full_name = ' '.join(part for part in [user.first_name, user.last_name] if part) or 'N/A'
    username = f"@{escape(user.username)}" if user.username else 'N/A'
    role = 'Owner' if user.is_owner else 'Admin' if user.is_admin else 'User'
    auto_download = 'Enabled' if user.auto_dl_enabled else 'Disabled'

    return panel(
        'User Information',
        [
            detail_text('Name', full_name),
            detail('Username', username),
            detail_text('ID', user.id),
            link_detail('Profile Link', f'tg://user?id={user.id}', 'Open Profile'),
            '',
            detail_text('Role', role),
            detail_text('Auto Download', auto_download),
            '',
            detail_text('Downloads Today', count),
            detail_text('Total Size Today', format_bytes(total_size)),
            detail_text('Last Download', last_time),
        ],
    )



def format_group_info(group: Group, db: Session) -> str:
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    downloads_today = db.query(func.count(Download.id), func.sum(Download.file_size)).filter(
        Download.group_id == group.id,
        Download.started_at >= today_start,
        Download.status == 'completed',
    ).first()

    count = downloads_today[0] or 0
    total_size = downloads_today[1] or 0

    last_download = db.query(Download).filter(
        Download.group_id == group.id,
        Download.status == 'completed',
    ).order_by(Download.completed_at.desc()).first()

    last_time = (
        last_download.completed_at.strftime('%Y-%m-%d %H:%M UTC')
        if (last_download and last_download.completed_at)
        else 'Never'
    )
    rank_name = group.rank.value.title() if isinstance(group.rank, RankType) else str(group.rank).title()
    status = 'Approved' if group.is_approved else 'Pending'
    auto_download = 'Enabled' if group.auto_dl_enabled else 'Disabled'
    username = f"@{escape(group.username)}" if group.username else 'N/A'

    return panel(
        'Group Information',
        [
            detail_text('Title', group.title or 'N/A'),
            detail('Username', username),
            detail_text('ID', group.id),
            '',
            detail_text('Rank', rank_name),
            detail_text('Status', status),
            detail_text('Auto Download', auto_download),
            '',
            detail_text('Downloads Today', count),
            detail_text('Total Size Today', format_bytes(total_size)),
            detail_text('Last Download', last_time),
        ],
    )



def format_bytes(bytes_size: int) -> str:
    if bytes_size <= 0:
        return '0 B'

    value = float(bytes_size)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if value < 1024.0:
            return f'{value:.2f} {unit}'
        value /= 1024.0
    return f'{value:.2f} TB'



def format_duration(seconds: int) -> str:
    total_seconds = max(int(seconds), 0)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f'{hours:02d}:{minutes:02d}:{secs:02d}'



def format_uptime(seconds: int) -> str:
    total_seconds = max(int(seconds), 0)
    total_days, remainder = divmod(total_seconds, 86400)
    months, remaining_days = divmod(total_days, 30)
    weeks, days = divmod(remaining_days, 7)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)

    parts: list[str] = []
    if months:
        parts.append(f"{months} month{'s' if months != 1 else ''}")
    if weeks:
        parts.append(f"{weeks} week{'s' if weeks != 1 else ''}")
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")

    parts.append(f'{hours:02d}:{minutes:02d}:{secs:02d}')
    return ' '.join(parts)
