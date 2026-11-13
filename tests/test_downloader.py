"""Download-path tests: error classification and filename sanitising.

Run with:  uv run --with pytest pytest -q
"""

import pytest

from utils.downloader import _classify_error, _first_entry, sanitize_filename

# Real error strings captured from yt-dlp 2025.12.08 against live URLs
REDDIT_AUTH = (
    "ERROR: [Reddit] 1xvbovp: Account authentication is required. Use --cookies, "
    "--cookies-from-browser, --username and --password, --netrc-cmd, or --netrc "
    "(reddit) to provide account credentials."
)
X_UNSUPPORTED = "ERROR: Unsupported URL: https://snpy.tv/"
FB_PARSE = (
    "ERROR: [facebook] 3676516585958356: Cannot parse data; please report this "
    "issue on https://github.com/yt-dlp/yt-dlp/issues"
)


@pytest.mark.parametrize(
    "msg,expected",
    [
        (REDDIT_AUTH, "auth"),
        # "Unsupported URL" must win over the word "cookies" -> stay silent
        (X_UNSUPPORTED, "novideo"),
        ("ERROR: No video could be found in this post", "novideo"),
        ("ERROR: [Reddit] No media found", "novideo"),
        ("ERROR: Requested format is not available. No formats found", "novideo"),
        ("ERROR: Sign in to confirm your age", "auth"),
        ("ERROR: Private video. Sign in if you've been granted access", "auth"),
        ("ERROR: Reddit - Prove your humanity", "auth"),
        (FB_PARSE, "failed"),
        ("ERROR: HTTP Error 500: Domain Not Found", "failed"),
        ("ERROR: Unable to download webpage: timed out", "failed"),
    ],
)
def test_error_classification(msg, expected):
    assert _classify_error(msg) == expected


@pytest.mark.parametrize(
    "title,expected",
    [
        ("a/b/c", "a_b_c"),
        ("line one\nline two", "line one line two"),
        ("", "video"),
        ("...", "video"),
        ("___", "video"),
        ("🎉🎉🎉", "video"),
    ],
)
def test_sanitize_filename(title, expected):
    assert sanitize_filename(title) == expected


def test_sanitize_filename_on_real_facebook_title():
    """X/Facebook titles carry stats, separators and emoji."""
    out = sanitize_filename("9.9K views · 340 reactions | When your trying to help")
    assert out.startswith("9.9K views")
    assert len(out) <= 50
    assert "·" not in out and "|" not in out
    assert "__" not in out  # underscore runs collapsed


def test_sanitize_filename_is_always_usable():
    for title in ["", "/", "   ", "..", "🙂", "a" * 500]:
        out = sanitize_filename(title)
        assert out
        assert len(out) <= 50
        assert "/" not in out
        assert "\n" not in out


def test_first_entry_flattens_playlist():
    info = {
        "_type": "playlist",
        "entries": [{"id": "inner", "title": "first", "duration": 12}],
    }
    assert _first_entry(info)["id"] == "inner"


def test_first_entry_flattens_nested_playlist():
    info = {
        "_type": "playlist",
        "entries": [
            {"_type": "multi_video", "entries": [{"id": "deep", "duration": 3}]}
        ],
    }
    assert _first_entry(info)["id"] == "deep"


def test_first_entry_skips_none_entries():
    info = {"_type": "playlist", "entries": [None, {"id": "real"}]}
    assert _first_entry(info)["id"] == "real"


def test_first_entry_passthrough_and_empty():
    assert _first_entry({"id": "plain"})["id"] == "plain"
    assert _first_entry(None) == {}
    assert _first_entry({"_type": "playlist", "entries": []}) == {
        "_type": "playlist",
        "entries": [],
    }
