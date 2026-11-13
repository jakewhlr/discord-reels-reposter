"""Event-loop responsiveness tests for the video handler.

The bot runs blocking work (yt-dlp, ffmpeg) that must never execute directly
on the asyncio event loop: while it does, discord.py cannot send gateway
heartbeats and the shard is eventually dropped. These tests measure the loop's
responsiveness while a deliberately slow blocking call is in flight.

Run with:  uv run --with pytest pytest -q
"""

import asyncio
import time

import cogs.video_handler as vh
from cogs.video_handler import VideoHandler

# A blocking call long enough that direct execution is unmistakable, but short
# enough to keep the suite fast.
BLOCK_SECONDS = 0.4

# The loop should keep servicing timers throughout. Generous enough not to
# flake on a loaded machine, far below BLOCK_SECONDS.
MAX_ACCEPTABLE_STALL = 0.2


class FakeMessage:
    """Minimal stand-in for discord.Message."""

    def __init__(self):
        self.replies = []
        self.reactions = []

    async def add_reaction(self, emoji):
        self.reactions.append(emoji)

    async def remove_reaction(self, emoji, user):
        pass

    async def reply(self, *args, **kwargs):
        self.replies.append((args, kwargs))


class FakeBot:
    user = object()


async def _worst_stall_while(coro_factory):
    """
    Run a coroutine while a 20ms timer ticks, and report the largest gap
    between consecutive ticks.

    A gap much larger than the tick interval means the event loop was blocked
    and could not service timers -- which is precisely what stops discord.py
    from sending gateway heartbeats.
    """
    ticks = []

    async def heartbeat():
        while True:
            await asyncio.sleep(0.02)
            ticks.append(time.monotonic())

    beat = asyncio.create_task(heartbeat())
    # Let the heartbeat actually start ticking. Without this the task is
    # merely scheduled: process_video_url's early awaits (reaction stubs)
    # never yield, so a blocking call would run before the first tick.
    while len(ticks) < 2:
        await asyncio.sleep(0.01)
    try:
        await coro_factory()
    finally:
        # Yield before cancelling, so the timer that was held off by any
        # blocking call gets to fire and record its (late) tick. Cancelling
        # immediately would discard the very stall being measured.
        await asyncio.sleep(0.05)
        beat.cancel()

    gaps = [later - earlier for earlier, later in zip(ticks, ticks[1:])]
    return max(gaps) if gaps else 0.0


def test_download_runs_off_the_event_loop(monkeypatch):
    """A slow download must not stall the loop (regression: heartbeat blocked)."""

    def slow_blocking_download(url):
        time.sleep(BLOCK_SECONDS)  # exactly what yt-dlp does
        return None  # treated as a download failure

    monkeypatch.setattr(vh, "download_video", slow_blocking_download)

    async def main():
        handler = VideoHandler(FakeBot())
        message = FakeMessage()
        return await _worst_stall_while(
            lambda: handler.process_video_url(message, "https://x.com/a/status/1", "X")
        )

    worst = asyncio.run(main())
    assert worst < MAX_ACCEPTABLE_STALL, (
        f"event loop blocked for {worst:.2f}s during download; "
        "download_video must be awaited via asyncio.to_thread"
    )


def test_compression_runs_off_the_event_loop(monkeypatch, tmp_path):
    """Compression is the longest blocking call and must also be offloaded."""
    fake_video = tmp_path / "video.mp4"
    fake_video.write_bytes(b"0" * (config_max_size() + 1))  # oversized -> compresses

    monkeypatch.setattr(
        vh,
        "download_video",
        lambda url: {
            'filepath': str(fake_video),
            'filesize': fake_video.stat().st_size,
            'title': 'clip',
            'duration': 10,
            'metadata': {},
        },
    )

    def slow_blocking_compress(path, target, attempts):
        time.sleep(BLOCK_SECONDS)  # exactly what ffmpeg.run does
        return None  # compression failed -> handler replies and bails

    monkeypatch.setattr(vh, "compress_video", slow_blocking_compress)

    async def main():
        handler = VideoHandler(FakeBot())
        message = FakeMessage()
        return await _worst_stall_while(
            lambda: handler.process_video_url(message, "https://x.com/a/status/1", "X")
        )

    worst = asyncio.run(main())
    assert worst < MAX_ACCEPTABLE_STALL, (
        f"event loop blocked for {worst:.2f}s during compression; "
        "compress_video must be awaited via asyncio.to_thread"
    )


def config_max_size():
    import config

    return config.MAX_FILE_SIZE


def test_concurrent_jobs_are_bounded(monkeypatch):
    """The semaphore must cap how many blocking jobs run at once."""
    import config

    monkeypatch.setattr(config, "MAX_CONCURRENT_JOBS", 2)

    in_flight = 0
    peak = 0

    def tracking_download(url):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        time.sleep(0.05)
        in_flight -= 1
        return None

    monkeypatch.setattr(vh, "download_video", tracking_download)

    async def main():
        handler = VideoHandler(FakeBot())
        await asyncio.gather(*(
            handler.process_video_url(FakeMessage(), f"https://x.com/a/status/{i}", "X")
            for i in range(8)
        ))

    asyncio.run(main())
    assert peak <= 2, f"{peak} jobs ran concurrently, expected at most 2"


def test_failed_download_still_replies(monkeypatch):
    """Offloading must not change the user-visible behaviour."""
    monkeypatch.setattr(vh, "download_video", lambda url: None)

    async def main():
        handler = VideoHandler(FakeBot())
        message = FakeMessage()
        await handler.process_video_url(message, "https://x.com/a/status/1", "X")
        return message

    message = asyncio.run(main())
    assert message.replies, "a failed download should still produce a reply"
    assert "❌" in message.reactions


def test_non_video_link_stays_silent(monkeypatch):
    """A 'novideo' result must produce no reply at all."""
    monkeypatch.setattr(vh, "download_video", lambda url: {'error': 'novideo'})

    async def main():
        handler = VideoHandler(FakeBot())
        message = FakeMessage()
        await handler.process_video_url(message, "https://x.com/a/status/1", "X")
        return message

    message = asyncio.run(main())
    assert message.replies == [], "non-video links must not be answered"


def test_auth_required_replies_with_lock(monkeypatch):
    monkeypatch.setattr(vh, "download_video", lambda url: {'error': 'auth'})

    async def main():
        handler = VideoHandler(FakeBot())
        message = FakeMessage()
        await handler.process_video_url(message, "https://x.com/a/status/1", "X")
        return message

    message = asyncio.run(main())
    assert message.replies
    assert "🔒" in message.reactions
