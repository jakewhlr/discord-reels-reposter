"""Embed builder tests.

The metadata fixtures below are verbatim captures from yt-dlp 2025.12.08
against live URLs, so they exercise the real shapes each platform returns
(including Facebook's stats-polluted title and X's duplicated title).

Run with:  uv run --with pytest pytest -q
"""

import pytest

import config
from utils.embeds import (
    _fmt_count,
    _fmt_duration,
    build_video_embed,
    clean_title,
    normalize_caption,
)

# --- real captures ---------------------------------------------------------

FACEBOOK_META = {
    'id': '2583815398764268',
    'title': "34K views · 390 reactions | Il n'aura pas tarder à retrouver du boulot... ou pas. | Prof Abronsius",
    'description': "Il n'aura pas tarder à retrouver du boulot... ou pas.",
    'uploader': 'Prof Abronsius',
    'duration': 153.366,
    'view_count': 18184,
    'timestamp': 1794564950,
    'thumbnail': 'https://scontent.flas1-2.fna.fbcdn.net/v/t15.5256-10/897485405.jpg',
    'webpage_url': 'https://m.facebook.com/watch/?v=2583815398764268&_rdr',
}

X_META = {
    'id': '1001551417340022785',
    'title': 'Lis Power - Holy shit, Shep is on a roll today.   In just 2 minutes Shep dismantl...',
    'description': 'Holy shit, Shep is on a roll today. In just 2 minutes Shep dismantles almost every single recent Fox News narrative',
    'uploader': 'Lis Power',
    'uploader_url': 'https://twitter.com/LisPower1',
    'duration': 111.278,
    'like_count': 54764,
    'repost_count': 16776,
    'comment_count': 2154,
    'timestamp': 1527623489,
    'webpage_url': 'https://twitter.com/LisPower1/status/1001551623938805763',
}

YOUTUBE_META = {
    'id': 'tPEE9ZwTmy0',
    'title': 'Shortest Video on Youtube',
    'description': 'The original "Shortest Video on Youtube" video, starring Mylo the Cat.',
    'uploader': 'Mylo the Cat',
    'uploader_url': 'https://www.youtube.com/@hiddentracktv2',
    'duration': 1,
    'view_count': 71860235,
    'like_count': 1450568,
    'comment_count': 77000,
    'timestamp': 1295458847,
    'webpage_url': 'https://www.youtube.com/watch?v=tPEE9ZwTmy0',
}


# --- formatting helpers ----------------------------------------------------

@pytest.mark.parametrize(
    "value,expected",
    [
        (None, None), (0, None), (1, "1"), (999, "999"),
        (1000, "1K"), (1234, "1.2K"), (18184, "18.2K"),
        (1_000_000, "1M"), (71_860_235, "71.9M"), (2_500_000_000, "2.5B"),
    ],
)
def test_fmt_count(value, expected):
    assert _fmt_count(value) == expected


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (None, None), (0, None), (1, "0:01"), (9.579, "0:10"),
        (111.278, "1:51"), (153.366, "2:33"), (3600, "1:00:00"), (3725, "1:02:05"),
    ],
)
def test_fmt_duration(seconds, expected):
    assert _fmt_duration(seconds) == expected


# --- title cleaning --------------------------------------------------------

def test_clean_title_strips_facebook_stats_and_uploader():
    out = clean_title(FACEBOOK_META['title'], "Facebook", "Prof Abronsius")
    assert out == "Il n'aura pas tarder à retrouver du boulot... ou pas."
    assert "views" not in out and "reactions" not in out


@pytest.mark.parametrize(
    "raw",
    [
        "34K views · 390 reactions | real caption | Someone",
        "1.2M views | real caption | Someone",
        "427 views · 12 comments · 3 shares | real caption | Someone",
    ],
)
def test_clean_title_facebook_stat_variants(raw):
    assert clean_title(raw, "Facebook", "Someone") == "real caption"


def test_clean_title_strips_x_uploader_prefix():
    out = clean_title(X_META['title'], "X", "Lis Power")
    assert out.startswith("Holy shit, Shep is on a roll")
    assert not out.startswith("Lis Power")


def test_clean_title_leaves_youtube_alone():
    assert clean_title(YOUTUBE_META['title'], "YouTube", "Mylo the Cat") == "Shortest Video on Youtube"


def test_clean_title_handles_empty():
    assert clean_title("", "Facebook") == ""
    assert clean_title("   ", "X") == ""


# --- embed construction ----------------------------------------------------

def test_facebook_embed():
    e = build_video_embed(FACEBOOK_META, "Facebook")
    assert e is not None
    assert e.author.name == "Prof Abronsius"
    assert "retrouver du boulot" in e.description
    assert e.colour.value == config.PLATFORM_COLORS["Facebook"]
    # Facebook reports views but not likes
    assert "18.2K" in e.footer.text
    assert "❤️" not in e.footer.text
    assert "2:33" in e.footer.text
    assert e.timestamp is not None


def test_x_embed_has_engagement_but_no_views():
    e = build_video_embed(X_META, "X")
    assert e is not None
    assert e.author.name == "Lis Power"
    assert e.author.url == "https://twitter.com/LisPower1"
    assert "Shep" in e.description
    assert "54.8K" in e.footer.text     # likes
    assert "16.8K" in e.footer.text     # reposts
    assert "👁" not in e.footer.text     # X gives no view count
    assert e.url == X_META['webpage_url']


def test_youtube_embed_keeps_both_title_and_caption():
    e = build_video_embed(YOUTUBE_META, "YouTube")
    assert e is not None
    assert e.title == "Shortest Video on Youtube"
    assert "Mylo the Cat" in e.description
    assert "71.9M" in e.footer.text


def test_title_not_duplicated_into_description():
    """Facebook's title is its caption, so only one of them should appear."""
    e = build_video_embed(FACEBOOK_META, "Facebook")
    caption = FACEBOOK_META['description']
    assert e.description.startswith(caption[:30])
    # the heading must not repeat the caption verbatim
    assert e.title != caption


def test_long_caption_truncated(monkeypatch):
    monkeypatch.setattr(config, "EMBED_DESCRIPTION_LIMIT", 50)
    meta = dict(X_META, description="x" * 500)
    e = build_video_embed(meta, "X")
    assert len(e.description) <= 50
    assert e.description.endswith("…")


def test_embed_survives_minimal_metadata():
    e = build_video_embed({'uploader': 'Someone'}, "TikTok")
    assert e is not None
    assert e.author.name == "Someone"
    assert e.footer.text == "TikTok"


def test_embed_is_none_when_nothing_to_show():
    assert build_video_embed({}, "TikTok") is None
    assert build_video_embed({'duration': 12}, "TikTok") is None


def test_thumbnail_opt_in(monkeypatch):
    assert build_video_embed(FACEBOOK_META, "Facebook").thumbnail.url is None
    monkeypatch.setattr(config, "ENABLE_EMBED_THUMBNAIL", True)
    assert build_video_embed(FACEBOOK_META, "Facebook").thumbnail.url is not None


def test_bad_timestamp_does_not_raise():
    e = build_video_embed(dict(X_META, timestamp="not-a-number"), "X")
    assert e is not None


@pytest.mark.parametrize("platform", ["Instagram", "TikTok", "YouTube", "Facebook", "Reddit", "X"])
def test_every_platform_has_a_colour(platform):
    assert platform in config.PLATFORM_COLORS
    e = build_video_embed({'uploader': 'u', 'description': 'd'}, platform)
    assert e.colour.value == config.PLATFORM_COLORS[platform]


# --- Instagram: captured from the deployed container (yt-dlp nightly) ------

INSTAGRAM_META = {
    'id': 'Dfml1Q9hE8i',
    'title': 'Video by wowforeverguide',
    'description': (
        "dual spec or mount first at 40? 👇\n\n\n"
        "quick maths for druids.\n\n\n"
        "travel form is instant and makes questing far smoother"
    ),
    'uploader': 'WoW Forever Guide',
    'like_count': 2437,
    'comment_count': 164,
    'timestamp': 1794403812,
    'thumbnail': 'https://instagram.flas1-1.fna.fbcdn.net/v/t51.82787-15/902591736.jpg',
    'webpage_url': 'https://www.instagram.com/reel/Dfml1Q9hE8i/?cplk=MWluaGd3c2VuNDZhYg==',
}


def test_instagram_boilerplate_title_dropped():
    """Instagram titles are just "Video by <handle>" -- no information."""
    assert clean_title("Video by wowforeverguide", "Instagram") == ""
    assert clean_title("Reel by someone", "Instagram") == ""
    # a genuine title must survive
    assert clean_title("Actual caption here", "Instagram") == "Actual caption here"


def test_instagram_embed_uses_caption_not_boilerplate():
    e = build_video_embed(INSTAGRAM_META, "Instagram")
    assert e is not None
    assert e.author.name == "WoW Forever Guide"
    assert "Video by" not in (e.title or "")
    assert e.title == "View on Instagram"
    assert e.description.startswith("dual spec or mount first at 40?")
    # Instagram reports likes/comments but neither views nor duration
    assert "2.4K" in e.footer.text
    assert "164" in e.footer.text
    assert "👁" not in e.footer.text
    assert "⏱" not in e.footer.text


def test_instagram_caption_keeps_paragraphs():
    e = build_video_embed(INSTAGRAM_META, "Instagram")
    # multi-line caption keeps its breaks, but never more than one blank line
    assert "\n" in e.description
    assert "\n\n\n" not in e.description


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("a\n\n\n\nb", "a\n\nb"),
        ("a\nb", "a\nb"),
        ("  padded  \n  lines  ", "padded\nlines"),
        ("\n\nleading and trailing\n\n", "leading and trailing"),
        ("", ""),
        ("   ", ""),
    ],
)
def test_normalize_caption(raw, expected):
    assert normalize_caption(raw) == expected


def test_discord_field_limits_respected():
    """Discord rejects titles >256 and descriptions >4096."""
    meta = {
        'title': "T" * 900,
        'description': "D" * 9000,
        'uploader': "U" * 900,
        'webpage_url': 'https://x.com/a/status/1',
    }
    e = build_video_embed(meta, "X")
    assert len(e.title or "") <= 256
    assert len(e.description or "") <= 4096
    assert len(e.author.name or "") <= 256
