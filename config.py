"""Configuration constants for the Discord video bot."""

import os
import re
import logging

# ---------------------------------------------------------------------------
# Upload size limit
#
# Discord's attachment limit depends on the guild's boost tier (10 MiB at
# tier 0/1, 50 MiB at tier 2, 100 MiB at tier 3), so it is resolved per
# message from Guild.filesize_limit -- see utils/limits.py. These settings
# only shape that resolution.
# ---------------------------------------------------------------------------

# Hard override in MB. 0 (default) means "use the guild's real limit".
# Set this to cap uploads below what the server would actually allow.
MAX_FILE_SIZE_OVERRIDE = int(os.getenv("MAX_FILE_SIZE_MB", "0")) * 1024 * 1024

# Used when there is no guild context or discord.py reports nothing useful.
MAX_FILE_SIZE_FALLBACK = 8 * 1024 * 1024  # 8MB

# The limit covers the whole multipart request, not just the video, so leave
# room for the embed JSON and boundaries.
UPLOAD_SIZE_HEADROOM = 256 * 1024  # 256KB

# Backwards compatibility: anything still reading config.MAX_FILE_SIZE gets
# the conservative fallback rather than a wrong per-guild answer.
MAX_FILE_SIZE = MAX_FILE_SIZE_OVERRIDE or MAX_FILE_SIZE_FALLBACK

# Temporary download directory
TEMP_DIR = "./temp_downloads"

# ---------------------------------------------------------------------------
# Platform URL patterns
#
# Maps a human-readable platform name to the URL patterns that identify it.
# Patterns are matched with re.match() against a cleaned URL token (see
# utils.validators.clean_url_token), so they anchor at the start of the string
# but need not match trailing path/query junk.
#
# Adding a platform is just a new entry here -- detection, the handler and the
# error messages are all driven off this dict.
# ---------------------------------------------------------------------------

PLATFORM_PATTERNS = {
    "Instagram": [
        re.compile(r'https?://(?:www\.)?instagram\.com/reels?/([A-Za-z0-9_-]+)'),
        re.compile(r'https?://(?:www\.)?instagram\.com/p/([A-Za-z0-9_-]+)'),
        re.compile(r'https?://(?:www\.)?instagram\.com/share/(?:reel/)?([A-Za-z0-9_-]+)'),
        re.compile(r'https?://(?:www\.)?instagram\.com/[A-Za-z0-9_.]+/reels?/([A-Za-z0-9_-]+)'),
    ],
    "TikTok": [
        re.compile(r'https?://(?:www\.)?tiktok\.com/@[^/\s]+/video/(\d+)'),
        re.compile(r'https?://(?:vm|vt)\.tiktok\.com/([A-Za-z0-9]+)'),  # Short links
        re.compile(r'https?://(?:www\.)?tiktok\.com/t/([A-Za-z0-9]+)'),  # Another short link format
    ],
    # Shorts only, deliberately: a bare youtu.be/<id> link matches any YouTube
    # video, and a reposter bot should not try to squeeze a 3-hour upload into
    # 8MB. Full-length links are left alone for Discord's own embed.
    "YouTube": [
        re.compile(r'https?://(?:www\.|m\.)?youtube\.com/shorts/([A-Za-z0-9_-]+)'),
    ],
    "Facebook": [
        # Reels: facebook.com/reel/123456
        re.compile(r'https?://(?:www\.|m\.|web\.|[a-z]{2}-[a-z]{2}\.)?facebook\.com/reel/(\d+)'),
        # App share links: facebook.com/share/v/abc123/ (/share/r/ for reels)
        re.compile(r'https?://(?:www\.|m\.|web\.)?facebook\.com/share/[rv]/([A-Za-z0-9_-]+)'),
        # Page/profile video: facebook.com/<name>/videos/<slug>/<id>
        re.compile(r'https?://(?:www\.|m\.|web\.|[a-z]{2}-[a-z]{2}\.)?facebook\.com/[^/\s]+/videos/'),
        # Watch pages: facebook.com/watch?v=123 and facebook.com/watch/?v=123
        re.compile(r'https?://(?:www\.|m\.|web\.)?facebook\.com/watch/?\?v=(\d+)'),
        # Legacy: facebook.com/video.php?v=123
        re.compile(r'https?://(?:www\.|m\.|web\.)?facebook\.com/video\.php\?.*v=(\d+)'),
        # Short links: fb.watch/abc123/
        re.compile(r'https?://fb\.watch/([A-Za-z0-9_-]+)'),
    ],
    "Reddit": [
        # Comment permalinks
        re.compile(r'https?://(?:www\.|old\.|new\.|np\.|m\.|sh\.)?reddit\.com/r/[^/\s]+/comments/([A-Za-z0-9]+)'),
        # New-style app share links: reddit.com/r/<sub>/s/<id>
        re.compile(r'https?://(?:www\.|old\.|new\.|np\.|m\.|sh\.)?reddit\.com/r/[^/\s]+/s/([A-Za-z0-9]+)'),
        # Subreddit-less permalink: reddit.com/comments/<id>
        re.compile(r'https?://(?:www\.|old\.|new\.|np\.|m\.)?reddit\.com/comments/([A-Za-z0-9]+)'),
        # User posts: reddit.com/user/<name>/comments/<id>
        re.compile(r'https?://(?:www\.|old\.|new\.|np\.|m\.)?reddit\.com/(?:user|u)/[^/\s]+/comments/([A-Za-z0-9]+)'),
        # Direct video host
        re.compile(r'https?://v\.redd\.it/([A-Za-z0-9]+)'),
        # Short links
        re.compile(r'https?://redd\.it/([A-Za-z0-9]+)'),
    ],
    "X": [
        # x.com / twitter.com status links
        re.compile(r'https?://(?:www\.|mobile\.|m\.)?(?:x|twitter)\.com/[A-Za-z0-9_]+/status(?:es)?/(\d+)'),
        # Logged-out / intent style: /i/status/123 and /i/web/status/123
        re.compile(r'https?://(?:www\.|mobile\.|m\.)?(?:x|twitter)\.com/i/(?:web/)?status/(\d+)'),
    ],
}

SUPPORTED_PLATFORMS = list(PLATFORM_PATTERNS)

# Hosts that mirror a canonical platform purely to fix Discord embeds. yt-dlp
# has no extractors for these, so the host is rewritten back to the real one
# before the URL is handed off. {mirror_host: canonical_host}
URL_HOST_REWRITES = {
    "vxtwitter.com": "x.com",
    "fixvx.com": "x.com",
    "fixupx.com": "x.com",
    "twittpr.com": "x.com",
    "fxtwitter.com": "x.com",
    "ddinstagram.com": "instagram.com",
    "kkinstagram.com": "instagram.com",
    "d.ddinstagram.com": "instagram.com",
    "rxddit.com": "reddit.com",
    "vxreddit.com": "reddit.com",
    "vxtiktok.com": "tiktok.com",
    "tnktok.com": "tiktok.com",
}

# Extra hint appended when a download fails. These platforms gate a meaningful
# share of their content behind a login.
PLATFORM_FAILURE_HINTS = {
    "Instagram": "Instagram usually needs a logged-in session for Reels.",
    "Facebook": "Facebook needs a logged-in session for most videos; private and group posts are never reachable.",
    "X": "X needs a logged-in session for most videos, including age-restricted posts.",
    "Reddit": "Reddit now blocks anonymous access from most datacenter/server IPs (it serves a 'prove your humanity' challenge), so YTDL_COOKIES_FILE is effectively required.",
}

# ---------------------------------------------------------------------------
# Download options
# ---------------------------------------------------------------------------

# Skip anything longer than this before downloading. Protects against someone
# posting a feature-length video that can never be compressed to 8MB.
# Set to 0 to disable the check.
MAX_DURATION_SECONDS = int(os.getenv("MAX_DURATION_SECONDS", "900"))  # 15 min

# Optional cookie source, needed for login-gated platforms (Facebook, X,
# Instagram). Set at most one of these in .env:
#   YTDL_COOKIES_FILE=/app/cookies.txt     (Netscape cookies.txt export)
#   YTDL_COOKIES_FROM_BROWSER=firefox      (or chrome, chromium:Profile 1, ...)
COOKIES_FILE = os.getenv("YTDL_COOKIES_FILE", "").strip()
COOKIES_FROM_BROWSER = os.getenv("YTDL_COOKIES_FROM_BROWSER", "").strip()
COOKIES_CONFIGURED = bool(COOKIES_FILE or COOKIES_FROM_BROWSER)

# Platforms that are pointless to even attempt without cookies, so their links
# are ignored entirely rather than answered with a "needs login" reply.
#
# Reddit is here because it now serves a "prove your humanity" challenge to
# anonymous requests from most server IPs -- every Reddit link would otherwise
# get a failure reply. Set YTDL_COOKIES_FILE to turn Reddit support on.
REQUIRES_COOKIES = {"Reddit"}

# yt-dlp download options for medium quality.
#
# The format chain prefers a single progressive MP4 (no remux needed), then
# falls back to merging separate video+audio streams. Those '+ba' branches are
# required for Reddit (v.redd.it) and some X/Facebook videos, which serve DASH
# only -- the old 'best[ext=mp4]/best' chain downloads those SILENT.
YTDL_OPTIONS = {
    'format': (
        'b[height<=720][ext=mp4]/'
        'bv*[height<=720][ext=mp4]+ba[ext=m4a]/'
        'bv*[height<=720]+ba/'
        'b[height<=720]/'
        'bv*+ba/b'
    ),
    'merge_output_format': 'mp4',  # Always hand Discord an .mp4 container
    'outtmpl': os.path.join(TEMP_DIR, '%(extractor_key)s-%(id)s.%(ext)s'),
    'quiet': True,  # Suppress yt-dlp output
    'no_warnings': True,
    'noplaylist': True,  # Don't download playlists
    'playlist_items': '1',  # Multi-video posts/tweets: first video only
    'retries': 3,
    'socket_timeout': 30,
}

if COOKIES_FILE:
    YTDL_OPTIONS['cookiefile'] = COOKIES_FILE
elif COOKIES_FROM_BROWSER:
    # "firefox" or "chrome:Default" -> (browser, profile, keyring, container)
    _browser, _, _profile = COOKIES_FROM_BROWSER.partition(':')
    YTDL_OPTIONS['cookiesfrombrowser'] = (_browser, _profile or None, None, None)

# Video compression settings
ENABLE_COMPRESSION = True  # Automatically compress videos that exceed MAX_FILE_SIZE
MAX_COMPRESSION_ATTEMPTS = 3  # Number of compression attempts with different settings

# How many downloads/compressions may run at once. yt-dlp and ffmpeg are
# blocking and run in worker threads; the container is capped at 1 CPU, so
# letting many ffmpeg jobs run together just makes them all slower.
MAX_CONCURRENT_JOBS = int(os.getenv("MAX_CONCURRENT_JOBS", "2"))

# ---------------------------------------------------------------------------
# Embed settings
#
# A reposted video is sent as a rich embed plus the video as an attachment.
# Discord does not allow a bot to place an uploaded file inside an embed's
# video slot, so the embed carries the caption/author/stats and the playable
# video renders directly below it.
# ---------------------------------------------------------------------------

ENABLE_EMBEDS = os.getenv("ENABLE_EMBEDS", "true").strip().lower() not in ("0", "false", "no")

# The poster frame duplicates the video that is already attached, so this is
# off by default. Turn it on for a small right-aligned thumbnail in the embed.
ENABLE_EMBED_THUMBNAIL = os.getenv("ENABLE_EMBED_THUMBNAIL", "false").strip().lower() in ("1", "true", "yes")

# Caption length before truncation (Discord's own ceiling is 4096)
EMBED_DESCRIPTION_LIMIT = int(os.getenv("EMBED_DESCRIPTION_LIMIT", "400"))

# Brand accent colour per platform
PLATFORM_COLORS = {
    "Instagram": 0xE1306C,
    "TikTok": 0x00F2EA,
    "YouTube": 0xFF0000,
    "Facebook": 0x1877F2,
    "Reddit": 0xFF4500,
    "X": 0x000000,
}

# Metadata fields pulled off the yt-dlp info dict and handed to the embed
# builder. Platforms populate different subsets -- verified live: Facebook
# gives views but no likes, X gives likes/reposts/comments but no views,
# YouTube gives views/likes/comments.
EMBED_METADATA_FIELDS = (
    'id',
    'title',
    'description',
    'uploader',
    'uploader_url',
    'duration',
    'view_count',
    'like_count',
    'repost_count',
    'comment_count',
    'timestamp',
    'thumbnail',
    'webpage_url',
    'original_url',
)

# Logging configuration
LOGGING_LEVEL = logging.INFO
LOGGING_FORMAT = '[%(asctime)s] %(levelname)s: %(message)s'
LOGGING_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
