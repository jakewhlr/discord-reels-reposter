"""Discord embed construction for reposted videos.

Discord will not let a bot put an uploaded file inside an embed's video slot
(embed.video is only populated by Discord's own URL unfurling), so the message
carries a rich embed *and* the video as a normal attachment. Discord renders
the embed first and the playable video directly beneath it.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import discord

import config

logger = logging.getLogger(__name__)

# Facebook stuffs engagement stats into the title:
#   "34K views · 390 reactions | <caption> | <uploader>"
# Strip that leading stats chunk so the title reads like a title.
_FB_STATS_RE = re.compile(
    r'^\s*[\d.,]+[KMB]?\s+(?:views?|reactions?|comments?|shares?|plays?)'
    r'(?:\s*·\s*[\d.,]+[KMB]?\s+\w+)*\s*\|\s*',
    re.IGNORECASE,
)

# X titles are "Uploader - first chunk of the tweet text ..." which duplicates
# the caption we already show.
_X_TITLE_RE = re.compile(r'^.{1,64}?\s+-\s+')

# Instagram has no real titles, just boilerplate built from the handle:
#   "Video by wowforeverguide"
_IG_TITLE_RE = re.compile(r'^(?:video|reel|post|photo)\s+by\s+\S+$', re.IGNORECASE)


def normalize_caption(text: str) -> str:
    """
    Tidy a caption while keeping its paragraph structure.

    Discord embeds render newlines, and Instagram/Facebook captions are
    genuinely multi-line, so collapsing everything to one line (as a naive
    whitespace join does) throws away readability. Runs of blank lines are
    squeezed to a single blank line.

    Args:
        text: The raw caption

    Returns:
        The normalised caption
    """
    if not text:
        return ""

    lines = [" ".join(line.split()) for line in text.splitlines()]
    out = "\n".join(lines)
    out = re.sub(r'\n{3,}', '\n\n', out)
    return out.strip()


def _fmt_count(value: Optional[int]) -> Optional[str]:
    """Render a count compactly: 1234 -> '1.2K', 1234567 -> '1.2M'."""
    if not value or value < 0:
        return None
    for threshold, suffix in ((1_000_000_000, 'B'), (1_000_000, 'M'), (1_000, 'K')):
        if value >= threshold:
            trimmed = f"{value / threshold:.1f}".rstrip('0').rstrip('.')
            return f"{trimmed}{suffix}"
    return str(value)


def _fmt_duration(seconds: Optional[float]) -> Optional[str]:
    """Render a duration as m:ss, or h:mm:ss when it runs over an hour."""
    if not seconds or seconds <= 0:
        return None
    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def clean_title(title: str, platform: str, uploader: str = "") -> str:
    """
    Strip platform boilerplate out of a video title.

    Args:
        title: The raw title from yt-dlp
        platform: The platform name
        uploader: The uploader name, stripped off the end when present

    Returns:
        A cleaned title, possibly empty if nothing useful remains
    """
    if not title:
        return ""

    cleaned = " ".join(title.split())

    if platform == "Facebook":
        cleaned = _FB_STATS_RE.sub('', cleaned)
        # Facebook also appends " | <uploader>"
        if uploader and cleaned.endswith(f"| {uploader}"):
            cleaned = cleaned[: -len(f"| {uploader}")].strip()
    elif platform == "X":
        cleaned = _X_TITLE_RE.sub('', cleaned)
    elif platform == "Instagram":
        # Boilerplate like "Video by somehandle" carries no information
        if _IG_TITLE_RE.match(cleaned):
            return ""

    return cleaned.strip(" |-·")


def _truncate(text: str, limit: int) -> str:
    """Truncate to limit characters, adding an ellipsis when cut."""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def build_video_embed(meta: Dict[str, Any], platform: str) -> Optional[discord.Embed]:
    """
    Build the embed that accompanies a reposted video.

    Args:
        meta: Metadata dict from utils.downloader.extract_metadata()
        platform: The platform name the video came from

    Returns:
        A discord.Embed, or None if there was no metadata worth showing
    """
    uploader = (meta.get('uploader') or '').strip()
    caption = normalize_caption(meta.get('description') or '')
    title = clean_title(meta.get('title') or '', platform, uploader)
    webpage_url = meta.get('webpage_url') or meta.get('original_url') or ''

    # The title and caption frequently say the same thing (Facebook embeds the
    # caption in the title). Keep whichever is richer, not both.
    if title and caption:
        if caption.startswith(title) or title.startswith(caption[:60]):
            title = ""

    body = caption or title
    heading = title if caption else ""

    embed = discord.Embed(
        colour=discord.Colour(config.PLATFORM_COLORS.get(platform, 0x2B2D31)),
    )

    if heading:
        embed.title = _truncate(heading, 256)
        if webpage_url:
            embed.url = webpage_url
    elif webpage_url:
        # No separate heading, so make the platform name the clickable link
        embed.title = f"View on {platform}"
        embed.url = webpage_url

    if body:
        embed.description = _truncate(body, config.EMBED_DESCRIPTION_LIMIT)

    if uploader:
        embed.set_author(
            name=_truncate(uploader, 256),
            url=meta.get('uploader_url') or None,
        )

    # Engagement stats, only the ones this platform actually reports
    stats = []
    for label, key in (
        ("👁", 'view_count'),
        ("❤️", 'like_count'),
        ("🔁", 'repost_count'),
        ("💬", 'comment_count'),
    ):
        rendered = _fmt_count(meta.get(key))
        if rendered:
            stats.append(f"{label} {rendered}")

    duration = _fmt_duration(meta.get('duration'))
    if duration:
        stats.append(f"⏱ {duration}")

    footer = f"{platform}"
    if stats:
        footer += "  •  " + "  ".join(stats)
    embed.set_footer(text=_truncate(footer, 2048))

    # Original post time, rendered by Discord in the viewer's own timezone
    ts = meta.get('timestamp')
    if ts:
        try:
            embed.timestamp = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            pass

    if config.ENABLE_EMBED_THUMBNAIL and meta.get('thumbnail'):
        embed.set_thumbnail(url=meta['thumbnail'])

    # Nothing worth showing beyond the bare platform footer
    if not (embed.title or embed.description or uploader):
        return None

    return embed
