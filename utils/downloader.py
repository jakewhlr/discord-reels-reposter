"""Video download utilities using yt-dlp."""

import logging
import os
import re
import yt_dlp
from typing import Any, Dict, Optional
import config

logger = logging.getLogger(__name__)

# Substrings yt-dlp uses when a URL is simply not a video (a Reddit text or
# image post, a gallery, a tweet with no media). These are NOT errors worth
# shouting about: a Reddit share link gives no hint whether the post contains
# video, so the bot has to try and then stay quiet when it doesn't.
_NO_VIDEO_MARKERS = (
    'no video could be found',
    'no media found',
    'there is no video',
    "there's no video",
    'no formats found',
    'unsupported url',
    'does not have a video',
    'no video in this',
)

# Substrings meaning the platform demanded a login. Actionable: the operator
# can fix it by supplying cookies.
_AUTH_MARKERS = (
    'account authentication is required',
    'login required',
    'requested content is not available',
    'sign in to confirm',
    'you must be logged in',
    'private video',
    'rate-limit reached',
    'prove your humanity',
    'cookies',
)


def _classify_error(msg: str) -> str:
    """
    Bucket a yt-dlp error message into 'novideo', 'auth' or 'failed'.

    Args:
        msg: The exception text from yt-dlp

    Returns:
        One of 'novideo', 'auth', 'failed'
    """
    lowered = msg.lower()

    # Check no-video first: "Unsupported URL" for a Reddit text post should
    # stay silent even though the message also mentions cookies.
    if any(marker in lowered for marker in _NO_VIDEO_MARKERS):
        return 'novideo'
    if any(marker in lowered for marker in _AUTH_MARKERS):
        return 'auth'
    return 'failed'


def _resolve_filepath(ydl: Any, info: Any) -> Optional[str]:
    """
    Work out the real path of the downloaded file.

    ydl.prepare_filename() reports the *pre-merge* extension, so for any video
    that needed a separate audio stream muxed in (Reddit's v.redd.it, several
    X and Facebook videos) it returns e.g. ".webm" while the file on disk is
    ".mp4". yt-dlp records the true post-processing path in
    info['requested_downloads'], so prefer that and only fall back to the
    guess -- plus a last-ditch extension scan -- if it is missing.

    Args:
        ydl: The YoutubeDL instance that performed the download
        info: The info dict returned by extract_info()

    Returns:
        Path to the downloaded file, or None if it cannot be located
    """
    for download in info.get('requested_downloads') or []:
        path = download.get('filepath') or download.get('_filename')
        if path and os.path.exists(path):
            return path

    guess = ydl.prepare_filename(info)
    if os.path.exists(guess):
        return guess

    # Final fallback: the merge changed the container, so try known extensions
    base = os.path.splitext(guess)[0]
    for ext in ('mp4', 'mkv', 'webm', 'mov'):
        candidate = f"{base}.{ext}"
        if os.path.exists(candidate):
            return candidate

    return None


def extract_metadata(info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Pull the embed-relevant fields off a yt-dlp info dict.

    Platforms populate different subsets of these, so every consumer must
    treat each field as optional.

    Args:
        info: The info dict returned by extract_info()

    Returns:
        A dict containing only the fields listed in
        config.EMBED_METADATA_FIELDS that actually had a value
    """
    return {
        key: info[key]
        for key in config.EMBED_METADATA_FIELDS
        if info.get(key) not in (None, "", [], {})
    }


def download_video(url: str) -> Optional[Dict[str, Any]]:
    """
    Download a video from the given URL using yt-dlp.

    Args:
        url: The URL of the video to download

    Returns:
        On success, a dictionary containing:
            - 'filepath': Path to the downloaded file
            - 'filesize': Size of the file in bytes
            - 'title': Title of the video
            - 'duration': Duration in seconds (0 if unknown)
        If the video is longer than config.MAX_DURATION_SECONDS, a dictionary
        containing 'error': 'duration' and 'duration'.
        Returns None if the download fails.
    """
    logger.info(f"Downloading video from: {url}")

    try:
        # Ensure temp directory exists
        os.makedirs(config.TEMP_DIR, exist_ok=True)

        with yt_dlp.YoutubeDL(config.YTDL_OPTIONS) as ydl:
            # Probe first so an over-long video is rejected before we spend
            # bandwidth on it (and before compression tries the impossible).
            if config.MAX_DURATION_SECONDS > 0:
                probe = ydl.extract_info(url, download=False)
                probe = _first_entry(probe)
                duration = probe.get('duration') or 0

                if duration and duration > config.MAX_DURATION_SECONDS:
                    logger.info(
                        f"Skipping {url}: duration {duration}s exceeds limit "
                        f"{config.MAX_DURATION_SECONDS}s"
                    )
                    return {'error': 'duration', 'duration': duration}

            info = _first_entry(ydl.extract_info(url, download=True))

            filepath = _resolve_filepath(ydl, info)
            if not filepath:
                logger.error(f"Download reported success but no file found for {url}")
                return None

            filesize = os.path.getsize(filepath)
            title = info.get('title') or 'video'

            logger.info(
                f"Download complete - Size: {filesize / 1024 / 1024:.2f}MB, Title: {title}"
            )

            return {
                'filepath': filepath,
                'filesize': filesize,
                'title': title,
                'duration': info.get('duration') or 0,
                'metadata': extract_metadata(info),
            }

    except yt_dlp.utils.DownloadError as e:
        kind = _classify_error(str(e))
        if kind == 'novideo':
            logger.info(f"No video at {url} (staying quiet)")
        else:
            logger.error(f"Download failed for {url}: {str(e)}")
        return None if kind == 'failed' else {'error': kind}
    except Exception as e:
        logger.error(f"Unexpected error downloading {url}: {str(e)}")
        return None


def _first_entry(info: Any) -> Dict[str, Any]:
    """
    Flatten a playlist-ish info dict down to its first real entry.

    Reddit galleries, Facebook watch pages and multi-video tweets can come
    back as a playlist even with noplaylist set, in which case the useful
    metadata lives one level down in 'entries'.
    """
    current: Dict[str, Any] = dict(info) if info else {}

    while current.get('_type') in ('playlist', 'multi_video') and current.get('entries'):
        entries = [e for e in current['entries'] if e]
        if not entries:
            break
        current = dict(entries[0])

    return current


def sanitize_filename(title: str, max_length: int = 50) -> str:
    """
    Turn a video title into a safe filename stem for the Discord upload.

    Platform titles routinely contain slashes, newlines and emoji (X uses the
    whole tweet text as the title), which make for broken attachment names.

    Args:
        title: The raw video title
        max_length: Maximum length of the returned stem

    Returns:
        A filesystem- and Discord-safe filename stem, never empty
    """
    # Collapse all whitespace (including newlines/tabs) to single spaces first,
    # so a line break becomes a space rather than an underscore.
    cleaned = " ".join(title.split())
    cleaned = "".join(c if c.isalnum() or c in " ._-" else "_" for c in cleaned)
    cleaned = re.sub(r"_{2,}", "_", cleaned)  # collapse underscore runs
    cleaned = cleaned.strip(" ._-")[:max_length].strip(" ._-")
    return cleaned or "video"


def cleanup_file(filepath: str) -> None:
    """
    Delete a file from the filesystem.

    Args:
        filepath: Path to the file to delete
    """
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.info(f"Cleaned up temporary file: {filepath}")
    except Exception as e:
        logger.warning(f"Failed to clean up file {filepath}: {str(e)}")
