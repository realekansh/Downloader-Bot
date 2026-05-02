import os
import shutil
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError as YtDlpDownloadError

from config import settings

TELEGRAM_SAFE_UPLOAD_BYTES = settings.TELEGRAM_MAX_UPLOAD_MB * 1024 * 1024

AUXILIARY_SUFFIXES = {
    ".description",
    ".info.json",
    ".jpg",
    ".jpeg",
    ".json",
    ".png",
    ".srt",
    ".txt",
    ".vtt",
    ".webp",
}


class DownloaderError(Exception):
    pass



def _unwrap_info(info: dict[str, Any]) -> dict[str, Any]:
    if info.get("entries"):
        for entry in info["entries"]:
            if entry:
                return entry
        raise DownloaderError("No downloadable entries were found in the provided URL.")

    return info




def _base_options() -> dict[str, Any]:
    return {
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "retries": settings.MAX_RETRIES,
        "fragment_retries": settings.MAX_RETRIES,
    }


def _preferred_format_selector() -> str:
    return (
        "best[ext=mp4][acodec!=none][vcodec!=none][height<=720]/"
        "best[acodec!=none][vcodec!=none][height<=720]/"
        "best[ext=mp4][acodec!=none][vcodec!=none][height<=480]/"
        "best[acodec!=none][vcodec!=none][height<=480]/"
        "best[ext=mp4][acodec!=none][vcodec!=none]/"
        "best[acodec!=none][vcodec!=none]/"
        "best"
    )


def _is_requested_format_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return 'requested format is not available' in message or 'format not available' in message



def _selected_filesize(info: dict[str, Any]) -> int:
    requested_formats = info.get("requested_formats") or []
    if requested_formats:
        selected_sizes = [
            int(size)
            for item in requested_formats
            for size in (item.get("filesize"), item.get("filesize_approx"))
            if isinstance(size, (int, float)) and size > 0
        ]
        if selected_sizes:
            return sum(selected_sizes)

    direct_sizes = [
        info.get("filesize"),
        info.get("filesize_approx"),
    ]
    numeric_sizes = [
        int(size)
        for size in direct_sizes
        if isinstance(size, (int, float)) and size > 0
    ]
    if numeric_sizes:
        return max(numeric_sizes)

    return 0



def _download_options(download_path: str) -> dict[str, Any]:
    options = _base_options()
    options["outtmpl"] = str(Path(download_path) / "%(extractor)s-%(id)s.%(ext)s")
    options["format"] = _preferred_format_selector()

    if shutil.which("ffmpeg"):
        options["merge_output_format"] = "mp4"

    return options



def _is_media_file(candidate: str) -> bool:
    path = Path(candidate)
    suffix = path.suffix.lower()
    if suffix in AUXILIARY_SUFFIXES:
        return False
    if candidate.endswith(".part") or candidate.endswith(".ytdl"):
        return False
    return path.is_file()



def _resolve_download_path(info: dict[str, Any], download_path: str) -> str:
    candidates = []

    for key in ("_filename", "filepath"):
        value = info.get(key)
        if value:
            candidates.append(value)

    for item in info.get("requested_downloads") or []:
        filepath = item.get("filepath")
        if filepath:
            candidates.append(filepath)

    for candidate in candidates:
        if candidate and os.path.exists(candidate) and _is_media_file(candidate):
            return candidate

    media_id = info.get("id")
    if media_id:
        for match in sorted(Path(download_path).glob(f"*{media_id}*")):
            if _is_media_file(str(match)):
                return str(match)

    raise DownloaderError("The media was downloaded but the output file could not be located.")



def get_video_info(url):
    """Fetch media metadata without downloading the file."""
    metadata_options = _base_options()
    metadata_options["format"] = _preferred_format_selector()

    try:
        with YoutubeDL(metadata_options) as ydl:
            info = _unwrap_info(ydl.extract_info(url, download=False))
    except YtDlpDownloadError as exc:
        if _is_requested_format_error(exc):
            fallback_options = _base_options()
            try:
                with YoutubeDL(fallback_options) as ydl:
                    info = _unwrap_info(ydl.extract_info(url, download=False))
            except YtDlpDownloadError as fallback_exc:
                raise DownloaderError(str(fallback_exc)) from fallback_exc
            except Exception as fallback_exc:
                raise DownloaderError(f"Unexpected downloader error: {fallback_exc}") from fallback_exc
        else:
            raise DownloaderError(str(exc)) from exc
    except Exception as exc:
        raise DownloaderError(f"Unexpected downloader error: {exc}") from exc

    return {
        "title": info.get("title") or "Untitled media",
        "filesize": _selected_filesize(info),
        "duration": int(info.get("duration") or 0),
        "platform": (info.get("extractor_key") or info.get("extractor") or "unknown").lower(),
    }



def download_media(url, download_path):
    """Download media to disk and return the final file path."""
    os.makedirs(download_path, exist_ok=True)

    download_options = _download_options(download_path)

    try:
        with YoutubeDL(download_options) as ydl:
            info = _unwrap_info(ydl.extract_info(url, download=True))
    except YtDlpDownloadError as exc:
        if _is_requested_format_error(exc):
            fallback_options = _base_options()
            fallback_options["outtmpl"] = str(Path(download_path) / "%(extractor)s-%(id)s.%(ext)s")
            try:
                with YoutubeDL(fallback_options) as ydl:
                    info = _unwrap_info(ydl.extract_info(url, download=True))
            except YtDlpDownloadError as fallback_exc:
                raise DownloaderError(str(fallback_exc)) from fallback_exc
            except Exception as fallback_exc:
                raise DownloaderError(f"Unexpected downloader error: {fallback_exc}") from fallback_exc
        else:
            raise DownloaderError(str(exc)) from exc
    except Exception as exc:
        raise DownloaderError(f"Unexpected downloader error: {exc}") from exc

    file_path = _resolve_download_path(info, download_path)
    actual_size = os.path.getsize(file_path)
    if actual_size > TELEGRAM_SAFE_UPLOAD_BYTES:
        raise DownloaderError(
            f"The downloaded file is too large for Telegram bots to send (max: {settings.TELEGRAM_MAX_UPLOAD_MB}MB)."
        )

    return file_path
