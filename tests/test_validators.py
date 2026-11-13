"""URL detection tests.

Run with:  uv run --with pytest pytest -q
"""

import pytest

import config
from utils.validators import (
    clean_url_token,
    detect_platform,
    extract_video_urls,
    is_supported_url,
)


@pytest.fixture
def cookies_on(monkeypatch):
    """Pretend a cookie source is configured, enabling cookie-gated platforms."""
    monkeypatch.setattr(config, "COOKIES_CONFIGURED", True)


# (url, expected platform) -- platforms that work without cookies
SUPPORTED = [
    # Instagram
    ("https://www.instagram.com/reel/Cxyz123_-/", "Instagram"),
    ("https://instagram.com/reels/Cxyz123/", "Instagram"),
    ("https://www.instagram.com/p/Cabc456/?igshid=xyz", "Instagram"),
    # TikTok
    ("https://www.tiktok.com/@someuser/video/7234567890123456789", "TikTok"),
    ("https://vm.tiktok.com/ZMabc123/", "TikTok"),
    ("https://vt.tiktok.com/ZSabc123/", "TikTok"),
    ("https://www.tiktok.com/t/ZTabc123/", "TikTok"),
    # YouTube (Shorts only)
    ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "YouTube"),
    ("https://m.youtube.com/shorts/dQw4w9WgXcQ?feature=share", "YouTube"),
    # Facebook -- all verified against live URLs
    ("https://www.facebook.com/reel/1234567890", "Facebook"),
    ("https://www.facebook.com/reel/2583815398764268/?mibextid=9drbnH&s=yWDuG2&fs=e", "Facebook"),
    ("https://facebook.com/share/v/abc123XYZ/", "Facebook"),
    ("https://www.facebook.com/share/r/1A2b3C4d/", "Facebook"),
    ("https://www.facebook.com/somepage/videos/my-clip/1234567890/", "Facebook"),
    ("https://www.facebook.com/radiokicksfm/videos/3676516585958356/", "Facebook"),
    ("https://www.facebook.com/watch?v=1234567890", "Facebook"),
    ("https://www.facebook.com/watch/?v=1234567890", "Facebook"),
    ("https://www.facebook.com/video.php?v=1234567890", "Facebook"),
    ("https://fb.watch/abc-123_x/", "Facebook"),
    ("https://m.facebook.com/reel/987654321", "Facebook"),
    # X / Twitter
    ("https://x.com/someuser/status/1234567890123456789", "X"),
    ("https://twitter.com/someuser/status/1234567890123456789", "X"),
    ("https://mobile.twitter.com/someuser/status/1234567890", "X"),
    ("https://x.com/i/status/1234567890", "X"),
    ("https://twitter.com/i/web/status/1234567890", "X"),
]

# Reddit is cookie-gated (anonymous access gets a humanity challenge), so these
# only resolve once a cookie source is configured.
REDDIT_URLS = [
    "https://www.reddit.com/r/aww/comments/1abc2de/some_title/",
    "https://old.reddit.com/r/videos/comments/1abc2de/",
    # both forms of the same post: browser URL and in-app share link
    "https://www.reddit.com/r/BravoRealHousewives/comments/1xvbovp/a_clip_from_mary/",
    "https://www.reddit.com/r/BravoRealHousewives/s/M4VfrUhKKS",
    "https://www.reddit.com/comments/124pp33",
    "https://reddit.com/user/someone/comments/1abc2de/title/",
    "https://v.redd.it/abc123def456",
    "https://redd.it/1abc2de",
]

UNSUPPORTED = [
    "https://example.com/video.mp4",
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",  # full-length, deliberately ignored
    "https://youtu.be/dQw4w9WgXcQ",                 # ditto
    "https://www.instagram.com/someuser/",          # profile, not a post
    "https://www.reddit.com/r/aww/",                # subreddit, not a post
    "https://x.com/someuser",                       # profile, not a status
    "https://www.facebook.com/somepage",            # page, not a video
    "not a url at all",
    "",
]


@pytest.mark.parametrize("url,platform", SUPPORTED)
def test_supported_urls_detected(url, platform):
    assert detect_platform(url) == platform
    assert is_supported_url(url) == (True, platform)


@pytest.mark.parametrize("url", UNSUPPORTED)
def test_unsupported_urls_ignored(url):
    assert detect_platform(url) is None
    assert is_supported_url(url) == (False, "")


@pytest.mark.parametrize("url", REDDIT_URLS)
def test_reddit_detected_when_cookies_configured(url, cookies_on):
    assert detect_platform(url) == "Reddit"


@pytest.mark.parametrize("url", REDDIT_URLS)
def test_reddit_ignored_without_cookies(url):
    """Without cookies, Reddit links must be dropped silently, not answered."""
    assert detect_platform(url) is None
    assert extract_video_urls(url) == []


@pytest.mark.parametrize(
    "raw,expected_host",
    [
        ("https://vxtwitter.com/u/status/123", "x.com"),
        ("https://fixupx.com/u/status/123", "x.com"),
        ("https://fxtwitter.com/u/status/123", "x.com"),
        ("https://ddinstagram.com/reel/Cabc123/", "instagram.com"),
        ("https://rxddit.com/r/aww/comments/1abc2de/", "reddit.com"),
        ("https://vxtiktok.com/@u/video/7234567890", "tiktok.com"),
    ],
)
def test_mirror_hosts_rewritten(raw, expected_host, cookies_on):
    cleaned = clean_url_token(raw)
    assert expected_host in cleaned
    # and the rewritten URL is now recognised by a real extractor pattern
    assert detect_platform(cleaned) is not None


@pytest.mark.parametrize(
    "raw,expected",
    [
        # Discord embed suppression
        ("<https://x.com/u/status/123>", "https://x.com/u/status/123"),
        # trailing sentence punctuation
        ("https://x.com/u/status/123.", "https://x.com/u/status/123"),
        ("https://x.com/u/status/123,", "https://x.com/u/status/123"),
        ("https://x.com/u/status/123)", "https://x.com/u/status/123"),
    ],
)
def test_markup_and_punctuation_stripped(raw, expected):
    assert clean_url_token(raw) == expected


def test_extract_from_prose():
    msg = (
        "lol look at this https://x.com/someuser/status/1234567890 "
        "and also <https://www.instagram.com/reel/Cabc123/> "
        "plus https://fb.watch/abc123/, wild"
    )
    found = extract_video_urls(msg)
    assert [p for _, p in found] == ["X", "Instagram", "Facebook"]
    assert all(not u.endswith((",", ">", ".")) for u, _ in found)


def test_extract_dedupes_including_mirrors():
    msg = (
        "https://x.com/u/status/123 "
        "https://x.com/u/status/123 "        # exact dupe
        "https://vxtwitter.com/u/status/123"  # same video via mirror
    )
    assert len(extract_video_urls(msg)) == 1


def test_extract_ignores_unsupported_mixed_in():
    msg = "https://example.com/a.mp4 https://fb.watch/abc123 https://youtu.be/xyz"
    assert extract_video_urls(msg) == [("https://fb.watch/abc123", "Facebook")]


def test_every_platform_has_patterns():
    assert set(config.SUPPORTED_PLATFORMS) == {
        "Instagram", "TikTok", "YouTube", "Facebook", "Reddit", "X",
    }
    for platform, patterns in config.PLATFORM_PATTERNS.items():
        assert patterns, f"{platform} has no patterns"
