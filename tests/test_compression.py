"""Compression planning and upload-limit tests.

The sizing numbers come from a real case in the logs: a 28.75MB Instagram reel
of 55.97s that the old CRF-based encoder could not fit into 8MB.

Run with:  uv run --with pytest pytest -q
"""

import pytest

import config
from utils.compressor import (
    AUDIO_BITRATE_LADDER,
    CONTAINER_EFFICIENCY,
    MIN_USABLE_VIDEO_BITRATE,
    _choose_scale_height,
    plan_compression,
)
from utils.limits import resolve_upload_limit

# The real clip from the logs
REEL_DURATION = 55.97
MB = 1024 * 1024


class FakeGuild:
    def __init__(self, filesize_limit):
        self.filesize_limit = filesize_limit


# --- upload limit resolution ----------------------------------------------

@pytest.mark.parametrize(
    "reported,tier",
    [
        (10 * MB, "0/1 unboosted"),
        (50 * MB, "2"),
        (100 * MB, "3"),
    ],
)
def test_limit_follows_guild_tier(reported, tier, monkeypatch):
    monkeypatch.setattr(config, "MAX_FILE_SIZE_OVERRIDE", 0)
    resolved = resolve_upload_limit(FakeGuild(reported))
    assert resolved < reported, "must leave headroom for the embed/multipart"
    assert resolved > reported * 0.9, f"tier {tier} headroom should be small"


def test_limit_override_wins(monkeypatch):
    monkeypatch.setattr(config, "MAX_FILE_SIZE_OVERRIDE", 5 * MB)
    assert resolve_upload_limit(FakeGuild(100 * MB)) == 5 * MB


def test_limit_falls_back_without_guild(monkeypatch):
    monkeypatch.setattr(config, "MAX_FILE_SIZE_OVERRIDE", 0)
    expected = config.MAX_FILE_SIZE_FALLBACK - config.UPLOAD_SIZE_HEADROOM
    assert resolve_upload_limit(None) == expected


def test_limit_falls_back_on_nonsense_value(monkeypatch):
    monkeypatch.setattr(config, "MAX_FILE_SIZE_OVERRIDE", 0)
    expected = config.MAX_FILE_SIZE_FALLBACK - config.UPLOAD_SIZE_HEADROOM
    assert resolve_upload_limit(FakeGuild(0)) == expected
    assert resolve_upload_limit(FakeGuild(None)) == expected
    assert resolve_upload_limit(object()) == expected


def test_limit_never_negative(monkeypatch):
    monkeypatch.setattr(config, "MAX_FILE_SIZE_OVERRIDE", 0)
    assert resolve_upload_limit(FakeGuild(1024)) >= 1


# --- the core sizing arithmetic -------------------------------------------

@pytest.mark.parametrize("target_mb", [8, 10, 25, 50])
def test_planned_bitrate_predicts_target_size(target_mb):
    """bitrate x duration must reconstruct the target size, within overhead."""
    target = target_mb * MB
    plan = plan_compression(REEL_DURATION, target, 1080, 1920, 30.0, has_audio=True)
    assert plan.feasible

    predicted_bytes = (plan.video_bitrate + plan.audio_bitrate) * REEL_DURATION / 8
    # Should be just under target -- never over, and not wastefully under
    assert predicted_bytes <= target
    assert predicted_bytes > target * 0.9


def test_audio_budget_is_subtracted():
    """Regression: the old code sized video off the whole budget, then added audio."""
    target = 8 * MB
    plan = plan_compression(REEL_DURATION, target, 1080, 1920, 30.0, has_audio=True)
    total = (target * 8 * CONTAINER_EFFICIENCY) / REEL_DURATION
    assert plan.video_bitrate == pytest.approx(total - plan.audio_bitrate, rel=0.01)


def test_no_audio_track_spends_everything_on_video():
    plan = plan_compression(REEL_DURATION, 8 * MB, 1080, 1920, 30.0, has_audio=False)
    assert plan.audio_bitrate == 0
    total = (8 * MB * 8 * CONTAINER_EFFICIENCY) / REEL_DURATION
    assert plan.video_bitrate == pytest.approx(total, rel=0.01)


def test_audio_degrades_only_when_video_would_starve():
    """A roomy budget keeps good audio; a tight one sacrifices it."""
    roomy = plan_compression(30, 50 * MB, 720, 1280, 30.0)
    tight = plan_compression(600, 8 * MB, 720, 1280, 30.0)
    assert roomy.audio_bitrate == AUDIO_BITRATE_LADDER[0]
    assert tight.audio_bitrate < roomy.audio_bitrate


def test_impossible_target_is_declined_not_attempted():
    """A 2-hour video in 8MB must be refused before any encode runs."""
    plan = plan_compression(7200, 8 * MB, 1920, 1080, 30.0)
    assert not plan.feasible
    assert "floor" in plan.reason
    assert plan.video_bitrate < MIN_USABLE_VIDEO_BITRATE


def test_unknown_duration_declined():
    assert not plan_compression(0, 8 * MB).feasible
    assert not plan_compression(-5, 8 * MB).feasible


def test_the_real_failing_case_now_fits_in_8mb():
    """The 28.75MB / 55.97s reel from the logs."""
    plan = plan_compression(REEL_DURATION, 8 * MB, 1080, 1920, 30.0, has_audio=True)
    assert plan.feasible
    # ~1.1Mbps total for 56s in 8MB
    assert 900_000 < plan.video_bitrate < 1_200_000


def test_unboosted_10mb_limit_is_roomier_than_old_8mb():
    """The dynamic limit should allow a higher bitrate than the old constant."""
    old = plan_compression(REEL_DURATION, 8 * MB, 1080, 1920, 30.0)
    new = plan_compression(REEL_DURATION, 10 * MB - config.UPLOAD_SIZE_HEADROOM, 1080, 1920, 30.0)
    assert new.video_bitrate > old.video_bitrate


def test_boosted_server_needs_no_compression_at_all():
    """28.75MB is already under a tier-2 limit, so the handler won't compress."""
    assert 28.75 * MB < resolve_upload_limit(FakeGuild(50 * MB))


# --- resolution laddering --------------------------------------------------

def test_high_bitrate_keeps_source_resolution():
    assert _choose_scale_height(1080, 1920, 30.0, 20_000_000) is None


def test_low_bitrate_downscales():
    chosen = _choose_scale_height(1080, 1920, 30.0, 400_000)
    assert chosen is not None
    assert chosen < 1920


def test_scale_never_upscales():
    # A 360p source must never be scaled up, however much bitrate is available
    assert _choose_scale_height(640, 360, 30.0, 50_000_000) is None


def test_scale_handles_unknown_dimensions():
    assert _choose_scale_height(0, 0, 0.0, 1_000_000) is None


def test_lower_bitrate_never_picks_larger_resolution():
    """The ladder must be monotonic: less bitrate cannot mean more pixels."""
    heights = [
        _choose_scale_height(1080, 1920, 30.0, bitrate) or 1920
        for bitrate in (200_000, 500_000, 1_000_000, 3_000_000, 10_000_000)
    ]
    assert heights == sorted(heights), heights
