"""URL validation and extraction utilities."""

import logging
import re
from typing import List, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit

import config

logger = logging.getLogger(__name__)

# Finds candidate URLs anywhere in a message, including ones glued to
# punctuation or wrapped in Discord's <...> embed-suppression syntax.
_URL_RE = re.compile(r'https?://[^\s<>()\[\]"\']+', re.IGNORECASE)

# Trailing characters that are almost never part of a real URL when a link is
# written inline in prose ("check this out: https://x.com/a/status/1.").
_TRAILING_JUNK = '.,!?:;\'"*_~`)]}>'


def clean_url_token(token: str) -> str:
    """
    Normalise a URL as it appeared in a chat message.

    Strips Discord markup and trailing punctuation, then rewrites known
    embed-fixer mirror hosts (vxtwitter.com, ddinstagram.com, ...) back to
    their canonical host so yt-dlp has an extractor for them.

    Args:
        token: A raw token from a message

    Returns:
        The cleaned, canonicalised URL
    """
    url = token.strip().strip('<>').rstrip(_TRAILING_JUNK)

    try:
        parts = urlsplit(url)
    except ValueError:
        return url

    # Strip credentials/port for the lookup
    bare_host = parts.netloc.lower().split('@')[-1].split(':')[0]

    canonical = config.URL_HOST_REWRITES.get(bare_host)
    if canonical:
        logger.info(f"Rewriting mirror host {bare_host} -> {canonical}")
        url = urlunsplit(parts._replace(netloc=canonical))

    return url


def detect_platform(url: str) -> Optional[str]:
    """
    Identify which supported platform a URL belongs to.

    Platforms listed in config.REQUIRES_COOKIES are treated as unsupported
    while no cookie source is configured, so their links are ignored outright
    instead of drawing a "needs login" reply on every post.

    Args:
        url: The URL to check (should already be cleaned)

    Returns:
        The platform name, or None if the URL is not supported
    """
    for platform, patterns in config.PLATFORM_PATTERNS.items():
        if platform in config.REQUIRES_COOKIES and not config.COOKIES_CONFIGURED:
            continue
        for pattern in patterns:
            if pattern.match(url):
                return platform
    return None


def is_supported_url(url: str) -> Tuple[bool, str]:
    """
    Check if a URL is from a supported platform.

    Args:
        url: The URL to check

    Returns:
        Tuple of (is_supported, platform_name)
    """
    platform = detect_platform(clean_url_token(url))
    return (True, platform) if platform else (False, "")


def extract_video_urls(message: str) -> List[Tuple[str, str]]:
    """
    Extract all supported video URLs from a message.

    URLs are cleaned and de-duplicated, so posting the same link twice -- or
    the same video via both a mirror host and the canonical one -- yields a
    single entry.

    Args:
        message: The message text to search

    Returns:
        List of tuples (url, platform_name) for all supported URLs found
    """
    urls: List[Tuple[str, str]] = []
    seen = set()

    for match in _URL_RE.findall(message):
        url = clean_url_token(match)
        platform = detect_platform(url)

        if not platform or url in seen:
            continue

        seen.add(url)
        urls.append((url, platform))
        logger.info(f"Detected {platform} URL: {url}")

    return urls


# ---------------------------------------------------------------------------
# Backward-compatible single-platform helpers
# ---------------------------------------------------------------------------

def _matches(platform: str, url: str) -> bool:
    return detect_platform(clean_url_token(url)) == platform


def is_instagram_url(url: str) -> bool:
    """Check if a URL is an Instagram Reel or post URL."""
    return _matches("Instagram", url)


def is_tiktok_url(url: str) -> bool:
    """Check if a URL is a TikTok video URL."""
    return _matches("TikTok", url)


def is_youtube_url(url: str) -> bool:
    """Check if a URL is a YouTube Shorts URL."""
    return _matches("YouTube", url)


def is_facebook_url(url: str) -> bool:
    """Check if a URL is a Facebook video or Reel URL."""
    return _matches("Facebook", url)


def is_reddit_url(url: str) -> bool:
    """Check if a URL is a Reddit post or v.redd.it video URL."""
    return _matches("Reddit", url)


def is_x_url(url: str) -> bool:
    """Check if a URL is an X (Twitter) status URL."""
    return _matches("X", url)


def extract_instagram_urls(message: str) -> List[str]:
    """Extract all Instagram URLs from a message."""
    return [url for url, platform in extract_video_urls(message) if platform == "Instagram"]
