import os
import shutil
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError as YtDlpDownloadError

from config import settings

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



def _extract_filesize(info: dict[str, Any]) -> int:
    size_candidates = [
        info.get("filesize"),
        info.get("filesize_approx"),
    ]

    for item in info.get("requested_formats") or []:
        size_candidates.extend([item.get("filesize"), item.get("filesize_approx")])

    for item in info.get("formats") or []:
        size_candidates.extend([item.get("filesize"), item.get("filesize_approx")])

    numeric_candidates = [
        int(size)
        for size in size_candidates
        if isinstance(size, (int, float)) and size > 0
    ]
    return max(numeric_candidates, default=0)



def _base_options() -> dict[str, Any]:
    return {
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "retries": settings.MAX_RETRIES,
        "fragment_retries": settings.MAX_RETRIES,
    }



def _download_options(download_path: str) -> dict[str, Any]:
    options = _base_options()
    options["outtmpl"] = str(Path(download_path) / "%(extractor)s-%(id)s.%(ext)s")

    if shutil.which("ffmpeg"):
        options["format"] = "bestvideo*+bestaudio/best"
        options["merge_output_format"] = "mp4"
    else:
        options["format"] = "best[acodec!=none][vcodec!=none]/best"

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
    try:
        with YoutubeDL(_base_options()) as ydl:
            info = _unwrap_info(ydl.extract_info(url, download=False))
    except YtDlpDownloadError as exc:
        raise DownloaderError(str(exc)) from exc
    except Exception as exc:
        raise DownloaderError(f"Unexpected downloader error: {exc}") from exc

    return {
        "title": info.get("title") or "Untitled media",
        "filesize": _extract_filesize(info),
        "duration": int(info.get("duration") or 0),
        "platform": (info.get("extractor_key") or info.get("extractor") or "unknown").lower(),
    }



def download_media(url, download_path):
    """Download media to disk and return the final file path."""
    os.makedirs(download_path, exist_ok=True)

    try:
        with YoutubeDL(_download_options(download_path)) as ydl:
            info = _unwrap_info(ydl.extract_info(url, download=True))
    except YtDlpDownloadError as exc:
        raise DownloaderError(str(exc)) from exc
    except Exception as exc:
        raise DownloaderError(f"Unexpected downloader error: {exc}") from exc

    return _resolve_download_path(info, download_path)
