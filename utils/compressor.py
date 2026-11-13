"""Video compression utilities using ffmpeg.

Sizing strategy
---------------
File size is just bitrate x duration, so the encode bitrate needed to hit a
target size is arithmetic, not guesswork:

    total_bitrate = (target_bytes * 8 * container_efficiency) / duration
    video_bitrate = total_bitrate - audio_bitrate

The catch is that the bitrate target only applies in ABR mode. Passing both
``-b:v`` and ``-crf`` to libx264 makes it honour the CRF and ignore the
bitrate entirely, so the computed size budget has no effect -- which is why a
CRF-based encoder needs repeated escalating attempts and still overshoots.

So: plan the bitrate from the duration budget, encode once in ABR mode with
``-maxrate``/``-bufsize`` to stop the peaks overshooting, then verify. If the
result still misses, correct using the *measured* error rather than a blind
guess. In practice the first encode lands.
"""

import logging
import os
from dataclasses import dataclass
from typing import Optional

import ffmpeg

import config

logger = logging.getLogger(__name__)

# MP4 container overhead (moov atom, per-frame headers). Aim slightly under
# the target so muxing overhead doesn't push the file over.
CONTAINER_EFFICIENCY = 0.97

# Audio bitrates to choose from, best first.
AUDIO_BITRATE_LADDER = (128_000, 96_000, 64_000, 48_000, 32_000)

# Share of the total budget audio may take. Proportional rather than enforcing
# a fixed video floor: a fixed floor collapses audio to the minimum on any
# longer clip, where the total budget is small but audio is still most of what
# matters (speech, music).
AUDIO_BUDGET_FRACTION = 0.15

# Below this, video is too degraded to be worth posting -- better to decline
# than to spend CPU producing a smear.
MIN_USABLE_VIDEO_BITRATE = 100_000

# Bits per pixel per frame that x264 needs for acceptable quality. Used to
# pick a downscale target: at low bitrates, fewer pixels look better than
# more smeared ones.
TARGET_BITS_PER_PIXEL = 0.08

# Never scale below this height, however tight the budget.
MIN_SCALE_HEIGHT = 144


@dataclass
class CompressionPlan:
    """The encoder settings calculated to hit a target size in one encode."""

    video_bitrate: int
    audio_bitrate: int
    scale_height: Optional[int]  # None = keep source resolution
    feasible: bool
    reason: str = ""


def _choose_scale_height(width: int, height: int, fps: float, video_bitrate: int) -> Optional[int]:
    """
    Pick a downscale height appropriate to the available bitrate.

    Works from a pixel budget rather than a ladder of standard heights,
    because the bot's main content is vertical: for a 1080x1920 reel, a
    "1080" rung means 1080 *height* and would downscale a portrait video
    that needed no downscaling at all.

    Args:
        width: Source width in pixels
        height: Source height in pixels
        fps: Source frame rate
        video_bitrate: The video bitrate the plan allows

    Returns:
        A height to scale to, or None to keep the source resolution
    """
    if not (width and height and fps):
        return None

    affordable_pixels = video_bitrate / (TARGET_BITS_PER_PIXEL * fps)
    source_pixels = width * height

    # Enough bitrate for the source as-is; never upscale
    if source_pixels <= affordable_pixels:
        return None

    factor = (affordable_pixels / source_pixels) ** 0.5
    scaled = int(height * factor)
    scaled -= scaled % 2  # libx264 needs even dimensions

    scaled = max(MIN_SCALE_HEIGHT, scaled)

    return None if scaled >= height else scaled


def plan_compression(
    duration: float,
    target_size_bytes: int,
    width: int = 0,
    height: int = 0,
    fps: float = 0.0,
    has_audio: bool = True,
) -> CompressionPlan:
    """
    Work out the encoder settings that should hit the target size in one pass.

    Args:
        duration: Video duration in seconds
        target_size_bytes: The size the output must fit within
        width: Source width in pixels (0 if unknown)
        height: Source height in pixels (0 if unknown)
        fps: Source frame rate (0 if unknown)
        has_audio: Whether the source has an audio track

    Returns:
        A CompressionPlan. When ``feasible`` is False the caller should decline
        rather than encode -- no bitrate can satisfy the target.
    """
    if duration <= 0:
        return CompressionPlan(0, 0, None, False, "unknown duration")

    total_bitrate = (target_size_bytes * 8 * CONTAINER_EFFICIENCY) / duration

    # Give audio a proportional slice, capped at transparent-enough quality
    # and floored at the lowest rung rather than starving it entirely.
    audio_bitrate = 0
    if has_audio:
        allowance = total_bitrate * AUDIO_BUDGET_FRACTION
        audio_bitrate = next(
            (rung for rung in AUDIO_BITRATE_LADDER if rung <= allowance),
            AUDIO_BITRATE_LADDER[-1],
        )

    video_bitrate = int(total_bitrate - audio_bitrate)

    if video_bitrate < MIN_USABLE_VIDEO_BITRATE:
        return CompressionPlan(
            video_bitrate,
            audio_bitrate,
            None,
            False,
            f"needs {video_bitrate / 1000:.0f}kbps video for {duration:.0f}s in "
            f"{target_size_bytes / 1024 / 1024:.1f}MB, below the {MIN_USABLE_VIDEO_BITRATE / 1000:.0f}kbps floor",
        )

    scale_height = _choose_scale_height(width, height, fps, video_bitrate)

    return CompressionPlan(video_bitrate, audio_bitrate, scale_height, True)


def probe_source(input_path: str) -> Optional[dict]:
    """
    Read the properties needed to plan an encode.

    Args:
        input_path: Path to the video file

    Returns:
        Dict with duration/size/width/height/fps/has_audio, or None on failure
    """
    try:
        probe = ffmpeg.probe(input_path)
    except Exception as e:
        logger.error(f"Failed to probe video: {str(e)}")
        return None

    streams = probe.get('streams') or []
    video = next((s for s in streams if s.get('codec_type') == 'video'), None)
    has_audio = any(s.get('codec_type') == 'audio' for s in streams)

    # r_frame_rate arrives as a rational string like "30000/1001"
    fps = 0.0
    if video:
        raw_fps = video.get('r_frame_rate') or video.get('avg_frame_rate') or ''
        try:
            numerator, _, denominator = raw_fps.partition('/')
            fps = float(numerator) / float(denominator or 1)
        except (ValueError, ZeroDivisionError):
            fps = 0.0

    try:
        duration = float(probe['format']['duration'])
    except (KeyError, ValueError, TypeError):
        duration = 0.0

    return {
        'duration': duration,
        'size': int(probe.get('format', {}).get('size') or 0),
        'width': int(video.get('width') or 0) if video else 0,
        'height': int(video.get('height') or 0) if video else 0,
        'fps': fps,
        'has_audio': has_audio,
    }


def _encode(input_path: str, output_path: str, plan: CompressionPlan, preset: str = 'medium') -> None:
    """
    Run a single ABR encode.

    Args:
        input_path: Source file
        output_path: Destination file
        plan: The settings to encode with
        preset: x264 preset

    Raises:
        ffmpeg.Error: if ffmpeg fails
    """
    if os.path.exists(output_path):
        os.remove(output_path)

    kwargs = {
        'vcodec': 'libx264',
        'preset': preset,
        # ABR mode. Deliberately NO crf: setting both makes x264 ignore the
        # bitrate, which is what breaks size targeting.
        'video_bitrate': plan.video_bitrate,
        'maxrate': int(plan.video_bitrate * 1.25),
        'bufsize': int(plan.video_bitrate * 2),
        'pix_fmt': 'yuv420p',  # broadest player compatibility
        'movflags': '+faststart',
    }

    if plan.scale_height:
        # -2 keeps the aspect ratio and an even width, which libx264 requires
        kwargs['vf'] = f"scale=-2:{plan.scale_height}"

    if plan.audio_bitrate:
        kwargs['acodec'] = 'aac'
        kwargs['audio_bitrate'] = plan.audio_bitrate
    else:
        kwargs['an'] = None

    stream = ffmpeg.output(ffmpeg.input(input_path), output_path, **kwargs)
    ffmpeg.run(stream, overwrite_output=True, quiet=True)


def compress_video(input_path: str, target_size_bytes: int, max_attempts: int = 3) -> Optional[str]:
    """
    Compress a video to fit within a target file size.

    The bitrate is calculated from the duration budget so the first encode
    should land under the target. Any further encode is a correction based on
    the measured size, not a blind escalation.

    Args:
        input_path: Path to the input video file
        target_size_bytes: Target file size in bytes
        max_attempts: Maximum number of encodes to run

    Returns:
        Path to the compressed video file, or None if it could not be done
    """
    logger.info(
        f"Starting compression for {input_path} (target: {target_size_bytes / 1024 / 1024:.2f}MB)"
    )

    source = probe_source(input_path)
    if not source:
        return None

    logger.info(
        f"Original: {source['size'] / 1024 / 1024:.2f}MB, {source['duration']:.2f}s, "
        f"{source['width']}x{source['height']} @ {source['fps']:.1f}fps, "
        f"audio={'yes' if source['has_audio'] else 'no'}"
    )

    plan = plan_compression(
        duration=source['duration'],
        target_size_bytes=target_size_bytes,
        width=source['width'],
        height=source['height'],
        fps=source['fps'],
        has_audio=source['has_audio'],
    )

    # Decline up front instead of burning CPU on encodes that cannot succeed
    if not plan.feasible:
        logger.warning(f"Cannot compress to target: {plan.reason}")
        return None

    base, ext = os.path.splitext(input_path)
    output_path = f"{base}_compressed{ext}"

    logger.info(
        f"Plan: video={plan.video_bitrate / 1000:.0f}kbps audio={plan.audio_bitrate / 1000:.0f}kbps"
        + (f" scale=-2:{plan.scale_height}" if plan.scale_height else " (no rescale)")
    )

    for attempt in range(1, max(1, max_attempts) + 1):
        try:
            _encode(input_path, output_path, plan)
        except ffmpeg.Error as e:
            stderr = e.stderr.decode(errors='replace') if e.stderr else str(e)
            logger.error(f"FFmpeg error on encode {attempt}: {stderr[-400:]}")
            break
        except Exception as e:
            logger.error(f"Unexpected error on encode {attempt}: {str(e)}")
            break

        if not os.path.exists(output_path):
            logger.error("Encode reported success but produced no file")
            break

        output_size = os.path.getsize(output_path)
        ratio = output_size / target_size_bytes
        logger.info(
            f"Encode {attempt}: {output_size / 1024 / 1024:.2f}MB "
            f"({ratio * 100:.0f}% of target)"
        )

        if output_size <= target_size_bytes:
            logger.info(f"Compression successful on encode {attempt}")
            return output_path

        if attempt >= max_attempts:
            break

        # Correct using the measured overshoot rather than guessing. The 0.95
        # keeps the correction slightly conservative so it doesn't need a third.
        corrected = int(plan.video_bitrate / ratio * 0.95)
        if corrected < MIN_USABLE_VIDEO_BITRATE:
            logger.warning(
                f"Correction would need {corrected / 1000:.0f}kbps, below the usable floor"
            )
            break

        logger.info(
            f"Overshot by {(ratio - 1) * 100:.0f}%, correcting "
            f"{plan.video_bitrate / 1000:.0f} -> {corrected / 1000:.0f}kbps"
        )
        plan = CompressionPlan(
            corrected,
            plan.audio_bitrate,
            _choose_scale_height(source['width'], source['height'], source['fps'], corrected),
            True,
        )

    logger.warning("Failed to compress video to target size")
    if os.path.exists(output_path):
        os.remove(output_path)

    return None


def get_video_info(filepath: str) -> Optional[dict]:
    """
    Get information about a video file.

    Args:
        filepath: Path to the video file

    Returns:
        Dictionary containing video information, or None if probe failed
    """
    source = probe_source(filepath)
    if not source:
        return None

    return {
        'duration': source['duration'],
        'size': source['size'],
        'bitrate': int(source['size'] * 8 / source['duration']) if source['duration'] else 0,
        'width': source['width'],
        'height': source['height'],
    }
